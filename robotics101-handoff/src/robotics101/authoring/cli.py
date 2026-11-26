"""``robotics101 authoring ...`` (offline; no paid calls)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_catalog(args) -> int:
    from robotics101.authoring.catalog import build_catalog, card_problems
    probs = card_problems()
    cat = build_catalog()
    text = json.dumps(cat, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"catalog: {args.out} ({', '.join(f'{k} {len(v)}' for k, v in cat.items() if isinstance(v, (dict, list)))})")
    else:
        sys.stdout.write(text)
    for p in probs:
        print(f"card problem: {p}", file=sys.stderr)
    return 1 if probs else 0


def _cmd_review(args) -> int:
    from robotics101.authoring.review import check_review, write_packet
    if args.write:
        path, sha = write_packet(args.run_dir, args.point)
        print(f"{args.point} packet: {path} sha256 {sha}")
    print(json.dumps(check_review(args.run_dir, args.point), indent=2))
    return 0


def add_parser(sub) -> None:
    a = sub.add_parser("authoring", help="topic-to-script authoring tools (offline, fixture mode; no paid calls)")
    asub = a.add_subparsers(dest="authoring_cmd", required=True)
    c = asub.add_parser("catalog", help="print/write the catalogue (code + capability cards); exit 1 on card problems")
    c.add_argument("--out", type=Path, default=None)
    c.set_defaults(func=_cmd_catalog)
    r = asub.add_parser("review", help="R1/R2 review packet status (--write builds the packet; never approves)")
    r.add_argument("run_dir", type=Path)
    r.add_argument("point", choices=["R1", "R2"])
    r.add_argument("--write", action="store_true")
    r.set_defaults(func=_cmd_review)
    _extra(asub)


def _extra(asub) -> None:
    """Later milestones register more sub-commands here."""


__all__ = ["add_parser"]
