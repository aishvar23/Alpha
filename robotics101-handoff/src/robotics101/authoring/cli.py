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


def _cmd_gate(args) -> int:
    from robotics101.authoring.gates import run_gates
    from robotics101.authoring.schemas import write_artifact
    from robotics101.authoring.screenplay import screenplay
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p else None   # noqa: E731
    doc = run_gates(spec, facts=load(args.facts), outline=load(args.outline), gaps=load(args.gaps),
                    age_band=args.age_band)
    if args.out:
        write_artifact(args.out, doc, "authoring_report")
    if args.screenplay:
        args.screenplay.write_text(screenplay(spec, load(args.gaps)), encoding="utf-8")
    for g in doc["gates"]:
        flag = "ok  " if g["ok"] else ("FAIL" if g["blocking"] else "warn")
        print(f"{flag} {g['id']}: {g['message']}")
    print(f"authoring gates: {doc['status'].upper()}")
    return 0 if doc["status"] == "pass" else 1


def _extra(asub) -> None:
    g = asub.add_parser("gate", help="run the deterministic + engagement gates on an authored spec (no render)")
    g.add_argument("spec", type=Path)
    g.add_argument("--facts", type=Path, default=None)
    g.add_argument("--outline", type=Path, default=None, help="outline.json (gag tags, hook)")
    g.add_argument("--gaps", type=Path, default=None)
    g.add_argument("--age-band", default="6-9", choices=["6-9", "9-12"])
    g.add_argument("--out", type=Path, default=None, help="write authoring_report.json")
    g.add_argument("--screenplay", type=Path, default=None, help="write the R2 screenplay view (.md)")
    g.set_defaults(func=_cmd_gate)
    _extra2(asub)


def _extra2(asub) -> None:
    """Later milestones register more sub-commands here."""


__all__ = ["add_parser"]
