from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = FastAPI(title="Document Formatter API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FormatResponse(BaseModel):
    source_markdown: str
    template_markdown: str
    extracted_json: dict[str, Any]
    reconstructed_markdown: str


class ExportWordRequest(BaseModel):
    markdown_text: str
    extracted_json: dict[str, Any] | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    result: FormatResponse | None = None
    error: str | None = None


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _update_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)


def _run_format_job(
    job_id: str,
    source_bytes: bytes,
    source_name: str,
    template_bytes: bytes,
    template_name: str,
    temperature: float,
) -> None:
    _update_job(job_id, status="running", progress=5, message="Starting worker...")

    try:
        from doc_formatter import build_extraction_chain, parse_to_markdown as parse_source_markdown
        from doc_reconstructor import reconstruct
    except Exception as exc:
        log.exception("Backend import failed during async job")
        _update_job(
            job_id,
            status="failed",
            progress=100,
            message="Failed to import backend modules.",
            error=f"Backend import failed: {exc}",
        )
        return

    try:
        _update_job(job_id, progress=15, message="Preparing uploaded files...")
        with tempfile.TemporaryDirectory(prefix="docfmt_job_") as tmp:
            temp_dir = Path(tmp)
            source_path = temp_dir / (Path(source_name or "source").name)
            template_path = temp_dir / (Path(template_name or "template").name)
            source_path.write_bytes(source_bytes)
            template_path.write_bytes(template_bytes)

            _update_job(job_id, progress=30, message="Parsing source document...")
            source_markdown = parse_source_markdown(source_path)

            _update_job(job_id, progress=50, message="Parsing template document...")
            template_markdown = parse_source_markdown(template_path)

            _update_job(job_id, progress=70, message="Extracting fields with LLM...")
            chain = build_extraction_chain(temperature=temperature)
            extracted_json = chain.invoke(
                {
                    "template_markdown": template_markdown,
                    "ordinary_markdown": source_markdown,
                }
            )

            _update_job(job_id, progress=85, message="Reconstructing final markdown...")
            reconstructed_markdown = reconstruct(
                extracted_json=extracted_json,
                template_markdown=template_markdown,
                temperature=temperature,
            )

            result = FormatResponse(
                source_markdown=source_markdown,
                template_markdown=template_markdown,
                extracted_json=extracted_json,
                reconstructed_markdown=reconstructed_markdown,
            )
            _update_job(
                job_id,
                status="completed",
                progress=100,
                message="Processing complete.",
                result=result.model_dump(),
            )
    except Exception as exc:
        log.exception("Async formatting job failed: %s", job_id)
        _update_job(
            job_id,
            status="failed",
            progress=100,
            message="Processing failed.",
            error=str(exc),
        )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs/format", response_model=JobCreateResponse)
async def queue_format_job(
    background_tasks: BackgroundTasks,
    source_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    temperature: float = 0,
) -> JobCreateResponse:
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set.")

    source_bytes = await source_file.read()
    template_bytes = await template_file.read()
    if not source_bytes or not template_bytes:
        raise HTTPException(status_code=400, detail="Both source_file and template_file must be non-empty.")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Queued for processing.",
            "result": None,
            "error": None,
        }

    background_tasks.add_task(
        _run_format_job,
        job_id,
        source_bytes,
        source_file.filename or "source",
        template_bytes,
        template_file.filename or "template",
        temperature,
    )
    return JobCreateResponse(job_id=job_id, status="queued")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatusResponse(**job)


@app.post("/api/format", response_model=FormatResponse)
async def format_document(
    source_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
    temperature: float = 0,
) -> FormatResponse:
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set.")
    try:
        from doc_formatter import build_extraction_chain, parse_to_markdown as parse_source_markdown
        from doc_reconstructor import reconstruct
    except Exception as exc:
        log.exception("Backend import failed during /api/format")
        raise HTTPException(status_code=500, detail=f"Backend import failed: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="docfmt_") as tmp:
        temp_dir = Path(tmp)

        source_path = temp_dir / (Path(source_file.filename or "source").name)
        template_path = temp_dir / (Path(template_file.filename or "template").name)

        with source_path.open("wb") as f:
            shutil.copyfileobj(source_file.file, f)
        with template_path.open("wb") as f:
            shutil.copyfileobj(template_file.file, f)

        source_markdown = parse_source_markdown(source_path)
        template_markdown = parse_source_markdown(template_path)

        chain = build_extraction_chain(temperature=temperature)
        extracted_json = chain.invoke(
            {
                "template_markdown": template_markdown,
                "ordinary_markdown": source_markdown,
            }
        )

        reconstructed_markdown = reconstruct(
            extracted_json=extracted_json,
            template_markdown=template_markdown,
            temperature=temperature,
        )

    return FormatResponse(
        source_markdown=source_markdown,
        template_markdown=template_markdown,
        extracted_json=extracted_json,
        reconstructed_markdown=reconstructed_markdown,
    )


@app.post("/api/export/word")
def export_word(payload: ExportWordRequest):
    try:
        from doc_to_word import build_word_document
    except Exception as exc:
        log.exception("Backend import failed during /api/export/word")
        raise HTTPException(status_code=500, detail=f"Backend import failed: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="docfmt_word_") as tmp:
        output_path = Path(tmp) / "reconstructed.docx"
        build_word_document(
            markdown_text=payload.markdown_text,
            json_data=payload.extracted_json,
            output_path=output_path,
        )

        temp_docx = tempfile.NamedTemporaryFile(prefix="docfmt_", suffix=".docx", delete=False)
        temp_docx.close()
        shutil.copyfile(output_path, temp_docx.name)

    return FileResponse(
        path=temp_docx.name,
        filename="final.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api_server:app", host=host, port=port, reload=False)
