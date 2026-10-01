import argparse
import os
import pathlib
import sys

import anthropic

from invoice_extraction.extraction import (
    MEDIA_TYPE_BY_SUFFIX,
    ExtractionError,
    extract_invoice,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the data of one invoice from a PDF, PNG or JPEG."
    )
    parser.add_argument("document_path", type=pathlib.Path)
    document_path: pathlib.Path = parser.parse_args().document_path
    media_type = MEDIA_TYPE_BY_SUFFIX.get(document_path.suffix.lower())

    if media_type is None:
        supported_suffixes = ", ".join(MEDIA_TYPE_BY_SUFFIX)
        sys.exit(
            f"{document_path.name}: unsupported file type, "
            f"expected one of {supported_suffixes}"
        )

    if not document_path.is_file():
        sys.exit(f"{document_path}: no such file")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set; copy .env.dist to .env and put the key there"
        )

    try:
        extraction = extract_invoice(
            anthropic.Anthropic(), document_path.read_bytes(), media_type
        )
    except (anthropic.APIError, ExtractionError) as error:
        sys.exit(f"extraction failed: {error}")

    print(extraction.model_dump_json(indent=2))
