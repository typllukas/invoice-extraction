import re

from invoice_extraction.schema import Invoice

COMPANY_ID_PATTERN = re.compile(r"\d{8}")
VAT_ID_PATTERN = re.compile(r"[A-Z]{2}[0-9A-Z]{2,13}")
CZECH_VAT_ID_PATTERN = re.compile(r"CZ\d{8,10}")
CZECH_COMPANY_VAT_ID_PATTERN = re.compile(r"CZ(\d{8})")


def calculate_vat_amount(net_amount: int, vat_rate_percent: int) -> int:
    absolute_vat_amount = (abs(net_amount) * vat_rate_percent * 2 + 100) // 200

    return absolute_vat_amount if net_amount >= 0 else -absolute_vat_amount


def find_failed_vat_checks(invoice: Invoice) -> list[str]:
    if not invoice.vat_lines:
        return []

    failed_checks = []
    vat_line_gross_amounts = []

    for vat_line in invoice.vat_lines:
        if (
            vat_line.vat_rate_percent is None
            or vat_line.net_amount is None
            or vat_line.vat_amount is None
        ):
            continue

        vat_line_gross_amounts.append(vat_line.net_amount + vat_line.vat_amount)
        expected_vat_amount = calculate_vat_amount(
            vat_line.net_amount, vat_line.vat_rate_percent
        )

        if vat_line.vat_amount != expected_vat_amount:
            failed_checks.append(
                f"VAT line {vat_line.vat_rate_percent} %: "
                f"VAT {vat_line.vat_amount} is not {expected_vat_amount}, "
                f"which is {vat_line.vat_rate_percent} % "
                f"of the base {vat_line.net_amount}"
            )

    every_vat_line_is_complete = len(vat_line_gross_amounts) == len(invoice.vat_lines)

    if (
        invoice.total_gross_amount is not None
        and every_vat_line_is_complete
        and sum(vat_line_gross_amounts) != invoice.total_gross_amount
    ):
        failed_checks.append(
            f"total {invoice.total_gross_amount} is not {sum(vat_line_gross_amounts)}, "
            "the sum of the VAT lines"
        )

    return failed_checks


def has_valid_check_digit(company_id: str) -> bool:
    if COMPANY_ID_PATTERN.fullmatch(company_id) is None:
        return False

    weighted_sum = sum(
        int(digit) * weight
        for digit, weight in zip(company_id[:7], range(8, 1, -1), strict=True)
    )

    return (11 - weighted_sum % 11) % 10 == int(company_id[7])


def find_failed_identifier_checks(invoice: Invoice) -> list[str]:
    failed_checks = []
    company_id = (
        "".join(invoice.supplier_company_id.split())
        if invoice.supplier_company_id is not None
        else None
    )

    if company_id is not None and COMPANY_ID_PATTERN.fullmatch(company_id) is None:
        failed_checks.append(f"IČO {company_id} is not eight digits")
    elif company_id is not None and not has_valid_check_digit(company_id):
        failed_checks.append(f"IČO {company_id} fails its check digit")

    if invoice.supplier_vat_id is None:
        return failed_checks

    vat_id = "".join(invoice.supplier_vat_id.split())

    if VAT_ID_PATTERN.fullmatch(vat_id) is None or (
        vat_id.startswith("CZ") and CZECH_VAT_ID_PATTERN.fullmatch(vat_id) is None
    ):
        failed_checks.append(f"DIČ {vat_id} is not in the form of a VAT number")
        return failed_checks

    company_vat_id_match = CZECH_COMPANY_VAT_ID_PATTERN.fullmatch(vat_id)

    if company_vat_id_match is None:
        return failed_checks

    if company_id is None:
        if not has_valid_check_digit(company_vat_id_match[1]):
            failed_checks.append(f"DIČ {vat_id} fails its check digit")
    elif company_vat_id_match[1] != company_id:
        failed_checks.append(f"DIČ {vat_id} does not match IČO {company_id}")

    return failed_checks


def find_failed_checks(invoice: Invoice) -> list[str]:
    return find_failed_vat_checks(invoice) + find_failed_identifier_checks(invoice)
