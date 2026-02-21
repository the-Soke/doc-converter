# Doc Converter

Full-stack document formatter app.

## Includes

- Next.js dashboard in `src/app/page.jsx`
- FastAPI backend in `api_server.py`
- Extraction pipeline in `doc_formatter.py`
- Reconstruction pipeline in `doc_reconstructor.py`
- Word export in `doc_to_word.py`

## Run frontend (local)

```bash
npm install
npm run dev
```

## Run backend (local)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api_server:app --host 127.0.0.1 --port 8000
```

## Vercel setup (important)

This frontend needs a separately hosted Python backend.

1. Deploy `api_server.py` on a Python host (Render/Railway/Fly/VPS).
2. In Vercel project settings, add env var:
   - `NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain`
3. Redeploy Vercel.
4. Verify backend health endpoint:
   - `https://your-backend-domain/api/health`

Without this env var and backend URL, the app will show backend configuration errors.
