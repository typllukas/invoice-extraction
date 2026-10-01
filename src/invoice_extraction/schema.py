import datetime

from pydantic import BaseModel, ConfigDict, Field


class VatLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    vat_rate_percent: int | None = Field(
        description="VAT rate in percent; 0 for an exempt line"
    )
    net_amount: int | None = Field(description="Tax base of this rate in whole haléře")
    vat_amount: int | None = Field(description="VAT of this rate in whole haléře")


class Invoice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supplier_name: str | None = Field(
        description="Name of the issuer, never the customer"
    )
    supplier_company_id: str | None = Field(description="IČO of the issuer")
    supplier_vat_id: str | None = Field(description="DIČ of the issuer")
    invoice_number: str | None = Field(description="Invoice number exactly as printed")
    variable_symbol: str | None
    issue_date: datetime.date | None
    tax_point_date: datetime.date | None = Field(
        description="Date of taxable supply (DUZP)"
    )
    due_date: datetime.date | None
    vat_lines: list[VatLine] | None = Field(
        description="One line per rate of the VAT recapitulation"
    )
    total_gross_amount: int | None = Field(description="Amount to pay in whole haléře")
    currency: str | None = Field(description="ISO 4217 code")
