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
    views = parser.add_mutually_exclusive_group()
    views.add_argument('--summary', action='store_true', help='短状态，制作默认查询')
    views.add_argument('--cue-id', help='展开一个 Cue 及适用反馈')
    views.add_argument('--feedback-id', help='展开原始反馈，不限制状态或适用性')
    args = parser.parse_args(argv)
    try:
        if args.action != 'status' and (args.summary or args.cue_id is not None or args.feedback_id is not None):
            raise ValueError('status view options are available only for status')
        request = json.loads(args.request_file.read_text()) if args.request_file else None
        if request is not None and not isinstance(request, dict):
            raise ValueError("request file must contain a JSON object")
        if args.action == "open":
            result = work_model.open_project(args.target, request)
        elif args.action == "status":
            if (args.target / "animation-manifest.json").is_file():
                view = 'summary' if args.summary else 'cue' if args.cue_id is not None else 'feedback' if args.feedback_id is not None else 'full'
                result = work_model.status(args.target, view=view, cue_id=args.cue_id, feedback_id=args.feedback_id)
            else:
                if args.summary or args.cue_id is not None or args.feedback_id is not None:
                    raise ValueError('status views require a production version root')
                result = work_model.project_status(args.target)
        else:
            if request is None:
                raise ValueError("write operations require --request-file")
            result = getattr(work_model, args.action)(args.target, request)
        if args.action in {'preview', 'resume'} and result.get('status') == 'complete':
            from scripts.work_model_review_entry import handoff
            result = handoff(args.target, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
