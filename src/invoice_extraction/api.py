import os
from typing import Annotated

import anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile, status

from invoice_extraction.extraction import (
    Extraction,
    ExtractionError,
    extract_invoice,
    is_supported_media_type,
)

app = FastAPI(title="Invoice extraction")


@app.post("/extract")
def extract(file: Annotated[UploadFile, File()]) -> Extraction:
    """Extract the data of one invoice from a PDF, PNG or JPEG and check it."""
    media_type = (file.content_type or "").split(";")[0].strip().lower()

    if not is_supported_media_type(media_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported media type {file.content_type}",
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not set",
        )

    try:
        return extract_invoice(anthropic.Anthropic(), file.file.read(), media_type)
    except (anthropic.APIError, ExtractionError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
        ) from error
