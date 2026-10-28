# DigiCareer AI Interview Portal

A starter full-stack app for an AI-led interview practice portal. Includes registration/sign-in, password hashing, saved interview history, role selection, one-question-at-a-time interviews, adaptive follow-up questions, feedback, and a downloadable report.

## What is included
- `index.html` — browser interface
- `main.py` — FastAPI backend and API routes
- `requirements.txt` — Python dependencies
- `.env.example` — server-side configuration template

## Requirements
- Python 3.10 or newer
- An OpenAI API key with API billing enabled. ChatGPT subscriptions and API billing are separate.
- Internet connection for AI interview requests.

## Run locally on Windows
1. Extract the ZIP to a folder.
2. Open that folder in Command Prompt or PowerShell.
3. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   ```
4. Install packages:
   ```powershell
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env`, then set your API key and preferred model. Never share the key or put it in `index.html`.
6. The backend loads the `.env` file automatically when it starts. Alternatively, you can set the variables in your terminal:
   ```powershell
   $env:OPENAI_API_KEY="your-api-key"
   $env:OPENAI_MODEL="gpt-6-luna"
   ```
7. Start the server:
   ```powershell
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```
8. Open http://127.0.0.1:8000 in your browser.

## Notes before public launch
- This is a starter project, not a production-audited service.
- AI responses require an API key and may incur usage charges. Confirm model access and pricing in your API account.
- SQLite is suitable for local testing, not a high-availability public deployment.
- For production, use HTTPS, secure HttpOnly cookies, rate limiting, email verification, password reset, abuse controls, database backups, retention/deletion controls, privacy terms, and a managed database.
- Session tokens are bearer tokens stored in browser localStorage for this starter; move to secure HttpOnly cookies before public launch.
- Do not use real candidate assessments as the sole basis for hiring decisions. Scores are coaching feedback, not validated employment tests.
- The portal does not record audio or video. Answers are typed.
- No employer job posting or application submission is connected.
