import argparse
import os
import pathlib
import sys
from collections.abc import Callable

import anthropic
from pydantic import BaseModel, ConfigDict, TypeAdapter

from invoice_extraction.checks import (
    find_failed_identifier_checks,
    find_failed_vat_checks,
)
from invoice_extraction.comparison import (
    Outcome,
    compare_invoices,
    find_disagreeing_fields,
)
from invoice_extraction.extraction import (
    MEDIA_TYPE_BY_SUFFIX,
    Extraction,
    ExtractionError,
    extract_invoice,
)
from invoice_extraction.schema import Invoice

TEST_SET_DIRECTORY = pathlib.Path("evaluation/test-set")
EXPECTED_INVOICES_DIRECTORY = TEST_SET_DIRECTORY / "expected-invoices"
QUALITIES = ("clean", "mild", "poor", "harsh")
AMOUNT_FIELDS = ("vat_lines", "total_gross_amount")
CHECK_DIGIT_FIELDS = ("supplier_company_id", "supplier_vat_id")
INPUT_USD_PER_MILLION_TOKENS = 4
OUTPUT_USD_PER_MILLION_TOKENS = 20


class ExtractedRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    invoice_number: str
    quality: str
    error: None
    outcomes: dict[str, Outcome]
    extraction: Extraction


class FailedRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    invoice_number: str
    quality: str
    error: str


ResultRow = ExtractedRow | FailedRow
RESULT_ROW_ADAPTER: TypeAdapter[ResultRow] = TypeAdapter(ResultRow)


def find_image_paths(qualities: tuple[str, ...]) -> list[pathlib.Path]:
    image_paths: list[pathlib.Path] = []

    for expected_path in sorted(EXPECTED_INVOICES_DIRECTORY.glob("*.json")):
        for quality in qualities:
            quality_directory = TEST_SET_DIRECTORY / "images" / quality
            image_paths.extend(
                image_path
                for image_path in sorted(
                    quality_directory.glob(f"{expected_path.stem}.*")
                )
                if image_path.suffix in MEDIA_TYPE_BY_SUFFIX
            )

    return image_paths


def evaluate_image(client: anthropic.Anthropic, image_path: pathlib.Path) -> ResultRow:
    expected_path = EXPECTED_INVOICES_DIRECTORY / f"{image_path.stem}.json"
    expected_invoice = Invoice.model_validate_json(expected_path.read_text())

    try:
        extraction = extract_invoice(
            client, image_path.read_bytes(), MEDIA_TYPE_BY_SUFFIX[image_path.suffix]
        )
    except (anthropic.APIError, ExtractionError) as error:
        return FailedRow(
            invoice_number=image_path.stem,
            quality=image_path.parent.name,
            error=str(error),
        )

    return ExtractedRow(
        invoice_number=image_path.stem,
        quality=image_path.parent.name,
        error=None,
        outcomes=compare_invoices(expected_invoice, extraction.invoice),
        extraction=extraction,
    )


def run_extractions(
    image_paths: list[pathlib.Path], results_path: pathlib.Path
) -> None:
    client = anthropic.Anthropic()
    results_path.parent.mkdir(parents=True, exist_ok=True)
    unfinished_results_path = results_path.with_suffix(".unfinished")

    with unfinished_results_path.open("w") as results_file:
        for image_path in image_paths:
            result_row = evaluate_image(client, image_path)
            results_file.write(result_row.model_dump_json() + "\n")
            results_file.flush()
            print(
                f"{result_row.quality:5} {result_row.invoice_number}: "
                f"{result_row.error or 'extracted'}"
            )

    unfinished_results_path.replace(results_path)


def format_check_summary(
    extracted_rows: list[ExtractedRow],
    checked_fields: tuple[str, ...],
    find_check_failures: Callable[[Invoice], list[str]],
    value_label: str,
    check_label: str,
) -> str:
    wrong_value_rows = [
        row
        for row in extracted_rows
        if any(
            row.outcomes[field_name] is Outcome.WRONG for field_name in checked_fields
        )
    ]
    flagged_rows = [
        row for row in extracted_rows if find_check_failures(row.extraction.invoice)
    ]
    flagged_wrong_value_rows = [row for row in flagged_rows if row in wrong_value_rows]

    return (
        f"extractions with a wrong {value_label}: {len(wrong_value_rows)}, "
        f"of which the {check_label} flagged {len(flagged_wrong_value_rows)}; "
        f"flagged without a wrong {value_label}: "
        f"{len(flagged_rows) - len(flagged_wrong_value_rows)}"
    )


def format_report(result_rows: list[ResultRow]) -> str:
    extracted_rows = [row for row in result_rows if isinstance(row, ExtractedRow)]
    report_lines = [
        f"{'field':20}" + "".join(f"{quality:>30}" for quality in QUALITIES)
    ]

    for field_name in Invoice.model_fields:
        report_line = f"{field_name:20}"

        for quality in QUALITIES:
            outcomes = [
                row.outcomes[field_name]
                for row in extracted_rows
                if row.quality == quality
            ]
            correct_count = outcomes.count(Outcome.CORRECT)
            wrong_count = outcomes.count(Outcome.WRONG)
            missing_count = outcomes.count(Outcome.MISSING)
            field_summary = (
                f"{correct_count}/{len(outcomes)} "
                f"({wrong_count} wrong, {missing_count} missing)"
            )
            report_line += f"{field_summary:>30}"

        report_lines.append(report_line)

    failed_calls_line = f"{'failed calls':20}"

    for quality in QUALITIES:
        failed_rows = [
            row
            for row in result_rows
            if row.quality == quality and isinstance(row, FailedRow)
        ]
        failed_calls_line += f"{len(failed_rows):>30}"

    report_lines.append(failed_calls_line)

    fully_correct_rows = [
        row for row in extracted_rows if set(row.outcomes.values()) == {Outcome.CORRECT}
    ]
    input_tokens = sum(row.extraction.input_tokens for row in extracted_rows)
    output_tokens = sum(row.extraction.output_tokens for row in extracted_rows)
    cost = (
        input_tokens * INPUT_USD_PER_MILLION_TOKENS
        + output_tokens * OUTPUT_USD_PER_MILLION_TOKENS
    ) / 1_000_000
    error_count = len(result_rows) - len(extracted_rows)

    report_lines += [
        "",
        f"images: {len(result_rows)}, extracted: {len(extracted_rows)}, "
        f"errors: {error_count}",
        "documents with every field correct: "
        f"{len(fully_correct_rows)}/{len(extracted_rows)}",
        format_check_summary(
            extracted_rows,
            AMOUNT_FIELDS,
            find_failed_vat_checks,
            "amount",
            "arithmetic check",
        ),
        format_check_summary(
            extracted_rows,
            CHECK_DIGIT_FIELDS,
            find_failed_identifier_checks,
            "IČO or DIČ",
            "check digits",
        ),
        f"tokens: {input_tokens} input, {output_tokens} output; "
        f"cost of the extracted images: {cost:.2f} USD",
    ]

    return "\n".join(report_lines)


def format_second_read_report(
    first_read_rows: list[ResultRow], second_read_rows: list[ResultRow]
) -> str:
    second_read_rows_by_image = {
        (row.invoice_number, row.quality): row
        for row in second_read_rows
        if isinstance(row, ExtractedRow)
    }
    summary_lines = ["second read:"]
    wrong_value_lines = []

    for quality in QUALITIES:
        compared_field_count = 0
        wrong_value_count = 0
        flagged_count = 0
        disagreement_without_wrong_value_count = 0

        for first_read_row in first_read_rows:
            second_read_row = second_read_rows_by_image.get(
                (first_read_row.invoice_number, first_read_row.quality)
            )

            if (
                first_read_row.quality != quality
                or not isinstance(first_read_row, ExtractedRow)
                or second_read_row is None
            ):
                continue

            first_read_invoice = first_read_row.extraction.invoice
            second_read_invoice = second_read_row.extraction.invoice
            disagreeing_fields = find_disagreeing_fields(
                first_read_invoice, second_read_invoice
            )
            first_read_values = first_read_invoice.model_dump(mode="json")
            second_read_values = second_read_invoice.model_dump(mode="json")

            for field_name in Invoice.model_fields:
                compared_field_count += 1
                is_flagged = field_name in disagreeing_fields
                read_outcomes = (
                    first_read_row.outcomes[field_name],
                    second_read_row.outcomes[field_name],
                )

                if Outcome.WRONG not in read_outcomes:
                    disagreement_without_wrong_value_count += is_flagged
                    continue

                wrong_value_count += 1
                flagged_count += is_flagged
                wrong_value_lines.append(
                    f"{quality:5} {first_read_row.invoice_number} {field_name}: "
                    f"{first_read_values[field_name]} / "
                    f"{second_read_values[field_name]}, "
                    f"{'flagged' if is_flagged else 'missed'}"
                )

        if compared_field_count:
            summary_lines.append(
                f"{quality}: {compared_field_count} fields compared, "
                f"{wrong_value_count} wrong in either read, "
                f"{flagged_count} of them flagged by disagreement; "
                f"disagreements with neither read wrong: "
                f"{disagreement_without_wrong_value_count}"
            )

    return "\n".join([*summary_lines, "", *wrong_value_lines])


def read_result_rows(results_path: pathlib.Path) -> list[ResultRow]:
    if not results_path.is_file():
        sys.exit(f"{results_path}: no results of a finished run")

    return [
        RESULT_ROW_ADAPTER.validate_json(line)
        for line in results_path.read_text().splitlines()
        if line.strip()
    ]


def parse_image_count(argument: str) -> int:
    image_count = int(argument)

    if image_count < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    return image_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure the extraction on the committed test set."
    )
    parser.add_argument(
        "--limit",
        type=parse_image_count,
        help="number of images, one paid call each; all of them when omitted",
    )
    parser.add_argument(
        "--quality",
        choices=QUALITIES,
        nargs="+",
        help="only the images of these qualities",
    )
    parser.add_argument(
        "--results", type=pathlib.Path, default=pathlib.Path("var/results.jsonl")
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="print the report of a finished run, no calls",
    )
    parser.add_argument(
        "--second-read",
        type=pathlib.Path,
        help="results of a second run over the same images, compared field by field",
    )
    arguments = parser.parse_args()

    if not arguments.report_only:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit(
                "ANTHROPIC_API_KEY is not set; "
                "copy .env.dist to .env and put the key there"
            )

        qualities = tuple(arguments.quality) if arguments.quality else QUALITIES
        image_paths = find_image_paths(qualities)[: arguments.limit]
        run_extractions(image_paths, arguments.results)

    result_rows = read_result_rows(arguments.results)
    print(format_report(result_rows))

    if arguments.second_read:
        print()
        print(
            format_second_read_report(
                result_rows, read_result_rows(arguments.second_read)
            )
        )
