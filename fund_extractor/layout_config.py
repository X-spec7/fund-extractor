from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class LayoutConfig:
    id: str
    fund_name_patterns: List[str]
    schedule_header: str
    layout_type: str  # e.g. "two_column_line_numeric", "one_column_line_numeric", "hartford_custom"
    columns: int = 1
    shares_token_index: int = 0
    value_token_index: int = 1
    instrument_headers: Dict[str, str] | None = None  # prefix -> security_type
    stop_line_prefixes: List[str] | None = None
    stop_line_contains: List[str] | None = None
    noise_prefixes: List[str] | None = None


def load_layout_configs(config_dir: Path) -> List[LayoutConfig]:
    configs: List[LayoutConfig] = []
    if not config_dir.exists():
        return configs

    for path in sorted(config_dir.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        cfg = LayoutConfig(
            id=raw["id"],
            fund_name_patterns=raw.get("fund_name_patterns", []),
            schedule_header=raw["schedule_header"],
            layout_type=raw["layout"]["type"],
            columns=raw["layout"].get("columns", 1),
            shares_token_index=raw["layout"].get("shares_token_index", 0),
            value_token_index=raw["layout"].get("value_token_index", 1),
            instrument_headers=raw.get("instrument_headers", {}),
            stop_line_prefixes=raw.get("stop_line_prefixes", []),
            stop_line_contains=raw.get("stop_line_contains", []),
            noise_prefixes=raw.get("noise_prefixes", []),
        )
        configs.append(cfg)

    return configs


def detect_config_for_pdf(text: str, configs: List[LayoutConfig]) -> Optional[LayoutConfig]:
    """
    Given concatenated text from the first few pages of a PDF, find the first
    layout config whose fund_name_patterns matches.
    """
    import re

    text_nospace = text.replace(" ", "")
    for cfg in configs:
        for patt in cfg.fund_name_patterns:
            pattern = re.compile(patt, re.IGNORECASE)
            if pattern.search(text) or pattern.search(text_nospace):
                return cfg
    return None


