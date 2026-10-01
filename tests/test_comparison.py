import datetime

from invoice_extraction.comparison import (
    Outcome,
    compare_invoices,
    find_disagreeing_fields,
)
from invoice_extraction.schema import Invoice, VatLine
from tests.invoices import (
    CORRECT_INVOICE,
    EMPTY_INVOICE,
    REDUCED_RATE_LINE,
    STANDARD_RATE_LINE,
    copy_correct_invoice,
)


def test_correct_values_score_all_correct() -> None:
    assert compare_invoices(CORRECT_INVOICE, CORRECT_INVOICE) == dict.fromkeys(
        Invoice.model_fields, Outcome.CORRECT
    )


def test_empty_answer_scores_all_missing() -> None:
    assert compare_invoices(CORRECT_INVOICE, EMPTY_INVOICE) == dict.fromkeys(
        Invoice.model_fields, Outcome.MISSING
    )


def test_absent_value_is_correct_when_none_is_expected() -> None:
    expected_invoice = copy_correct_invoice(supplier_vat_id=None)

    outcomes = compare_invoices(expected_invoice, EMPTY_INVOICE)

    assert outcomes["supplier_vat_id"] is Outcome.CORRECT


def test_invented_value_is_wrong_when_none_is_expected() -> None:
    expected_invoice = copy_correct_invoice(supplier_vat_id=None)

    outcomes = compare_invoices(expected_invoice, CORRECT_INVOICE)

    assert outcomes["supplier_vat_id"] is Outcome.WRONG


def test_wrong_date_is_wrong_and_leaves_the_other_fields_correct() -> None:
    extracted_invoice = copy_correct_invoice(due_date=CORRECT_INVOICE.issue_date)

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes == dict.fromkeys(Invoice.model_fields, Outcome.CORRECT) | {
        "due_date": Outcome.WRONG
    }


def test_spacing_of_text_is_normalised() -> None:
    extracted_invoice = copy_correct_invoice(
        supplier_name=" Vzorová  dodavatelská s.r.o. ",
        supplier_vat_id="CZ 87654326",
    )

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["supplier_name"] is Outcome.CORRECT
    assert outcomes["supplier_vat_id"] is Outcome.CORRECT


def test_name_with_two_words_joined_is_wrong() -> None:
    extracted_invoice = copy_correct_invoice(supplier_name="Vzorovádodavatelská s.r.o.")

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["supplier_name"] is Outcome.WRONG


def test_vat_lines_match_in_any_order() -> None:
    extracted_invoice = copy_correct_invoice(
        vat_lines=[REDUCED_RATE_LINE, STANDARD_RATE_LINE]
    )

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["vat_lines"] is Outcome.CORRECT


def test_one_misread_vat_line_makes_all_vat_lines_wrong() -> None:
    misread_line = VatLine(vat_rate_percent=21, net_amount=600000, vat_amount=126001)
    extracted_invoice = copy_correct_invoice(
        vat_lines=[REDUCED_RATE_LINE, misread_line]
    )

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["vat_lines"] is Outcome.WRONG


def test_repeated_vat_line_is_wrong() -> None:
    extracted_invoice = copy_correct_invoice(
        vat_lines=[STANDARD_RATE_LINE, STANDARD_RATE_LINE, REDUCED_RATE_LINE]
    )

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["vat_lines"] is Outcome.WRONG


def test_identical_reads_agree() -> None:
    assert find_disagreeing_fields(CORRECT_INVOICE, CORRECT_INVOICE) == []


def test_reads_differing_in_a_date_disagree_on_it() -> None:
    second_read = copy_correct_invoice(due_date=datetime.date(2026, 10, 15))

    assert find_disagreeing_fields(CORRECT_INVOICE, second_read) == ["due_date"]


def test_value_against_missing_is_a_disagreement() -> None:
    assert find_disagreeing_fields(CORRECT_INVOICE, EMPTY_INVOICE) == list(
        Invoice.model_fields
    )


def test_reads_differing_only_in_form_agree() -> None:
    second_read = copy_correct_invoice(
        supplier_company_id="876 54 326",
        vat_lines=[REDUCED_RATE_LINE, STANDARD_RATE_LINE],
    )

    assert find_disagreeing_fields(CORRECT_INVOICE, second_read) == []


def test_blank_text_and_empty_vat_lines_are_missing() -> None:
    extracted_invoice = copy_correct_invoice(supplier_name=" ", vat_lines=[])

    outcomes = compare_invoices(CORRECT_INVOICE, extracted_invoice)

    assert outcomes["supplier_name"] is Outcome.MISSING
    assert outcomes["vat_lines"] is Outcome.MISSING
