from collections import Counter
from enum import StrEnum

from invoice_extraction.schema import Invoice

FIELDS_COMPARED_WITHOUT_SPACES = frozenset(
    {"supplier_company_id", "supplier_vat_id", "variable_symbol"}
)


class Outcome(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    MISSING = "missing"


def normalise_field_value(field_name: str, value: object) -> object:
    if isinstance(value, list):
        return Counter(value) or None

    if isinstance(value, str):
        separator = "" if field_name in FIELDS_COMPARED_WITHOUT_SPACES else " "
        return separator.join(value.split()) or None

    return value


def compare_invoices(
    expected_invoice: Invoice, extracted_invoice: Invoice
) -> dict[str, Outcome]:
    outcomes = {}

    for field_name in Invoice.model_fields:
        expected_value = normalise_field_value(
            field_name, getattr(expected_invoice, field_name)
        )
        extracted_value = normalise_field_value(
            field_name, getattr(extracted_invoice, field_name)
        )

        if extracted_value == expected_value:
            outcomes[field_name] = Outcome.CORRECT
        elif extracted_value is None:
            outcomes[field_name] = Outcome.MISSING
        else:
            outcomes[field_name] = Outcome.WRONG

    return outcomes


def find_disagreeing_fields(first_read: Invoice, second_read: Invoice) -> list[str]:
    return [
        field_name
        for field_name in Invoice.model_fields
        if normalise_field_value(field_name, getattr(first_read, field_name))
        != normalise_field_value(field_name, getattr(second_read, field_name))
    ]
