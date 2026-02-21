from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
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

app = FastAPI(title="Document Formatter API", version="1.0.0")

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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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

        # FileResponse needs a stable path after this function returns,
        # so copy into a second NamedTemporaryFile managed by OS cleanup.
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
