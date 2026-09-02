#!/usr/bin/env python3
"""Generate or verify the human-readable workflow stage contract projection."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

try:
    from scripts.workflow_stages import CONTRACT_PATH, load_stage_contract, render_stage_contract_markdown
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from workflow_stages import CONTRACT_PATH, load_stage_contract, render_stage_contract_markdown  # type: ignore


PROJECTION_PATH = CONTRACT_PATH.with_suffix(".md")


def render_projection(contract_path: Path = CONTRACT_PATH) -> str:
    contract = load_stage_contract(contract_path)
    return render_stage_contract_markdown(
        contract,
        contract_sha256=hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或核验 workflow stage contract 的 Markdown 投影视图。")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_projection()
    if args.check:
        if not PROJECTION_PATH.is_file() or PROJECTION_PATH.read_text(encoding="utf-8") != rendered:
            print("workflow stage contract projection is stale")
            return 1
        print("workflow stage contract projection is current")
        return 0
    PROJECTION_PATH.write_text(rendered, encoding="utf-8")
    print(PROJECTION_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
