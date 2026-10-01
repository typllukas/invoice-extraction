import base64
from typing import Literal, TypeIs

import anthropic
from anthropic.types import DocumentBlockParam, ImageBlockParam
from pydantic import BaseModel, ConfigDict, ValidationError

from invoice_extraction.checks import find_failed_checks
from invoice_extraction.schema import Invoice

MODEL = "claude-opus-5-5"
MAXIMUM_OUTPUT_TOKENS = 4000
INSTRUCTION = (
    "Extract the data of this Czech invoice. The supplier is the issuer (Dodavatel), "
    "never the customer (Odběratel). Amounts are whole haléře: 1 234,50 Kč is 123450. "
    "Return null for any value that is absent from the document or that you cannot "
    "read with confidence. Never guess."
)

MediaType = Literal["application/pdf", "image/png", "image/jpeg"]

MEDIA_TYPE_BY_SUFFIX: dict[str, MediaType] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class Extraction(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice: Invoice
    failed_checks: list[str]
    model: str
    input_tokens: int
    output_tokens: int


class ExtractionError(Exception):
    pass


def is_supported_media_type(content_type: str) -> TypeIs[MediaType]:
    return content_type in MEDIA_TYPE_BY_SUFFIX.values()


def build_document_block(
    document_content: bytes, media_type: MediaType
) -> DocumentBlockParam | ImageBlockParam:
    encoded_content = base64.standard_b64encode(document_content).decode()

    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded_content,
            },
        }

    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": encoded_content},
    }


def extract_invoice(
    client: anthropic.Anthropic, document_content: bytes, media_type: MediaType
) -> Extraction:
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAXIMUM_OUTPUT_TOKENS,
            output_config={"effort": "medium"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        build_document_block(document_content, media_type),
                        {"type": "text", "text": INSTRUCTION},
                    ],
                }
            ],
            output_format=Invoice,
        )
    except ValidationError as error:
        raise ExtractionError(
            "the model returned an answer that is not a complete invoice"
        ) from error

    if response.model != MODEL:
        raise ExtractionError(f"answered by {response.model}, not {MODEL}")

    if response.stop_reason != "end_turn" or response.parsed_output is None:
        raise ExtractionError(
            f"the model stopped with {response.stop_reason} and returned no invoice"
        )

    return Extraction(
        invoice=response.parsed_output,
        failed_checks=find_failed_checks(response.parsed_output),
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
