"""Eval-харнесс качества нарезки (план §7.1–7.2).

Pure: clip_bucket (рубрика C1–C8 + killers), compute_q (Q=(usable+fixable)/total).
I/O: generate_eval_csv (job.json → пустая scoring-таблица), score_sheet (заполненная → Q).

Использование (из services/worker):
  uv run python -m app.eval <job_id>           # → data/<job_id>/eval_sheet.csv (заполнить C1–C8)
  uv run python -m app.eval <job_id> --score   # посчитать Q по заполненной таблице
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

# eval.py → parents[1] = app/, parents[1].. data рядом с пакетом (как в run.py)
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

CRITERIA = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]
_KILLERS = ("c1", "c5", "c6")  # standalone / face-framed / captions-accurate
_TRIMMABLE = {"c2", "c3", "c4", "c8"}  # чинятся сдвигом границ (Phase 2 trim-редактор)


def clip_bucket(scores: dict[str, int]) -> str:
    """C1–C8 (0/1) → 'usable' | 'fixable' | 'reject' (рубрика §7.1).

    Killer (C1/C5/C6=0) или total≤3 → reject. total≥7 → usable.
    total≥5 и провалы только тримабельные → fixable. Иначе reject.
    """
    total = sum(int(scores[c]) for c in CRITERIA)
    if any(int(scores[k]) == 0 for k in _KILLERS) or total <= 3:
        return "reject"
    if total >= 7:
        return "usable"
    failed = {c for c in CRITERIA if int(scores[c]) == 0}
    if total >= 5 and failed <= _TRIMMABLE:
        return "fixable"
    return "reject"


def compute_q(buckets: list[str]) -> float:
    """Q = (usable + fixable) / total. Пустой список → 0.0."""
    if not buckets:
        return 0.0
    good = sum(1 for b in buckets if b in ("usable", "fixable"))
    return round(good / len(buckets), 3)


_HEADER = [
    "clip_id", "type", "model_score", "timecode", "reason",
    *CRITERIA, "reason_agrees", "notes",
]  # fmt: skip


def generate_eval_csv(job: dict[str, Any]) -> str:
    """job.json (wire) → CSV: строка на клип; C1–C8/reason_agrees пустые (заполнить глядя клип)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_HEADER)
    for c in job.get("clips", []):
        tc = f"{c['start']:.1f}-{c['end']:.1f}"
        w.writerow([c["id"], c["type"], c["score"], tc, c["reason"], *([""] * 8), "", ""])
    return buf.getvalue()


def score_sheet(csv_path: Path) -> tuple[list[tuple[str, str]], float]:
    """Заполненная таблица → ([(clip_id, bucket)], Q). Незаполненные строки пропускаются."""
    rows: list[tuple[str, str]] = []
    with csv_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not (r.get("c1") or "").strip():
                continue
            scores = {c: int((r.get(c) or "0").strip() or 0) for c in CRITERIA}
            rows.append((r["clip_id"], clip_bucket(scores)))
    return rows, compute_q([b for _, b in rows])


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: python -m app.eval <job_id> [--score]")
    job_id = args[0]
    out = DATA_ROOT / job_id
    sheet = out / "eval_sheet.csv"
    if "--score" in args:
        rows, q = score_sheet(sheet)
        for cid, b in rows:
            print(f"  {cid}: {b}")
        usable = sum(1 for _, b in rows if b == "usable")
        print(f"\nQ = {q}  (usable+fixable)/{len(rows)};  usable={usable}/{len(rows)}")
        print("GO ✅" if q >= 0.60 else "NO-GO ❌", "(порог Q ≥ 0.60)")
    else:
        job = json.loads((out / "job.json").read_text(encoding="utf-8"))
        sheet.write_text(generate_eval_csv(job), encoding="utf-8")
        print(f"scoring-таблица: {sheet}")
        print(f"Заполни C1–C8 (0/1) глядя каждый клип, потом: python -m app.eval {job_id} --score")


if __name__ == "__main__":
    main()
