#!/usr/bin/env python3
"""Single local entry point for AfterForge work-model operations."""
import argparse
import json
import sys
import subprocess
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import work_model


def main(argv=None):
    parser = argparse.ArgumentParser(description="AfterForge：作品、修改、预览与交付")
    parser.add_argument("action", choices=("open", "status", "update", "preview", "deliver", "resume"))
    parser.add_argument("target", type=Path)
    parser.add_argument("--request-file", type=Path)
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request_file.read_text()) if args.request_file else None
        if request is not None and not isinstance(request, dict):
            raise ValueError("request file must contain a JSON object")
        if args.action == "open":
            result = work_model.open_project(args.target, request)
        elif args.action == "status":
            result = work_model.status(args.target) if (args.target / "animation-manifest.json").is_file() else work_model.project_status(args.target)
        else:
            if request is None:
                raise ValueError("write operations require --request-file")
            result = getattr(work_model, args.action)(args.target, request)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
