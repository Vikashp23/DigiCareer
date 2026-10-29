# DigiCareer AI Interview Portal

DigiCareer is a starter full-stack app for registration/sign-in, role-based AI interview practice, answer feedback, and saved interview history. The AI provider is now Google Gemini.

## Important: where the working website lives

GitHub Pages only hosts static files and cannot run the Python API. The registration form calls `/api/register`, so open the running FastAPI service URL on Render, not the GitHub Pages URL.

## Deploy on Render

1. Open Render and connect the GitHub repository `Vikashp23/DigiCareer`.
2. Use the existing web service or create a Blueprint from `render.yaml`.
3. In Render → DigiCareer → Environment, add:
   - `AI_PROVIDER` = `gemini`
   - `GEMINI_API_KEY` = your secret key from Google AI Studio
   - `GEMINI_MODEL` = `gemini-2.5-flash`
4. Remove or ignore the old `OPENAI_API_KEY` variable; the Gemini integration does not use it.
5. Save changes and wait for the deployment to finish.
6. Open the Render service URL and visit `/api/health`. It should return JSON with `ok: true`. Confirm `ai_configured` is true.
7. Register/sign in on the Render URL and test an interview.

Google AI Studio API keys are private credentials. Never commit a real key to GitHub or paste it into chat. Free-tier model access and quotas can vary by account and model. Check the current Gemini API pricing and rate limits before relying on free usage.

## Run locally on Windows

1. Install Python 3.10 or newer.
2. Extract/clone this repository and open PowerShell in the project folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Never commit `.env`.
5. Start the server:
   ```powershell
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```
6. Open http://127.0.0.1:8000.

## Included files

- `index.html` — frontend and registration form
- `main.py` — FastAPI backend and Gemini integration
- `requirements.txt` — Python dependencies
- `.env.example` — safe configuration template (no real key)
- `render.yaml` — Render deployment configuration

## Persistence and production readiness

Render free web services can sleep after inactivity and local filesystem storage is not persistent. This starter stores accounts and history in SQLite, so data may be lost when the instance is replaced. Use a managed database before relying on it for real users. This demo is not production-audited.

Before public launch, add secure HttpOnly cookie sessions, rate limiting, email verification, password reset, abuse controls, database backups, retention/deletion controls, and a privacy notice. Scores are practice feedback, not validated employment tests. Do not use them as the sole basis for hiring decisions. The portal does not record audio/video or submit real job applications.
