from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    fund_name: str
    report_date: str
    security_name: str
    security_type: Optional[str]
    country_iso3: Optional[str]
    sector: Optional[str]
    shares: Optional[float]
    principal: Optional[float]
    market_value: Optional[float]


