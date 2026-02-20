# Doc Converter

Full-stack document formatter app.

## Includes

- Next.js dashboard in `src/app/page.tsx`
- FastAPI backend in `api_server.py`
- Extraction pipeline in `doc_formatter.py`
- Reconstruction pipeline in `doc_reconstructor.py`
- Word export in `doc_to_word.py`

## Run frontend

```bash
npm install
npm run dev
```

## Run backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Set API URL for frontend:

- copy `.env.example` to `.env.local`
- default value: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`
