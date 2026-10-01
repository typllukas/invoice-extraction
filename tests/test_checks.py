import pytest

from invoice_extraction.checks import calculate_vat_amount, find_failed_checks
from invoice_extraction.schema import VatLine
from tests.invoices import CORRECT_INVOICE, STANDARD_RATE_LINE, copy_correct_invoice


@pytest.mark.parametrize(
    ("net_amount", "vat_rate_percent", "expected_vat_amount"),
    [
        (2424300, 12, 290916),
        (50, 21, 11),
        (4, 12, 0),
        (5, 12, 1),
        (100000, 0, 0),
        (-150, 21, -32),
    ],
)
def test_vat_amount_is_rounded_half_away_from_zero(
    net_amount: int, vat_rate_percent: int, expected_vat_amount: int
) -> None:
    assert calculate_vat_amount(net_amount, vat_rate_percent) == expected_vat_amount


def test_correct_invoice_fails_no_check() -> None:
    assert find_failed_checks(CORRECT_INVOICE) == []


def test_misread_vat_amount_is_reported() -> None:
    misread_line = VatLine(vat_rate_percent=12, net_amount=2424300, vat_amount=290918)
    invoice = copy_correct_invoice(vat_lines=[STANDARD_RATE_LINE, misread_line])

    failed_checks = find_failed_checks(invoice)

    assert len(failed_checks) == 2
    assert "12 %" in failed_checks[0]
    assert "290918" in failed_checks[0]
    assert "total" in failed_checks[1]


def test_misread_total_is_reported() -> None:
    invoice = copy_correct_invoice(total_gross_amount=3441210)

    assert len(find_failed_checks(invoice)) == 1


def test_rule_with_a_missing_value_is_skipped() -> None:
    unreadable_line = VatLine(vat_rate_percent=12, net_amount=None, vat_amount=290916)
    invoice = copy_correct_invoice(vat_lines=[STANDARD_RATE_LINE, unreadable_line])

    assert find_failed_checks(invoice) == []


@pytest.mark.parametrize(
    "absent_vat_lines", [pytest.param(None, id="none"), pytest.param([], id="empty")]
)
def test_absent_vat_lines_fail_no_check(absent_vat_lines: list[VatLine] | None) -> None:
    invoice = copy_correct_invoice(vat_lines=absent_vat_lines)

    assert find_failed_checks(invoice) == []


@pytest.mark.parametrize(
    "company_id", ["87654326", "25596641", "00006947", "27082440", "45274649"]
)
def test_valid_company_id_fails_no_check(company_id: str) -> None:
    invoice = copy_correct_invoice(
        supplier_company_id=company_id, supplier_vat_id=f"CZ{company_id}"
    )

    assert find_failed_checks(invoice) == []


@pytest.mark.parametrize(
    "misread_company_id", ["87654321", "87054326", "78654326", "8765432"]
)
def test_misread_company_id_is_reported(misread_company_id: str) -> None:
    invoice = copy_correct_invoice(
        supplier_company_id=misread_company_id, supplier_vat_id=None
    )

    failed_checks = find_failed_checks(invoice)

    assert len(failed_checks) == 1
    assert misread_company_id in failed_checks[0]


def test_company_id_printed_with_spaces_fails_no_check() -> None:
    invoice = copy_correct_invoice(supplier_company_id="876 54 326")

    assert find_failed_checks(invoice) == []


def test_vat_id_not_matching_company_id_is_reported() -> None:
    invoice = copy_correct_invoice(supplier_vat_id="CZ87654328")

    failed_checks = find_failed_checks(invoice)

    assert len(failed_checks) == 1
    assert "CZ87654328" in failed_checks[0]
    assert "87654326" in failed_checks[0]


@pytest.mark.parametrize(
    ("vat_id", "expected_failed_check_count"),
    [("CZ87654326", 0), ("CZ87654321", 1)],
)
def test_vat_id_alone_is_checked_against_the_check_digit(
    vat_id: str, expected_failed_check_count: int
) -> None:
    invoice = copy_correct_invoice(supplier_company_id=None, supplier_vat_id=vat_id)

    assert len(find_failed_checks(invoice)) == expected_failed_check_count


@pytest.mark.parametrize("vat_id", ["CZ7103192745", "CZ699001234", "DE123456789"])
def test_vat_id_of_a_person_or_another_country_is_not_checked(vat_id: str) -> None:
    invoice = copy_correct_invoice(supplier_vat_id=vat_id)

    assert find_failed_checks(invoice) == []


@pytest.mark.parametrize("misread_vat_id", ["C287654326", "87654326", "CZ8765432A"])
def test_vat_id_not_in_the_form_of_a_vat_id_is_reported(misread_vat_id: str) -> None:
    invoice = copy_correct_invoice(supplier_vat_id=misread_vat_id)

    failed_checks = find_failed_checks(invoice)

    assert len(failed_checks) == 1
    assert misread_vat_id in failed_checks[0]


def test_company_id_of_other_than_eight_digits_is_reported_as_such() -> None:
    invoice = copy_correct_invoice(supplier_company_id="6947", supplier_vat_id=None)

    assert find_failed_checks(invoice) == ["IČO 6947 is not eight digits"]
