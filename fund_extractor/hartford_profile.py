from dataclasses import dataclass
from typing import List, Optional


@dataclass
class HartfordHolding:
    fund_name: str
    report_date: str
    security_name: str
    security_type: Optional[str]
    sector: Optional[str]
    shares: Optional[float]
    principal: Optional[float]
    market_value: Optional[float]


HARTFORD_SOI_HEADER_KEY = "Schedule of Investments"


