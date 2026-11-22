"""`robotics101` command-line entry point.

Exit codes: 0 ok, 1 validation failed, 2 usage/input error (missing file, bad JSON),
3 command not implemented yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from robotics101 import __version__
from robotics101.validation import validate_file

EXIT_OK, EXIT_INVALID, EXIT_INPUT, EXIT_NOT_IMPLEMENTED = 0, 1, 2, 3


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_file(args.episode)
    except OSError as e:
        print(f"error: cannot read {args.episode}: {e.strerror or e}", file=sys.stderr)
        return EXIT_INPUT
    except json.JSONDecodeError as e:
        print(f"error: {args.episode} is not valid JSON: {e}", file=sys.stderr)
        return EXIT_INPUT

    for issue in report.issues:
        print(issue, file=sys.stderr if issue.severity == "error" else sys.stdout)

    failed = not report.ok or (args.strict and report.warnings)
    status = "INVALID" if failed else "VALID"
    print(f"{status}: {args.episode} ({len(report.errors)} error(s), {len(report.warnings)} warning(s))")
    return EXIT_INVALID if failed else EXIT_OK


def _cmd_render(args: argparse.Namespace) -> int:
    print("error: render not implemented yet (M01.5)", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="robotics101", description="Robotics 101 episode pipeline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate an EpisodeSpec JSON file")
    v.add_argument("episode", type=Path)
    v.add_argument("--strict", action="store_true", help="treat warnings as errors")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("render", help="render an episode (not implemented yet: M01.5)")
    r.add_argument("episode", type=Path)
    r.add_argument("--out", type=Path, default=None)
    r.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
