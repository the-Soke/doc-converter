"""
doc_reconstructor.py
====================
Takes the JSON output from doc_extractor.py and a Markdown representation
of the template, then uses LangChain + Groq (LLaMA 3.3 70B) to reconstruct
the document — placing the extracted content exactly within the template's
structure, preserving all headers, bullet points, and emphasis styles.

The output is valid, well-formed Markdown saved to a file.

Usage
-----
    # Reconstruct from JSON file + template PDF (Docling converts template):
    python doc_reconstructor.py \
        --json-file      result.json \
        --template-file  Resume.pdf \
        --output         reconstructed.md

    # Or supply the template as a pre-converted Markdown file:
    python doc_reconstructor.py \
        --json-file          result.json \
        --template-markdown  template.md \
        --output             reconstructed.md

Requirements
------------
    pip install docling langchain langchain-groq python-dotenv

Environment variable (or .env file):
    GROQ_API_KEY=gsk_...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# -- Docling ------------------------------------------------------------------
from docling.document_converter import DocumentConverter

# -- LangChain ----------------------------------------------------------------
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1.  Docling helper  (reused from doc_extractor.py)
# -----------------------------------------------------------------------------

def parse_to_markdown(file_path: str | Path) -> str:
    """Convert any Docling-supported file to a Markdown string."""
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    log.info("Parsing '%s' with Docling ...", path.name)
    converter = DocumentConverter()
    result = converter.convert(str(path))
    markdown = result.document.export_to_markdown()
    log.info("  -> %d characters of Markdown extracted", len(markdown))
    return markdown


# -----------------------------------------------------------------------------
# 2.  LangChain reconstruction chain
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert document formatter and Markdown specialist.

You will receive:
  * TEMPLATE MARKDOWN  - the skeleton document that defines the exact structure,
    layout, headers, bullet styles, bold/italic emphasis, and section order that
    the final document MUST follow.
  * EXTRACTED JSON     - a JSON object containing the field names (keys) and
    the real content to be inserted (values).

Your job:
  1. Use the TEMPLATE MARKDOWN as the EXACT structural blueprint.
     - Keep every heading level (# ## ### etc.) exactly as in the template.
     - Keep every bullet style (-, *, numbered) exactly as in the template.
     - Keep all bold (**text**), italic (*text*), and other emphasis exactly
       as in the template.
     - Keep all horizontal rules, blank lines between sections, and spacing
       patterns.
  2. Replace every placeholder / blank / example value in the template with
     the matching content from the EXTRACTED JSON.
     - Match fields by their semantic meaning, not just exact key name.
     - If a JSON value is null or missing, leave the template placeholder as
       an empty string or a tasteful placeholder like "[Not provided]".
  3. Do NOT add new sections, headings, or structure that is not in the template.
  4. Do NOT remove any sections from the template even if the JSON has no value
     for them.
  5. Output ONLY the final reconstructed Markdown document — no explanation,
     no preamble, no code fences wrapping the whole document.
"""

USER_PROMPT = """\
=== TEMPLATE MARKDOWN ===
{template_markdown}

=== EXTRACTED JSON ===
{extracted_json}
"""


def build_reconstruction_chain(temperature: float = 0):
    """
    Build a LangChain LCEL chain:
        prompt -> ChatGroq (LLaMA 3.3 70B) -> StrOutputParser

    StrOutputParser is used (not JsonOutputParser) because the output
    is a free-form Markdown document, not JSON.
    """
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", USER_PROMPT),
        ]
    )

    chain = prompt | llm | StrOutputParser()
    return chain


# -----------------------------------------------------------------------------
# 3.  Main reconstruction function
# -----------------------------------------------------------------------------

def reconstruct(
    extracted_json: dict,
    template_markdown: str,
    temperature: float = 0,
) -> str:
    """
    Core function.

    Parameters
    ----------
    extracted_json    : dict   — the JSON output from doc_extractor.py
    template_markdown : str    — Markdown string of the template document
    temperature       : float  — LLM temperature (default 0 = deterministic)

    Returns
    -------
    str — a valid, fully reconstructed Markdown document
    """
    log.info("Sending data to Groq for document reconstruction ...")

    chain = build_reconstruction_chain(temperature=temperature)

    result: str = chain.invoke(
        {
            "template_markdown": template_markdown,
            "extracted_json": json.dumps(extracted_json, indent=2, ensure_ascii=False),
        }
    )

    log.info("Reconstruction complete — %d characters of Markdown produced.", len(result))
    return result


# -----------------------------------------------------------------------------
# 4.  Convenience wrapper  (file-based)
# -----------------------------------------------------------------------------

def reconstruct_from_files(
    json_file: str | Path,
    template_source: str | Path,
    output_file: str | Path | None = None,
    temperature: float = 0,
) -> str:
    """
    High-level helper that:
      - Loads the JSON from a file produced by doc_extractor.py
      - Accepts either a raw document (PDF/DOCX/…) or a pre-converted .md file
        as the template source
      - Calls reconstruct()
      - Optionally writes the result to output_file
      - Always returns the Markdown string

    Parameters
    ----------
    json_file       : path to result.json from doc_extractor.py
    template_source : path to the template (PDF/DOCX/… or .md)
    output_file     : optional path to write the reconstructed Markdown
    temperature     : LLM temperature
    """
    # Load JSON
    json_path = Path(json_file).resolve()
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    log.info("Loading extracted JSON from '%s' ...", json_path.name)
    extracted = json.loads(json_path.read_text(encoding="utf-8"))

    # Load template Markdown
    template_path = Path(template_source).resolve()
    if template_path.suffix.lower() == ".md":
        log.info("Loading template Markdown from '%s' ...", template_path.name)
        template_md = template_path.read_text(encoding="utf-8")
    else:
        # Use Docling to convert PDF/DOCX/etc. → Markdown
        template_md = parse_to_markdown(template_path)

    # Reconstruct
    reconstructed_md = reconstruct(
        extracted_json=extracted,
        template_markdown=template_md,
        temperature=temperature,
    )

    # Save if requested
    if output_file:
        out_path = Path(output_file)
        out_path.write_text(reconstructed_md, encoding="utf-8")
        log.info("Reconstructed document saved to '%s'.", out_path)

    return reconstructed_md


# -----------------------------------------------------------------------------
# 5.  CLI entry-point
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstruct a document by merging extracted JSON into a "
                    "Markdown template using Groq (free).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--json-file", required=True,
        help="Path to the result.json produced by doc_extractor.py.",
    )

    # Template source — either a raw document OR a pre-converted .md file
    template_group = parser.add_mutually_exclusive_group(required=True)
    template_group.add_argument(
        "--template-file",
        help="Path to the original template document (PDF, DOCX, …). "
             "Docling will convert it to Markdown automatically.",
    )
    template_group.add_argument(
        "--template-markdown",
        help="Path to an already-converted template .md file "
             "(skips Docling conversion).",
    )

    parser.add_argument(
        "--output", default="reconstructed.md",
        help="Path to write the reconstructed Markdown (default: reconstructed.md).",
    )
    parser.add_argument(
        "--temperature", type=float, default=0,
        help="LLM temperature (default: 0).",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()

    if not os.getenv("GROQ_API_KEY"):
        log.error(
            "GROQ_API_KEY is not set.\n"
            "  1. Sign up free at https://console.groq.com\n"
            "  2. Create an API key\n"
            "  3. Add it to a .env file:  GROQ_API_KEY=gsk_...\n"
        )
        sys.exit(1)

    args = parse_args()

    template_source = args.template_file or args.template_markdown

    reconstruct_from_files(
        json_file=args.json_file,
        template_source=template_source,
        output_file=args.output,
        temperature=args.temperature,
    )

    log.info("Done! Open '%s' in VSCode to review the result.", args.output)


if __name__ == "__main__":
    main()
