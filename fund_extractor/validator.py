from __future__ import annotations

from typing import Any, Dict, List

from .country_codes import COUNTRY_TO_ISO3
from .models import Holding


def validate_holdings(holdings: List[Holding]) -> Dict[str, Any]:
    """
    Basic validation for a list of Holding objects.

    Returns a dictionary with:
      - "errors": List[str]
      - "warnings": List[str]

    The goal is to catch clearly bad data (errors) and suspicious patterns
    (warnings) without being fund-specific.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not holdings:
        errors.append("No holdings extracted.")
        return {"errors": errors, "warnings": warnings}

    valid_iso3 = set(COUNTRY_TO_ISO3.values())
    total_market_value = 0.0

    for idx, h in enumerate(holdings):
        ctx = f"[row {idx}]"

        # Required-ish fields
        if not h.fund_name:
            errors.append(f"{ctx} fund_name is empty.")
        if not h.security_name:
            errors.append(f"{ctx} security_name is empty.")
        if not h.report_date:
            warnings.append(f"{ctx} report_date is empty.")

        # At least one numeric field should be present
        if h.shares is None and h.principal is None and h.market_value is None:
            warnings.append(
                f"{ctx} no numeric value present (shares, principal, or market_value)."
            )

        # ISO3 country code sanity check
        if h.country_iso3 is not None and h.country_iso3 not in valid_iso3:
            warnings.append(
                f"{ctx} country_iso3 '{h.country_iso3}' is not in the known ISO3 list."
            )

        # Numeric sanity checks
        for field_name in ("shares", "principal", "market_value"):
            value = getattr(h, field_name)
            if value is not None:
                if value < 0:
                    errors.append(
                        f"{ctx} {field_name} is negative ({value}); "
                        "long-only mutual funds should not have negative amounts."
                    )

        if h.market_value is not None:
            total_market_value += h.market_value

        # Very rough security name sanity check
        if h.security_name and len(h.security_name.split()) < 2:
            warnings.append(
                f"{ctx} security_name '{h.security_name}' has suspiciously few words."
            )

    if total_market_value <= 0:
        warnings.append(
            "Total market_value across all holdings is non-positive; "
            "this is suspicious for a typical mutual fund."
        )

    return {"errors": errors, "warnings": warnings}


