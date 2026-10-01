import datetime

from invoice_extraction.schema import Invoice, VatLine

STANDARD_RATE_LINE = VatLine(vat_rate_percent=21, net_amount=600000, vat_amount=126000)
REDUCED_RATE_LINE = VatLine(vat_rate_percent=12, net_amount=2424300, vat_amount=290916)

CORRECT_INVOICE = Invoice(
    supplier_name="Vzorová dodavatelská s.r.o.",
    supplier_company_id="87654326",
    supplier_vat_id="CZ87654326",
    invoice_number="2026-000236",
    variable_symbol="2026000236",
    issue_date=datetime.date(2026, 10, 1),
    tax_point_date=datetime.date(2026, 9, 29),
    due_date=datetime.date(2026, 10, 13),
    vat_lines=[STANDARD_RATE_LINE, REDUCED_RATE_LINE],
    total_gross_amount=3441216,
    currency="CZK",
)

EMPTY_INVOICE = Invoice(
    supplier_name=None,
    supplier_company_id=None,
    supplier_vat_id=None,
    invoice_number=None,
    variable_symbol=None,
    issue_date=None,
    tax_point_date=None,
    due_date=None,
    vat_lines=None,
    total_gross_amount=None,
    currency=None,
)


def copy_correct_invoice(**changes: object) -> Invoice:
    # model_copy does not validate, a misspelt field would pass silently
    return Invoice.model_validate(CORRECT_INVOICE.model_dump() | changes)
