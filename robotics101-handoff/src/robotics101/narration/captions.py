"""SRT caption generation, parsing and validation (episode timeline)."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

MAX_LINE = 42
MAX_LINES = 2
MAX_CUE_CHARS = MAX_LINE * MAX_LINES

_TS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str  # may contain "\n"


def format_ts(ms: int) -> str:
    h, rem = divmod(int(ms), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_ = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_:03d}"


def parse_ts(ts: str) -> int:
    m = _TS_RE.match(ts.strip())
    if not m:
        raise ValueError(f"bad SRT timestamp {ts!r}")
    h, mi, s, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + s) * 1000 + ms


def _fits(chunk: str) -> bool:
    return len(textwrap.wrap(chunk, MAX_LINE)) <= MAX_LINES


def split_cue_texts(narration: str) -> list[str]:
    """Sentences, then clauses (",;:"), then word-packing, so each cue wraps to <= 2 x 42 chars."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(narration.split())):
        if not sentence:
            continue
        if _fits(sentence):
            out.append(sentence)
            continue
        clauses = re.split(r"(?<=[,;:])\s+", sentence)
        cur = ""
        for clause in clauses:
            for word in clause.split():
                cand = f"{cur} {word}".strip()
                if _fits(cand):
                    cur = cand
                else:
                    if cur:
                        out.append(cur)
                    cur = word
            # prefer breaking at clause boundaries once a cue is reasonably full
            if cur and len(cur) >= int(MAX_CUE_CHARS * 0.7):
                out.append(cur)
                cur = ""
        if cur:
            out.append(cur)
    return out


def wrap_cue(text: str) -> str:
    return "\n".join(textwrap.wrap(text, MAX_LINE))


def scene_cues(narration: str, start_s: float, end_s: float) -> list[tuple[int, int, str]]:
    """Distribute cues over [start_s, end_s] proportionally to character count (integer ms, contiguous)."""
    texts = split_cue_texts(narration)
    if not texts:
        return []
    start_ms, end_ms = round(start_s * 1000), round(end_s * 1000)
    total = sum(len(t) for t in texts)
    cues, acc, prev = [], 0, start_ms
    for t in texts:
        acc += len(t)
        b = start_ms + round((end_ms - start_ms) * acc / total)
        cues.append((prev, b, wrap_cue(t)))
        prev = b
    return cues


def build_srt(cues: list[tuple[int, int, str]]) -> str:
    blocks = [f"{i}\n{format_ts(s)} --> {format_ts(e)}\n{text}\n" for i, (s, e, text) in enumerate(cues, 1)]
    return "\n".join(blocks)


def parse_srt(srt: str) -> list[Cue]:
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            raise ValueError(f"malformed SRT block: {block!r}")
        idx = int(lines[0])
        start, arrow, end = lines[1].partition(" --> ")
        if not arrow:
            raise ValueError(f"missing '-->' in {lines[1]!r}")
        cues.append(Cue(idx, parse_ts(start), parse_ts(end), "\n".join(lines[2:])))
    return cues


def validate_srt(cues: list[Cue], *, bounds_ms: tuple[int, int] | None = None) -> list[str]:
    """Return a list of problems (empty == valid)."""
    problems: list[str] = []
    prev_end = -1
    for n, c in enumerate(cues, 1):
        if c.index != n:
            problems.append(f"cue {n}: index {c.index} not sequential")
        if c.end_ms <= c.start_ms:
            problems.append(f"cue {n}: non-positive duration")
        if c.start_ms < prev_end:
            problems.append(f"cue {n}: overlaps previous cue")
        lines = c.text.splitlines()
        if len(lines) > MAX_LINES or any(len(l) > MAX_LINE for l in lines):
            problems.append(f"cue {n}: exceeds {MAX_LINES}x{MAX_LINE} chars")
        if bounds_ms and (c.start_ms < bounds_ms[0] or c.end_ms > bounds_ms[1]):
            problems.append(f"cue {n}: outside bounds {bounds_ms}")
        prev_end = c.end_ms
    return problems
