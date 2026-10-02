# invoice-extraction

Reads a received Czech invoice with a multimodal model and checks the result in code. One call to
`claude-opus-5-5` per document through the Anthropic SDK, with the answer held to a Pydantic schema,
behind a command and a FastAPI endpoint. A prototype with a measurement, not a product. Python 3.13,
mypy strict, Ruff and pytest, all in Docker.

## Features

- **Extraction** of the supplier, IČO, DIČ, invoice number, variable symbol, dates, VAT
  recapitulation, total and currency from a PDF, PNG or JPEG
- **`null` instead of a guess.** Every field is nullable and the model is told to leave out what it
  cannot read
- **Checks in code**: the VAT arithmetic and the check digits of the IČO and DIČ. A failed check is
  reported beside the data and the value is never corrected
- **Measurement** of every field as correct, wrong or missing on forty committed images

## Running it

Requires Docker with the Compose plugin, Make and an Anthropic API key.

```bash
git clone https://github.com/typllukas/invoice-extraction.git
cd invoice-extraction
cp .env.dist .env    # put the key after ANTHROPIC_API_KEY=
make build
make extract FILE=evaluation/test-set/pdfs/2026-000236.pdf    # one paid call, about 2 cents
make report RESULTS=evaluation/results.jsonl                  # the measured figures again, free
make check                                                    # Ruff, mypy strict, pytest; no test calls the model
```

`make evaluate` repeats the measurement for about 0.82 USD. `make serve` starts the endpoint on
`http://127.0.0.1:8083/extract`; it has no authentication and pays for every request.

## Measured

On 1 October 2026: ten invoices, each at four image qualities, one read per image.

| Quality | What it is | Documents entirely correct |
|---|---|---|
| Clean | the PDF rendered at 150 DPI | 10/10 |
| Mild | an ordinary office scan | 10/10 |
| Poor | the worst scan a person can still read | 10/10 |
| Harsh | past what a person can read | 1/10 |

- **Harsh, missing**: 12 values came back `null`, which is the safe failure
- **Harsh, wrong**: 5 dates came back with one misread digit and no sign of doubt
- **Amounts** were right on all forty images, so the arithmetic check had nothing to catch
- **Cost**: 0.82 USD for the forty images, about two cents each

A second read of the poor and harsh images flagged four of the five wrong dates by disagreeing with
the first. A stricter instruction turned all five into `null` but blanked nineteen more values, so
it was rejected. All raw answers are in `evaluation/`.

## Free alternatives

Two were installed and run on the same test set. Their raw outputs are in
`evaluation/baselines/`.

- **Tesseract 5.5**, OCR followed by regular expressions written for this one layout, on all forty
  images: 10/10 documents on the clean images, 0/10 on every scan
- **Qwen3-VL 8B**, an open-weight vision model run through Ollama on a CPU with the same instruction
  and schema, on one invoice: 10 of 11 fields from the clean image and 8 of 11 from the poor one,
  at 17 to 20 minutes a page

Not tried, only considered: an invoice that carries its data as ISDOC XML or a QR code needs no reading
at all. A product would read those exactly and send only the rest to the model.

## What it is not

- Not a proof of reliability. Thirty readable documents without an error are consistent with up to
  one in ten having one (95 % confidence)
- Not a varied test set. Ten invoices of one fictional supplier in one layout, degraded
  synthetically
- Not repeatable to the digit. The model's randomness cannot be fixed; a second read of the harsh
  images differed in seven fields

## Output

```json
{
  "invoice": {
    "supplier_name": "Vzorová dodavatelská s.r.o.",
    "supplier_company_id": "87654326",
    "supplier_vat_id": "CZ87654326",
    "invoice_number": "2026-000236",
    "variable_symbol": "2026000236",
    "issue_date": "2026-10-01",
    "tax_point_date": "2026-09-29",
    "due_date": "2026-10-13",
    "vat_lines": [
      { "vat_rate_percent": 21, "net_amount": 600000, "vat_amount": 126000 },
      { "vat_rate_percent": 12, "net_amount": 2424300, "vat_amount": 290916 }
    ],
    "total_gross_amount": 3441216,
    "currency": "CZK"
  },
  "failed_checks": [],
  "model": "claude-opus-5-5",
  "input_tokens": 3892,
  "output_tokens": 221
}
```

Amounts are integers in haléře, the hundredth of a koruna: `3441216` is 34 412,16 CZK. Any field of
the invoice can be `null`, meaning absent or illegible.
