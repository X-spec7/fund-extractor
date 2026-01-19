from __future__ import annotations

"""
Layout configuration loading and detection.

Each mutual fund family / report style is described by a `LayoutConfig` loaded
from a YAML file. The extractor stays generic and uses these configs to adapt
to new PDFs without code changes.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass(frozen=True)
class LayoutConfig:
    """
    In-memory representation of a single layout configuration.

    Most fields map directly from the YAML schema; see the README and
    example configs under `configs/` for concrete examples.
    """

    id: str
    fund_name_patterns: List[str]
    schedule_header: str
    # e.g. "two_column_line_numeric", "one_column_line_numeric", "hartford_custom"
    layout_type: str
    columns: int = 1
    shares_token_index: int = 0
    value_token_index: int = 1
    # Mapping from text prefixes on a page to a normalized security type label.
    instrument_headers: Dict[str, str] | None = None
    # Line-level controls to stop or skip parsing within a schedule page.
    stop_line_prefixes: List[str] | None = None
    stop_line_contains: List[str] | None = None
    noise_prefixes: List[str] | None = None


def load_layout_configs(config_dir: Path) -> List[LayoutConfig]:
    """
    Load all YAML layout configurations from `config_dir`.

    Returns a list of `LayoutConfig` instances; if the directory does not
    exist, an empty list is returned.
    """
    configs: List[LayoutConfig] = []
    if not config_dir.exists():
        return configs

    for path in sorted(config_dir.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        layout = raw.get("layout") or {}

        cfg = LayoutConfig(
            id=raw["id"],
            fund_name_patterns=raw.get("fund_name_patterns", []),
            schedule_header=raw["schedule_header"],
            layout_type=layout["type"],
            columns=layout.get("columns", 1),
            shares_token_index=layout.get("shares_token_index", 0),
            value_token_index=layout.get("value_token_index", 1),
            instrument_headers=raw.get("instrument_headers", {}),
            stop_line_prefixes=raw.get("stop_line_prefixes", []),
            stop_line_contains=raw.get("stop_line_contains", []),
            noise_prefixes=raw.get("noise_prefixes", []),
        )
        configs.append(cfg)

    return configs


def detect_config_for_pdf(text: str, configs: List[LayoutConfig]) -> Optional[LayoutConfig]:
    """
    Given concatenated text from the first few pages of a PDF, return the first
    layout config whose `fund_name_patterns` matches the text.

    Matching is performed against both the raw text and a version with spaces
    removed to make the detection robust to broken line-wrapping.
    """
    import re

    text_nospace = text.replace(" ", "")
    for cfg in configs:
        for patt in cfg.fund_name_patterns:
            pattern = re.compile(patt, re.IGNORECASE)
            if pattern.search(text) or pattern.search(text_nospace):
                return cfg
    return None


