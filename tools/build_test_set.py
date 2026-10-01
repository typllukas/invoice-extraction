import base64
import io
import json
import random
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Any

import pypdfium2
from PIL import Image, ImageFilter

from invoice_extraction.evaluation import TEST_SET_DIRECTORY
from invoice_extraction.schema import Invoice, VatLine

# invoice-book counts demo dates back from its load day, so a rebuild changes this set
INVOICE_BOOK_URL = "http://localhost:8082"
RENDER_DOTS_PER_INCH = 150
INVOICE_NUMBERS = (
    "2026-000236",
    "2026-000237",
    "2026-000238",
    "2025-000001",
    "2025-000002",
    "2026-000016",
    "2026-000231",
    "2026-000036",
    "2026-000120",
    "2026-000183",
)


@dataclass(frozen=True)
class Degradation:
    scale: float
    angle: float
    blur_radius: float
    noise_percent: int
    jpeg_quality: int


DEGRADATIONS = {
    "mild": Degradation(
        scale=0.67, angle=1.5, blur_radius=0.6, noise_percent=6, jpeg_quality=45
    ),
    "poor": Degradation(
        scale=0.50, angle=3.0, blur_radius=0.95, noise_percent=12, jpeg_quality=24
    ),
    "harsh": Degradation(
        scale=0.45, angle=4.0, blur_radius=1.1, noise_percent=14, jpeg_quality=18
    ),
}


def fetch_resource(path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        INVOICE_BOOK_URL + path, headers={"Accept": "application/ld+json"}
    )

    with urllib.request.urlopen(request) as response:
        resource: dict[str, Any] = json.load(response)

    return resource


def find_invoice_paths() -> dict[str, str]:
    invoice_paths: dict[str, str] = {}
    page_number = 1
    members = fetch_resource(f"/api/invoices?page={page_number}")["member"]

    while members:
        for member in members:
            if member["number"] is not None:
                invoice_paths[member["number"]] = member["@id"]

        page_number += 1
        members = fetch_resource(f"/api/invoices?page={page_number}")["member"]

    return invoice_paths


def build_expected_invoice(resource: dict[str, Any]) -> Invoice:
    return Invoice(
        supplier_name=resource["supplierName"],
        supplier_company_id=resource["supplierCompanyId"],
        supplier_vat_id=resource["supplierVatId"],
        invoice_number=resource["number"],
        variable_symbol=resource["variableSymbol"],
        issue_date=resource["issuedAt"],
        tax_point_date=resource["taxPointAt"],
        due_date=resource["dueAt"],
        vat_lines=[
            VatLine(
                vat_rate_percent=int(summary_line["vatRate"]),
                net_amount=summary_line["netAmount"],
                vat_amount=summary_line["vatAmount"],
            )
            for summary_line in resource["vatSummary"]
        ],
        total_gross_amount=resource["totalGrossAmount"],
        currency="CZK",
    )


def render_first_page(pdf_content: bytes) -> Image.Image:
    page = pypdfium2.PdfDocument(pdf_content)[0]
    rendered_image: Image.Image = page.render(scale=RENDER_DOTS_PER_INCH / 72).to_pil()

    return rendered_image.convert("RGB")


def degrade_image(
    image: Image.Image, degradation: Degradation, noise_seed: int
) -> bytes:
    scan = image.convert("L")
    scaled_size = (
        round(scan.width * degradation.scale),
        round(scan.height * degradation.scale),
    )
    scan = scan.resize(scaled_size, Image.Resampling.BICUBIC)
    scan = scan.rotate(
        degradation.angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=255,
    )
    scan = scan.filter(ImageFilter.GaussianBlur(degradation.blur_radius))
    noise_content = random.Random(noise_seed).randbytes(scan.width * scan.height)
    noise = Image.frombytes("L", scan.size, noise_content)
    scan = Image.blend(scan, noise, degradation.noise_percent / 100)
    jpeg_buffer = io.BytesIO()
    scan.save(jpeg_buffer, "JPEG", quality=degradation.jpeg_quality)

    return jpeg_buffer.getvalue()


def write_test_set_file(relative_path: str, content: bytes) -> None:
    file_path = TEST_SET_DIRECTORY / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)


def main() -> None:
    invoice_paths = find_invoice_paths()

    for invoice_number in INVOICE_NUMBERS:
        invoice_path = invoice_paths[invoice_number]
        expected_invoice = build_expected_invoice(fetch_resource(invoice_path))
        pdf_resource = fetch_resource(f"{invoice_path}/pdf")
        pdf_content = base64.b64decode(pdf_resource["base64Content"])
        clean_image = render_first_page(pdf_content)
        clean_png_buffer = io.BytesIO()
        clean_image.save(clean_png_buffer, "PNG", optimize=True)

        write_test_set_file(
            f"expected-invoices/{invoice_number}.json",
            expected_invoice.model_dump_json(indent=2).encode(),
        )
        write_test_set_file(f"pdfs/{invoice_number}.pdf", pdf_content)
        write_test_set_file(
            f"images/clean/{invoice_number}.png", clean_png_buffer.getvalue()
        )

        for quality, degradation in DEGRADATIONS.items():
            noise_seed = zlib.crc32(f"{invoice_number}/{quality}".encode())
            write_test_set_file(
                f"images/{quality}/{invoice_number}.jpg",
                degrade_image(clean_image, degradation, noise_seed),
            )

        print(f"{invoice_number}: built")


if __name__ == "__main__":
    main()
