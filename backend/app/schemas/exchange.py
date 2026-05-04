"""
Currency exchange domain schemas.

Source of truth: API_CONTRACT.md.
No external API calls, no ExchangeService implementation — contract only.
"""

from enum import Enum

from pydantic import BaseModel, Field


class CurrencyCode(str, Enum):
    """Supported currency codes for exchange quotation."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    ARS = "ARS"
    BTC = "BTC"


class ExchangeQuote(BaseModel):
    """
    Exchange rate quote returned to the customer.

    Populated by ExchangeService (future phase). This schema is the data contract only.
    """

    base_currency: CurrencyCode
    target_currency: CurrencyCode
    rate: float = Field(gt=0)
    timestamp: str
    provider: str | None = None
