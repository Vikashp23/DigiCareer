import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DB_PATH = Path(os.getenv("DIGICAREER_DB", str(BASE_DIR / "digicareer.db")))
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
if AI_PROVIDER == "gemini":
    MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    client = genai.Client(api_key=API_KEY) if API_KEY else None
else:
    MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    client = None
app = FastAPI(title="DigiCareer AI Interview API", version="1.1.0")

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE COLLATE NOCASE, salt TEXT NOT NULL,
          password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS interviews(
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role TEXT NOT NULL, interview_type TEXT NOT NULL, level TEXT NOT NULL,
          question_count INTEGER NOT NULL, language TEXT NOT NULL, current_question TEXT NOT NULL,
          transcript TEXT NOT NULL, status TEXT NOT NULL, score INTEGER, report TEXT,
          created_at TEXT NOT NULL, finished_at TEXT, job_description TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_interviews_user ON interviews(user_id, created_at DESC);
        """)
        columns = {row["name"] for row in con.execute("PRAGMA table_info(interviews)").fetchall()}
        if "job_description" not in columns:
            con.execute("ALTER TABLE interviews ADD COLUMN job_description TEXT NOT NULL DEFAULT ''")

init_db()

class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class StartBody(BaseModel):
    role: str = Field(min_length=2, max_length=100)
    interview_type: str = Field(pattern="^(mixed|technical|hr|communication)$")
    level: str = Field(min_length=1, max_length=30)
    question_count: int = Field(ge=5, le=12)
    language: str = Field(min_length=2, max_length=30)
    job_description: str = Field(default="", max_length=20000)

class AnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)

def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000).hex()

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(36)
    with connect() as con:
        con.execute("INSERT INTO sessions(token_hash,user_id,created_at) VALUES(?,?,?)",
                    (token_digest(token), user_id, now_iso()))
    return token

def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in.")
    digest = token_digest(authorization[7:].strip())
    with connect() as con:
        row = con.execute("""SELECT u.id,u.name,u.email FROM users u
          JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=?""", (digest,)).fetchone()
    if not row:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return dict(row)

def require_ai():
    if not client:
        raise HTTPException(503, "AI is not configured. Set GEMINI_API_KEY in the server environment.")
    return client

def extract_output(response) -> str:
    output = getattr(response, "output_text", None)
    if output:
        return output.strip()
    raise ValueError("The AI service returned no text.")

def ask_ai(instructions: str, payload: dict) -> dict:
    ai = require_ai()
    try:
        if AI_PROVIDER != "gemini":
            raise RuntimeError("This deployment is configured for Gemini. Set AI_PROVIDER=gemini.")

        response = None
        for attempt in range(3):
            try:
                response = ai.models.generate_content(
                    model=MODEL,
                    contents=json.dumps(payload, ensure_ascii=False),
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        response_mime_type="application/json",
                        max_output_tokens=1400,
                    ),
                )
                break
            except Exception as exc:
                message = str(exc).upper()
                transient = any(marker in message for marker in (
                    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                    "500", "INTERNAL", "TIMEOUT", "TIMED OUT",
                ))
                if not transient or attempt == 2:
                    raise
                delay = 1 + (2 ** attempt)
                print(f"Temporary AI provider error on attempt {attempt + 1}/3; retrying in {delay}s.")
                time.sleep(delay)

        raw = (response.text or "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(502, "The AI response could not be parsed. Please retry your answer.")
    except Exception as exc:
        print("AI provider error:", type(exc).__name__, str(exc)[:300])
        raise HTTPException(502, "The AI interviewer could not respond. Check the server API configuration and try again.")

QUESTION_INSTRUCTIONS = """You are a professional, fair job interviewer conducting practice interviews.
Return ONLY valid JSON with keys: question (string).
Ask exactly one concise question appropriate for the target role, interview type, candidate experience level, language, and supplied job description. When a job description is provided, prioritise its actual responsibilities, required skills, tools, and qualifications. Cover a balanced mix of role-specific technical questions and realistic practical scenarios; include HR questions when the interview type is mixed. Do not invent employer requirements or ask for sensitive personal data. For accounting roles, questions may cover reconciliation, GST, TDS, AP/AR, journals, Excel, controls and month-end close as appropriate. For other roles, use relevant role knowledge. Make it realistic, clear, and not overly difficult for the chosen level."""

ANSWER_INSTRUCTIONS = """You are a professional job interview coach and interviewer. Assess the candidate's answer fairly against the question and role. Do not infer personality or protected traits. Be constructive and specific. Return ONLY valid JSON with keys:
score (integer 0-100), feedback (string, 2-5 sentences), next_question (string), finished (boolean), overall_score (integer 0-100), technical_knowledge (string), answer_clarity (string), structure (string), role_relevance (string), strengths (array of 1-4 strings), improvements (array of 1-5 strings), next_steps (array of 1-5 strings).
The next_question must be one question, ideally a follow-up based on the answer, unless the requested question count has now been reached; when finished=true, next_question may be empty. Score only evidence in the answer: accuracy, completeness, clarity, reasoning and relevance. Do not reward verbosity alone. The overall fields should be brief and actionable. Use the requested language for feedback. If the candidate's answer is blank or irrelevant, say so tactfully. The system decides when the question count is reached; obey the finish_now flag."""

def load_interview(interview_id: str, user_id: int):
    with connect() as con:
        row = con.execute("SELECT * FROM interviews WHERE id=? AND user_id=?", (interview_id,user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Interview not found.")
    return dict(row)

def interview_public(row):
    transcript = json.loads(row["transcript"])
    return {"id":row["id"],"role":row["role"],"interview_type":row["interview_type"],
            "level":row["level"],"question_count":row["question_count"],"language":row["language"],
            "job_description":row.get("job_description",""),"current_question":row["current_question"],"answers":transcript,"status":row["status"],
            "score":row["score"]}

def build_report(row, transcript, last_feedback=None):
    feedback = [x for x in transcript if x.get("feedback")]
    scores = [int(x.get("score",0)) for x in feedback]
    average = round(sum(scores)/len(scores)) if scores else 0
    report = {
        "role": row["role"], "answers_reviewed":len(feedback), "overall_score":average,
        "technical_knowledge": (last_feedback or {}).get("technical_knowledge","Not enough evidence"),
        "answer_clarity": (last_feedback or {}).get("answer_clarity","Not enough evidence"),
        "structure": (last_feedback or {}).get("structure","Not enough evidence"),
        "role_relevance": (last_feedback or {}).get("role_relevance","Not enough evidence"),
        "strengths": (last_feedback or {}).get("strengths",["Continue practising role-specific questions."]),
        "improvements": (last_feedback or {}).get("improvements",["Answer with a clear structure and specific examples."]),
        "next_steps": (last_feedback or {}).get("next_steps",["Review the feedback and practise again."]),
        "answer_feedback":[{"question":x["question"],"answer":x["answer"],"feedback":x.get("feedback",""),"score":x.get("score",0)} for x in feedback]
    }
    return report

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    content = "User-agent: *\\nAllow: /\\nDisallow: /api/\\nSitemap: https://digicareer.onrender.com/sitemap.xml\\n"
    return Response(content=content, media_type="text/plain; charset=utf-8")

@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://digicareer.onrender.com/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>
</urlset>"""
    return Response(content=content, media_type="application/xml; charset=utf-8")

@app.get("/api/health")
def health():
    return {"ok":True,"ai_configured":bool(API_KEY),"model":MODEL if API_KEY else None}

@app.post("/api/register")
def register(body: RegisterBody):
    name = body.name.strip()
    email = body.email.strip().lower()
    if len(name) < 2:
        raise HTTPException(400, "Please enter your name.")
    salt = secrets.token_bytes(16)
    pw_hash = hash_password(body.password, salt)
    try:
        with connect() as con:
            cur = con.execute("INSERT INTO users(name,email,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                (name,email,salt.hex(),pw_hash,now_iso()))
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists. Please sign in.")
    token = issue_session(user_id)
    return {"token":token,"user":{"id":user_id,"name":name,"email":email}}

@app.post("/api/login")
def login(body: LoginBody):
    with connect() as con:
        user = con.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not user or not hmac.compare_digest(hash_password(body.password,bytes.fromhex(user["salt"])),user["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    token = issue_session(user["id"])
    return {"token":token,"user":{"id":user["id"],"name":user["name"],"email":user["email"]}}

@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"user":user}

@app.post("/api/logout")
def logout(user=Depends(current_user), authorization: Optional[str]=Header(default=None)):
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(authorization[7:].strip()),))
    return {"ok":True}

@app.post("/api/interviews")
def start_interview(body: StartBody, user=Depends(current_user)):
    if not API_KEY:
        raise HTTPException(503, "AI is not configured yet. Set GEMINI_API_KEY on the server. See README.md.")
    role = body.role.strip()
    job_description = body.job_description.strip()
    payload={"role":role,"interview_type":body.interview_type,"experience_level":body.level,
             "language":body.language,"job_description":job_description,
             "question_number":1,"total_questions":body.question_count}
    result=ask_ai(QUESTION_INSTRUCTIONS,payload)
    question=str(result.get("question","")).strip()
    if not question:
        raise HTTPException(502,"The AI interviewer did not return a question. Please try again.")
    interview_id=secrets.token_urlsafe(18)
    transcript=[]
    with connect() as con:
        con.execute("""INSERT INTO interviews(id,user_id,role,interview_type,level,question_count,language,current_question,transcript,status,created_at,job_description)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(interview_id,user["id"],role,body.interview_type,body.level,body.question_count,body.language,question,json.dumps(transcript), "in_progress",now_iso(),job_description))
        row=con.execute("SELECT * FROM interviews WHERE id=?",(interview_id,)).fetchone()
    return interview_public(dict(row))

@app.post("/api/interviews/{interview_id}/answer")
def answer_interview(interview_id: str, body: AnswerBody, user=Depends(current_user)):
    row=load_interview(interview_id,user["id"])
    if row["status"]!="in_progress":
        raise HTTPException(409,"This interview is already finished.")
    answer=body.answer.strip()
    if not answer:
        raise HTTPException(400,"Please enter an answer.")
    transcript=json.loads(row["transcript"])
    if len(transcript)>=row["question_count"]:
        raise HTTPException(409,"The question limit has been reached. Finish the interview.")
    payload={"role":row["role"],"interview_type":row["interview_type"],"experience_level":row["level"],
             "language":row["language"],"job_description":row.get("job_description",""),
             "question_number":len(transcript)+1,"total_questions":row["question_count"],
             "finish_now":len(transcript)+1>=row["question_count"],
             "current_question":row["current_question"],"candidate_answer":answer,
             "previous_exchange":[{"question":x["question"],"answer":x["answer"],"feedback":x.get("feedback","")} for x in transcript[-4:]]}
    result=ask_ai(ANSWER_INSTRUCTIONS,payload)
    score=max(0,min(100,int(result.get("score",0))))
    feedback=str(result.get("feedback","Review the answer for accuracy and clarity.")).strip()[:2500]
    transcript.append({"question":row["current_question"],"answer":answer,"score":score,"feedback":feedback})
    finished=bool(payload["finish_now"])
    next_question=str(result.get("next_question","")).strip()[:1200]
    if not finished and not next_question:
        # If the model omitted a follow-up, request a new role-relevant question.
        q=ask_ai(QUESTION_INSTRUCTIONS,{"role":row["role"],"interview_type":row["interview_type"],"experience_level":row["level"],"language":row["language"],"question_number":len(transcript)+1,"total_questions":row["question_count"],"previous_answer":answer})
        next_question=str(q.get("question","")).strip()
        if not next_question:
            finished=True
    report=None
    with connect() as con:
        if finished:
            report=build_report(row,transcript,result)
            con.execute("UPDATE interviews SET transcript=?,current_question='',status='finished',score=?,report=?,finished_at=? WHERE id=? AND user_id=?",
                (json.dumps(transcript,ensure_ascii=False),report["overall_score"],json.dumps(report,ensure_ascii=False),now_iso(),interview_id,user["id"]))
        else:
            con.execute("UPDATE interviews SET transcript=?,current_question=? WHERE id=? AND user_id=?",
                (json.dumps(transcript,ensure_ascii=False),next_question,interview_id,user["id"]))
        updated=con.execute("SELECT * FROM interviews WHERE id=?",(interview_id,)).fetchone()
    return {"interview":interview_public(dict(updated)),"finished":finished,"report":report}

@app.post("/api/interviews/{interview_id}/finish")
def finish_interview(interview_id: str, user=Depends(current_user)):
    row=load_interview(interview_id,user["id"])
    transcript=json.loads(row["transcript"])
    if row["status"]=="finished":
        return {"interview":interview_public(row),"report":json.loads(row["report"] or "{}")}
    if not transcript:
        raise HTTPException(400,"Answer at least one question before finishing.")
    report=build_report(row,transcript)
    with connect() as con:
        con.execute("UPDATE interviews SET status='finished',current_question='',score=?,report=?,finished_at=? WHERE id=? AND user_id=?",
                    (report["overall_score"],json.dumps(report,ensure_ascii=False),now_iso(),interview_id,user["id"]))
        updated=con.execute("SELECT * FROM interviews WHERE id=?",(interview_id,)).fetchone()
    return {"interview":interview_public(dict(updated)),"report":report}

@app.get("/api/history")
def history(user=Depends(current_user)):
    with connect() as con:
        rows=con.execute("""SELECT id,role,interview_type,question_count,score,status,created_at
        FROM interviews WHERE user_id=? ORDER BY created_at DESC LIMIT 50""",(user["id"],)).fetchall()
    return {"interviews":[dict(r) for r in rows]}

@app.get("/api/interviews/{interview_id}")
def get_interview(interview_id: str, user=Depends(current_user)):
    row=load_interview(interview_id,user["id"])
    return {"interview":interview_public(row),"report":json.loads(row["report"]) if row["report"] else None}

# Static assets are served after API routes.
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")
