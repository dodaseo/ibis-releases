#!/usr/bin/env python3
"""다운로드 스냅숏(stats/downloads.csv) → 읽을 수 있는 요약·그래프(마크다운).

GitHub 은 **누적** 수만 주므로 일별 증가는 스냅숏 사이의 차분으로 계산한다.
표준 라이브러리만 쓴다(Actions 의 python3 로 바로 돌린다).

사용법:
  python3 stats/report.py [csv]                 전체 요약(stats/README.md 용, 표준출력)
  python3 stats/report.py [csv] --chart         README 하단 삽입용 짧은 블록만 출력
  python3 stats/report.py [csv] --write-readme  README.md 의 마커 사이를 직접 갱신

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

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
CHART_ONLY = "--chart" in sys.argv[1:]
WRITE_README = "--write-readme" in sys.argv[1:]
CSV = Path(ARGS[0] if ARGS else "stats/downloads.csv")

README = Path("README.md")
MARK_S = "<!-- DL-STATS:START -->"
MARK_E = "<!-- DL-STATS:END -->"
MARK_NOTE = ("<!-- 이 블록은 .github/workflows/dl-stats.yml 이 매일 생성합니다. "
             "직접 고치지 마세요. -->")


def kind(asset: str) -> str:
    a = asset.lower()
    if a.endswith(".sha256"):
        return "checksum"
    if a.endswith("setup.exe"):
        return "setup"
    if a.endswith(".zip"):
        return "zip"
    return "기타"


def chart_block(days: list[str], per_day) -> list[str]:
    """누적 다운로드 mermaid 차트 — GitHub 이 자체 렌더한다(이미지 파일 불필요).

    점이 하나면 그리지 않는다(선이 성립하지 않고 축도 못 잡는다).
    xychart-beta 는 범례를 지원하지 않아 제목·캡션으로 계열을 밝힌다.
    """
    if len(days) < 2:
        return ["> 스냅숏이 하나뿐이라 아직 그래프를 그릴 수 없습니다 — 내일부터 채워집니다.", ""]
    setup = [per_day[d].get("setup", 0) for d in days]
    zipd = [per_day[d].get("zip", 0) for d in days]
    top = int(max([*setup, *zipd, 1]) * 1.2) + 1        # 위쪽 여유
    xs = ", ".join(d[5:] for d in days)                  # MM-DD (긴 라벨은 겹친다)
    return [
        "```mermaid",
        "xychart-beta",
        '    title "누적 다운로드 — 설치 프로그램 / 무설치 zip"',
        f"    x-axis [{xs}]",
        f'    y-axis "건수" 0 --> {top}',
        "    line [" + ", ".join(str(v) for v in setup) + "]",
        "    line [" + ", ".join(str(v) for v in zipd) + "]",
        "```",
        "",
        "> 설치 프로그램은 **새로 설치한 사람**에 가깝고, zip 은 **인앱 업데이트**가 섞입니다.",
        "",
    ]


def load():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_asset: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for r in rows:
        d, tag, asset = r["date"], r["tag"], r["asset"]
        n = int(r["downloads"])
        per_day[d][kind(asset)] += n
        per_asset[d][(tag, asset)] = n
    return rows, per_day, per_asset


def short_block(days: list[str], per_day, last: str) -> str:
    """README 하단 '사용 현황' 에 넣을 짧은 블록(요약 한 줄 + 차트 + 링크)."""
    tot = sum(per_day[last].get(k, 0) for k in ("setup", "zip", "checksum"))
    head = (f"최신 기록 **{last}** · 누적 합계 **{tot}건**"
            f" (설치 {per_day[last].get('setup', 0)} · zip {per_day[last].get('zip', 0)})")
    tail = ("자세한 표는 [stats/README.md](stats/README.md), "
            "원본은 [stats/downloads.csv](stats/downloads.csv).")
    return "\n".join([head, ""] + chart_block(days, per_day) + [tail])


def write_readme(block: str) -> None:
    """마커 사이만 바꿔치운다 — 워크플로가 매일 부르므로 나머지 문서를 건드리면 안 된다."""
    if not README.is_file():
        print("README.md 없음 — 건너뜀")
        return
    t = README.read_text(encoding="utf-8")
    if MARK_S not in t or MARK_E not in t:
        print("README 에 DL-STATS 마커가 없음 — 건너뜀")
        return
    new = "\n".join([MARK_S, MARK_NOTE, "", block.strip(), "", MARK_E])
    head, rest = t.split(MARK_S, 1)
    _, tail = rest.split(MARK_E, 1)
    README.write_text(head + new + tail, encoding="utf-8")
    print("README '사용 현황' 갱신")


def main() -> int:
    if not CSV.is_file():
        print("스냅숏이 아직 없습니다.")
        return 0
    rows, per_day, per_asset = load()
    if not rows:
        print("스냅숏이 비어 있습니다.")
        return 0
    days = sorted(per_day)
    last, prev = days[-1], (days[-2] if len(days) > 1 else None)

    if CHART_ONLY or WRITE_README:
        block = short_block(days, per_day, last)
        if WRITE_README:
            write_readme(block)
        else:
            print(block)
        return 0

    out: list[str] = ["# 다운로드 추이", ""]
    out.append(f"- 기록 시작 **{days[0]}** · 최신 스냅숏 **{last}** · 스냅숏 {len(days)}개")
    out.append("- 이 파일은 매일 자동 생성됩니다. 원본은 [`downloads.csv`](downloads.csv).")
    out.append("")

    out += ["## 누적", "", "| 구분 | 누적 | 전일 대비 |", "|---|---:|---:|"]
    labels = [("setup", "설치 프로그램 (새 설치에 가깝다)"),
              ("zip", "무설치 zip (+ 인앱 업데이트)"),
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
    out += [f"| **합계** | **{tot}** | |", ""]

    if len(days) > 1:
        out += ["## 일별 증가", "", "| 날짜 | 설치 | zip | 합계 |", "|---|---:|---:|---:|"]
        for i in range(1, len(days)):
            a, b = days[i - 1], days[i]
            ds = per_day[b].get("setup", 0) - per_day[a].get("setup", 0)
            dz = per_day[b].get("zip", 0) - per_day[a].get("zip", 0)
            out.append(f"| {b} | {ds:+d} | {dz:+d} | {ds + dz:+d} |")
        out.append("")

    out += ["## 누적 그래프", ""] + chart_block(days, per_day)

    out += ["## 릴리스별 (최신 스냅숏)", "", "| 릴리스 | 설치 | zip |", "|---|---:|---:|"]
    by_tag: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (tag, asset), n in per_asset[last].items():
        by_tag[tag][kind(asset)] += n
    ranked = sorted(by_tag.items(), key=lambda kv: -(kv[1].get("setup", 0) + kv[1].get("zip", 0)))
    for tag, v in ranked[:8]:
        out.append(f"| {tag} | {v.get('setup', 0)} | {v.get('zip', 0)} |")
    if len(ranked) > 8:
        out.append(f"| … 외 {len(ranked) - 8}개 | | |")
    out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
