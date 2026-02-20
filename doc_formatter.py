"""
doc_extractor.py
================
Python tool that:
  1. Parses an 'ordinary text' file and a 'template' file into Markdown via Docling.
  2. Uses LangChain + Groq (LLaMA 3.3 70B) to identify every data field in the
     template and extract the corresponding information from the ordinary text.
  3. Returns a JSON object whose keys are the template sections/fields and
     whose values are the extracted text (or null when not found).

Usage
-----
    python doc_extractor.py \
        --ordinary-file  path/to/ordinary.pdf \
        --template-file  path/to/template.pdf \
        [--output        results.json]

Supported input formats (anything Docling handles):
    PDF, DOCX, PPTX, XLSX, HTML, images, plain-text, ...

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
from langchain_core.output_parsers import JsonOutputParser
from langchain_groq import ChatGroq

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1.  Docling helpers
# -----------------------------------------------------------------------------

def parse_to_markdown(file_path: str | Path) -> str:
    """
    Convert any Docling-supported file to a Markdown string.
    Docling automatically handles layout analysis, table reconstruction,
    OCR (if needed), and Markdown serialisation.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    log.info("Parsing '%s' with Docling ...", path.name)
    converter = DocumentConverter()
    result = converter.convert(str(path))
    markdown = result.document.export_to_markdown()
    log.info("  -> %d characters of Markdown", len(markdown))
    return markdown


# -----------------------------------------------------------------------------
# 2.  LangChain chain
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a precise data-extraction assistant.

You will receive:
  * TEMPLATE MARKDOWN  - a structured document that defines the data fields \
that must be filled in (sections, labels, placeholders, blank lines, etc.).
  * ORDINARY TEXT MARKDOWN - a source document that contains the actual \
information.

Your job:
  1. Identify EVERY distinct data field / section / placeholder present in \
the template.
  2. For each field, search the ordinary text and extract the most relevant \
value.
  3. Return ONLY a single valid JSON object:
       {{
         "<field_name_from_template>": "<extracted_value_or_null>",
         ...
       }}
     * Keys   -> the field names / section headings as they appear in the \
template (normalised: lowercase, underscores instead of spaces).
     * Values -> the extracted text snippet, or JSON null if the information \
is not present in the ordinary text.
  4. Do NOT include any explanation, markdown fences, or extra text - just the \
raw JSON object.
"""

USER_PROMPT = """\
=== TEMPLATE MARKDOWN ===
{template_markdown}

=== ORDINARY TEXT MARKDOWN ===
{ordinary_markdown}
"""


def build_extraction_chain(temperature: float = 0):
    """
    Build a LangChain LCEL chain:
        prompt -> ChatGroq (LLaMA 3.3 70B) -> JsonOutputParser
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

    # JsonOutputParser handles stripping markdown fences and parsing JSON.
    chain = prompt | llm | JsonOutputParser()
    return chain


# -----------------------------------------------------------------------------
# 3.  Main extraction function
# -----------------------------------------------------------------------------

def extract(
    ordinary_file: str | Path,
    template_file: str | Path,
    temperature: float = 0,
) -> dict:
    """
    Full pipeline:
      ordinary_file + template_file -> dict of extracted fields.
    """
    # Step 1 - parse both documents to Markdown
    ordinary_md = parse_to_markdown(ordinary_file)
    template_md = parse_to_markdown(template_file)

    # Step 2 - build and invoke LangChain chain
    log.info("Sending documents to Groq (LLaMA 3.3 70B) for field extraction ...")
    chain = build_extraction_chain(temperature=temperature)
    result: dict = chain.invoke(
        {
            "template_markdown": template_md,
            "ordinary_markdown": ordinary_md,
        }
    )
    log.info("Extraction complete - %d fields identified.", len(result))
    return result


# -----------------------------------------------------------------------------
# 4.  CLI entry-point
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract template fields from an ordinary document using "
                    "Docling + LangChain + Groq (free).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ordinary-file", required=True,
        help="Path to the source document (PDF, DOCX, TXT, ...).",
    )
    parser.add_argument(
        "--template-file", required=True,
        help="Path to the template document that defines the fields.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Optional path to write the JSON result. "
             "Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--temperature", type=float, default=0,
        help="LLM temperature (default: 0 for deterministic output).",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()  # picks up GROQ_API_KEY from a .env file if present

    if not os.getenv("GROQ_API_KEY"):
        log.error(
            "GROQ_API_KEY is not set.\n"
            "  1. Sign up free at https://console.groq.com\n"
            "  2. Create an API key\n"
            "  3. Add it to a .env file:  GROQ_API_KEY=gsk_...\n"
        )
        sys.exit(1)

    args = parse_args()

    extracted: dict = extract(
        ordinary_file=args.ordinary_file,
        template_file=args.template_file,
        temperature=args.temperature,
    )

    json_output = json.dumps(extracted, indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_output, encoding="utf-8")
        log.info("Results saved to '%s'.", output_path)
    else:
        print(json_output)


if __name__ == "__main__":
    main()