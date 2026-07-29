#!/usr/bin/env python3
"""다운로드 스냅숏(stats/downloads.csv) → 읽을 수 있는 요약(마크다운).

GitHub 은 **누적** 수만 주므로 일별 증가는 스냅숏 사이의 차분으로 계산한다.
표준 라이브러리만 쓴다(Actions 의 python3 로 바로 돌린다).

분석 주의 — 이 구분이 숫자의 뜻을 바꾼다:
  · setup.exe  : 새로 설치한 사람에 가깝다(인앱 업데이터는 setup 을 받지 않는다)
  · win64.zip  : 무설치 사용자 + **인앱 업데이트**가 섞인다
  · .sha256    : 업데이터의 무결성 검증·수동 확인 — 사람 수와 무관
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

CSV = Path(sys.argv[1] if len(sys.argv) > 1 else "stats/downloads.csv")


def kind(asset: str) -> str:
    a = asset.lower()
    if a.endswith(".sha256"):
        return "checksum"
    if a.endswith("setup.exe"):
        return "setup"
    if a.endswith(".zip"):
        return "zip"
    return "기타"


def main() -> int:
    if not CSV.is_file():
        print("스냅숏이 아직 없습니다."); return 0
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    if not rows:
        print("스냅숏이 비어 있습니다."); return 0

    # date -> kind -> 누적합 / date -> (tag, asset) -> 값
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_asset: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for r in rows:
        d, tag, asset = r["date"], r["tag"], r["asset"]
        n = int(r["downloads"])
        per_day[d][kind(asset)] += n
        per_asset[d][(tag, asset)] = n
    days = sorted(per_day)
    last, prev = days[-1], (days[-2] if len(days) > 1 else None)

    out: list[str] = []
    out.append("# 다운로드 추이")
    out.append("")
    out.append(f"- 기록 시작 **{days[0]}** · 최신 스냅숏 **{last}** · 스냅숏 {len(days)}개")
    out.append("- 이 파일은 매일 자동 생성됩니다. 원본은 [`downloads.csv`](downloads.csv).")
    out.append("")

    # ── 누적 ──
    out.append("## 누적")
    out.append("")
    out.append("| 구분 | 누적 | 전일 대비 |")
    out.append("|---|---:|---:|")
    labels = [("setup", "설치 프로그램 (새 설치에 가깝다)"), ("zip", "무설치 zip (+ 인앱 업데이트)"),
              ("checksum", "체크섬 파일 (사람 수 아님)")]
    for k, label in labels:
        cur = per_day[last].get(k, 0)
        if prev is None:
            delta = "—"
        else:
            d = cur - per_day[prev].get(k, 0)
            delta = f"+{d}" if d > 0 else str(d)
        out.append(f"| {label} | {cur} | {delta} |")
    tot = sum(per_day[last].get(k, 0) for k, _ in labels)
    out.append(f"| **합계** | **{tot}** | |")
    out.append("")

    # ── 일별 증가 ──
    if len(days) > 1:
        out.append("## 일별 증가")
        out.append("")
        out.append("| 날짜 | 설치 | zip | 합계 |")
        out.append("|---|---:|---:|---:|")
        for i in range(1, len(days)):
            a, b = days[i - 1], days[i]
            ds = per_day[b].get("setup", 0) - per_day[a].get("setup", 0)
            dz = per_day[b].get("zip", 0) - per_day[a].get("zip", 0)
            out.append(f"| {b} | {ds:+d} | {dz:+d} | {ds + dz:+d} |")
        out.append("")
    else:
        out.append("> 스냅숏이 하나뿐이라 아직 증가를 계산할 수 없습니다 — 내일부터 채워집니다.")
        out.append("")

    # ── 릴리스별(최신 스냅숏 기준, 상위 8개) ──
    out.append("## 릴리스별 (최신 스냅숏)")
    out.append("")
    by_tag: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (tag, asset), n in per_asset[last].items():
        by_tag[tag][kind(asset)] += n
    ranked = sorted(by_tag.items(), key=lambda kv: -(kv[1].get("setup", 0) + kv[1].get("zip", 0)))
    out.append("| 릴리스 | 설치 | zip |")
    out.append("|---|---:|---:|")
    for tag, v in ranked[:8]:
        out.append(f"| {tag} | {v.get('setup', 0)} | {v.get('zip', 0)} |")
    if len(ranked) > 8:
        out.append(f"| … 외 {len(ranked) - 8}개 | | |")
    out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
