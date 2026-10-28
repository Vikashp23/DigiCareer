# DigiCareer AI Interview Portal

DigiCareer is a starter full-stack app for registration/sign-in, role-based AI interview practice, answer feedback, and saved interview history.

## Important: where the working website lives

GitHub Pages only hosts static files and cannot run the Python API. The registration form calls `/api/register`, so it must be opened from the running FastAPI web service, not the GitHub Pages URL.

This repository includes `render.yaml` to make deployment to Render easier. After deployment, open the Render service URL (for example, `https://your-service.onrender.com`) to register and practise. The GitHub Pages address will not register users unless it is separately configured to call a deployed API.

## Deploy on Render

1. Open [Render](https://render.com/) and sign in.
2. Choose **New → Blueprint** and connect the GitHub repository `Vikashp23/DigiCareer`.
3. Render reads `render.yaml` and prepares a Python web service. Review the configuration and create/deploy it.
4. After the service is created, open its **Environment** page and add:
   - Key: `OPENAI_API_KEY`
   - Value: your OpenAI API key
5. Keep `OPENAI_MODEL` set to `gpt-4.1-mini` initially, and verify that this model is available to your API account. Change it to a model your account can access if needed.
6. Wait for deployment to finish, then open the service's `onrender.com` URL.
7. Test `https://YOUR-SERVICE.onrender.com/api/health`. It should return JSON with `"ok": true`. After adding the key, `"ai_configured"` should be `true`.
8. Register an account on the Render service URL. The AI interview itself requires a valid API key and API billing; ChatGPT subscriptions and API billing are separate.

Render's free web services can sleep after inactivity and their local filesystem is not persistent. This starter stores accounts and history in SQLite, so use a persistent disk or a managed database before relying on it for real users. It is a demo, not production-audited.

## Run locally on Windows

1. Install Python 3.10 or newer.
2. Extract/clone this repository and open PowerShell in the project folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and add your API key. Never commit `.env`.
5. Start the server:
   ```powershell
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```
6. Open http://127.0.0.1:8000.

## Included files

- `index.html` — frontend and registration form
- `main.py` — FastAPI backend and API endpoints
- `requirements.txt` — Python dependencies
- `.env.example` — safe configuration template (no real key)
- `render.yaml` — Render deployment configuration

## Before public launch

- Use HTTPS, secure HttpOnly cookies, rate limiting, email verification, password reset, abuse controls, database backups, retention/deletion controls, and a privacy notice.
- Do not commit a real `.env` file or API key.
- Scores are practice feedback, not validated employment tests. Do not use them as the sole basis for hiring decisions.
- The portal does not record audio/video or submit real job applications.
