import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import pdfplumber
from dotenv import load_dotenv
from openai import OpenAI


def guess_fund_name(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(?im)^(.*Fund)\s*$", text)
    return m.group(1).strip() if m else ""


def guess_report_date(text: str) -> str:
    if not text:
        return ""
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2}),\s*(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return ""
    month, day, year = m.groups()
    return f"{month.title()} {int(day)}, {year}"


def extract_sample(pdf_path: Path, max_schedule_pages: int = 3) -> Dict[str, Any]:
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        num_pages = len(pages)

        # Use first few pages for metadata
        first_text = "\n".join((pages[i].extract_text() or "") for i in range(min(3, num_pages)))
        fund_name = guess_fund_name(first_text) or pdf_path.stem
        report_date = guess_report_date(first_text)

        # Find first Schedule of Investments page
        schedule_idx = None
        for idx, page in enumerate(pages):
            text = page.extract_text() or ""
            if "Schedule of Investments" in text:
                schedule_idx = idx
                break

        sample_pages: List[Dict[str, Any]] = []

        # Cover / metadata pages
        for i in range(min(2, num_pages)):
            text = pages[i].extract_text() or ""
            sample_pages.append(
                {
                    "page_index": i,
                    "role": "front_matter",
                    "text": text[:4000],
                }
            )

        # Schedule pages
        if schedule_idx is not None:
            for offset in range(max_schedule_pages):
                idx = schedule_idx + offset
                if idx >= num_pages:
                    break
                text = pages[idx].extract_text() or ""
                sample_pages.append(
                    {
                        "page_index": idx,
                        "role": "schedule",
                        "text": text[:6000],
                    }
                )

        return {
            "file_name": pdf_path.name,
            "fund_name_guess": fund_name,
            "report_date_guess": report_date,
            "sample_pages": sample_pages,
        }


def load_example_configs(config_dir: Path) -> Dict[str, str]:
    examples: Dict[str, str] = {}
    if not config_dir.exists():
        return examples
    for path in sorted(config_dir.glob("*.yaml")):
        # Only load a couple of small examples to keep prompt size manageable
        examples[path.stem] = path.read_text(encoding="utf-8")[:4000]
        if len(examples) >= 3:
            break
    return examples


def build_prompt(sample: Dict[str, Any], examples: Dict[str, str], layout_id: str) -> List[Dict[str, str]]:
    system = {
        "role": "system",
        "content": (
            "You are an assistant that designs YAML layout configurations for extracting holdings from mutual "
            "fund Schedule of Investments PDFs.\n"
            "You must ONLY output a YAML document matching the following schema:\n\n"
            "id: <string>\n"
            "fund_name_patterns: [<regex strings that match the fund name on the page>]\n"
            "schedule_header: <literal header text used to find the section, e.g. 'Schedule of Investments'>\n"
            "layout:\n"
            "  type: <one of 'two_column_multiline_shares_first', 'two_column_line_numeric', 'one_column_line_numeric'>\n"
            "  columns: <int number of columns per page, usually 1 or 2>\n"
            "  shares_token_index: <int index of the numeric token that represents shares>\n"
            "  value_token_index: <int index of the numeric token that represents value>\n"
            "instrument_headers: <mapping from header prefixes to security types, e.g. 'CommonStocks' -> 'Common Stock'>\n"
            "stop_line_prefixes: [<strings where parsing on a page should stop, like 'TOTAL INVESTMENTS'>]\n"
            "stop_line_contains: [<substrings that stop parsing when present in a line>]\n"
            "noise_prefixes: [<strings that mark lines to be skipped as non-holdings>]\n\n"
            "Be conservative: prefer simple regexes and literal prefixes that match the sample text. "
            "Do not invent fields that are not in the schema. "
            "Do not explain the YAML; just output the YAML itself."
        ),
    }

    example_blocks = []
    for name, yaml_text in examples.items():
        example_blocks.append(f"# Example layout config: {name}\n{yaml_text}")

    user_content = [
        "Here are some example layout configs:\n",
        *example_blocks,
        "\nNow here is a JSON description of a NEW fund PDF. "
        "Use it to infer a suitable YAML layout config. "
        f"Use the id '{layout_id}'.\n",
        "```json\n",
        json.dumps(sample, indent=2),
        "\n```",
    ]

    user = {"role": "user", "content": "\n".join(user_content)}
    return [system, user]


def _derive_layout_id(fund_name_guess: str, pdf_stem: str) -> str:
    base = fund_name_guess or pdf_stem
    # Normalize: lowercase, replace non-alphanumerics with underscores, collapse
    base = base.lower()
    base = re.sub(r"[^a-z0-9]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    # Ensure it starts with a letter for YAML friendliness
    if not base or not base[0].isalpha():
        base = "layout_" + base
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate layout config YAMLs for new funds using an LLM.")
    parser.add_argument(
        "pdf",
        type=Path,
        nargs="?",
        help="Optional single sample PDF. If omitted, all PDFs in --samples-dir are processed.",
    )
    parser.add_argument(
        "--id",
        help="Explicit layout id to use (only when a single PDF is specified). "
        "If omitted, an id is derived from the fund name or file name.",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=Path("report_samples"),
        help="Directory containing sample PDFs (used when no PDF argument is given).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model name to use (default: gpt-4.1-mini).",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("configs"),
        help="Directory containing existing example configs to include in the prompt.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("generated_configs"),
        help="Directory where the generated YAML configs will be written.",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment or .env file.")

    # Determine which PDFs to process
    if args.pdf:
        pdf_paths = [args.pdf]
    else:
        if not args.samples_dir.exists():
            raise SystemExit(f"Samples directory not found: {args.samples_dir}")
        pdf_paths = sorted(p for p in args.samples_dir.glob("*.pdf"))
        if not pdf_paths:
            raise SystemExit(f"No PDFs found in samples directory: {args.samples_dir}")

    if args.id and len(pdf_paths) > 1:
        raise SystemExit("--id can only be used when generating a config for a single PDF.")

    examples = load_example_configs(args.config_dir)
    client = OpenAI(api_key=api_key)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdf_paths:
        sample = extract_sample(pdf_path)
        layout_id = args.id or _derive_layout_id(sample.get("fund_name_guess", ""), pdf_path.stem)
        messages = build_prompt(sample, examples, layout_id=layout_id)

        print(f"Generating config for {pdf_path.name} with id '{layout_id}' using model {args.model}...")
        resp = client.chat.completions.create(
            model=args.model,
            messages=messages,
            temperature=0.2,
        )

        yaml_text = resp.choices[0].message.content.strip()

        out_path = args.out_dir / f"{layout_id}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
        print(f"  -> written to {out_path}")


if __name__ == "__main__":
    main()


