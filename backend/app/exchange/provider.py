"""Exchange provider contract and controlled error type."""

from abc import ABC, abstractmethod
from typing import Any


class ExchangeProviderError(Exception):
    """Raised when an exchange provider cannot return a valid quote."""


class ExchangeProvider(ABC):
    """
    Abstract exchange provider interface.

    Implementations must validate external responses and return a normalized
    quote dict with at least: base_currency, target_currency, rate, timestamp,
    provider.
    """

    @abstractmethod
    def get_quote(self, base_currency: str, target_currency: str) -> dict[str, Any]:
        """Return a normalized exchange quote or raise ExchangeProviderError."""
