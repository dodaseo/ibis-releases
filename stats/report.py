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
  · .sha256    : **앱이 켜질 때마다** 한 번 — 아래 참고

🔑 .sha256 이 이 저장소에서 유일한 '살아 있는 설치' 신호다(2026-09-10 확인).
   앱은 시작할 때 `checkUpdate(true)` → `updater.check_latest()` 를 부르는데, 그 안의
   `_find_sha256()` 이 **업데이트가 없어도** `<zip>.sha256` 자산을 실제로 내려받는다.
   그래서 체크섬 증가분 ≈ **앱 실행 횟수**다(사람 수가 아니라 실행 횟수 — 하루에 두세 번
   켜면 그만큼 는다. 스캐너도 섞이므로 상한으로 읽는다).
   ⛔ "체크섬은 사람 수와 무관" 이라고 적혀 있던 것을 뒤집은 것이다 — 그 서술을 믿고
      이 계열을 통계에서 빼면, 클라우드에 로그인하지 않는 사용자를 볼 길이 아예 없어진다
      (2026-09-10 실측: Supabase 가입자는 개발 계정 1 뿐이라 서버 쪽에 신호가 없다).
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
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


# ── 그래프 ────────────────────────────────────────────────────────────────
# mermaid `xychart-beta` 를 쓰다 SVG 를 직접 그리는 쪽으로 옮겼다(2026-09-03).
# 그쪽으로는 이 그래프를 읽을 수 있게 만들 수 없었다:
#   · 범례가 없다 — 두 선을 구분할 방법이 제목 문장뿐이었다.
#   · 스냅숏이 서른 개를 넘자 x 축 라벨이 서로 겹쳐 날짜를 못 읽는다.
#   · 색을 정할 수 없어 앱·홈페이지의 종이톤과 따로 놀았다.
# SVG 는 셋 다 해결한다. 선 끝에 이름을 직접 붙여 범례 자체를 없애고,
# x 축은 **날짜 간격대로** 놓아 스냅숏이 빠진 날이 사실대로 보이게 한다.

SVG_W, SVG_H = 760, 200
PAD_L, PAD_R, PAD_T, PAD_B = 30, 96, 14, 26    # 왼쪽=눈금 숫자, 오른쪽=선 끝 라벨
# 둘을 같은 쪽에 두면 겹친다 — 처음에 y 숫자를 오른쪽에 놓았다가 실제 렌더에서 잡았다.
FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', "
        "'Apple SD Gothic Neo', sans-serif")

# 앱 Ivory 테마에서 가져온 초록을 '설치'(사람 수에 가까운 쪽)에 준다.
# zip 은 인앱 업데이트가 섞여 사람 수가 아니므로 눈에 덜 띄는 중성색으로 둔다.
THEMES = {
    "light": {"setup": "#0e7a5b", "zip": "#b0a68c", "grid": "#e6e0d0",
              "axis": "#d8d0bb", "text": "#847f6d", "ink": "#4c4f43"},
    "dark":  {"setup": "#4fb391", "zip": "#8a8069", "grid": "#302c23",
              "axis": "#3e392e", "text": "#9a937f", "ink": "#cdc7b6"},
}


def _axis(maxv: int, want: int = 5) -> tuple[int, int]:
    """(위끝, 눈금 간격). 간격을 먼저 고르고 위끝을 그 배수로 올린다 —
    위끝부터 정하면 0·17·33·50 처럼 읽히지 않는 눈금이 나온다(실제로 그랬다)."""
    raw = max(maxv, 1) / want
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    for m in (1, 2, 2.5, 5, 10):
        if mag * m >= raw:
            step = int(mag * m) or 1
            break
    return (maxv // step + 1) * step, step


def daily_runs(days: list[str], per_day) -> list[tuple[str, float, int]]:
    """[(날짜, 그날 실행 추정, 스냅숏 간격 일수)] — 체크섬 증가분을 하루치로 고른다.

    스냅숏이 하루 빠지면 다음 증가분이 이틀치가 된다(실제로 08-31·09-10 이 비었다).
    그대로 그리면 그날만 치솟아 사실과 다르게 보이므로 **간격 일수로 나눈다**.
    """
    def ordinal(d: str) -> int:
        y, m, dd = (int(x) for x in d.split("-"))
        return date(y, m, dd).toordinal()
    out = []
    for i in range(1, len(days)):
        a, b = days[i - 1], days[i]
        gap = max(ordinal(b) - ordinal(a), 1)
        delta = per_day[b].get("checksum", 0) - per_day[a].get("checksum", 0)
        out.append((b, max(delta, 0) / gap, gap))
    return out


def _x_positions(days: list[str]) -> list[float]:
    """날짜 간격에 비례해 x 를 놓는다 — 스냅숏이 빠진 날이 사실대로 벌어진다."""
    def ordinal(d: str) -> int:
        y, m, dd = (int(x) for x in d.split("-"))
        return date(y, m, dd).toordinal()
    o = [ordinal(d) for d in days]
    span = max(o[-1] - o[0], 1)
    w = SVG_W - PAD_L - PAD_R
    return [PAD_L + w * (v - o[0]) / span for v in o]


def svg_chart(days: list[str], per_day, theme: str) -> str:
    c = THEMES[theme]
    setup = [per_day[d].get("setup", 0) for d in days]
    zipd = [per_day[d].get("zip", 0) for d in days]
    top, step = _axis(max([*setup, *zipd, 1]))
    xs = _x_positions(days)
    h = SVG_H - PAD_T - PAD_B

    def y(v: int) -> float:
        return PAD_T + h * (1 - v / top)

    def path(vals: list[int]) -> str:
        return " ".join(f"{x:.1f},{y(v):.1f}" for x, v in zip(xs, vals))

    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
        f'viewBox="0 0 {SVG_W} {SVG_H}" role="img" '
        f'aria-label="누적 다운로드 추이 — 설치 프로그램 {setup[-1]}건, zip {zipd[-1]}건">',
        f'<g font-family="{FONT}" font-size="11">',
    ]

    # 가로 눈금 — 간격의 배수라 숫자가 읽힌다
    for v in range(0, top + 1, step):
        yy = y(v)
        o.append(f'<line x1="{PAD_L}" y1="{yy:.1f}" x2="{SVG_W - PAD_R}" y2="{yy:.1f}" '
                 f'stroke="{c["grid"]}" stroke-width="1"/>')
        o.append(f'<text x="{PAD_L - 8}" y="{yy + 3.5:.1f}" fill="{c["text"]}" '
                 f'font-size="10" text-anchor="end">{v}</text>')

    # 두 계열 — zip 을 먼저 그려 설치선이 위로 온다
    for vals, key, width in ((zipd, "zip", 1.6), (setup, "setup", 2)):
        o.append(f'<polyline points="{path(vals)}" fill="none" stroke="{c[key]}" '
                 f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')

    # 선 끝에 이름을 직접 붙인다 — 범례를 따로 두지 않는 이유
    ends = sorted(((setup[-1], "setup", "설치"), (zipd[-1], "zip", "zip")),
                  key=lambda t: -t[0])
    prev_y = None
    for val, key, label in ends:
        yy = y(val)
        if prev_y is not None and abs(yy - prev_y) < 13:   # 겹치면 아래로 민다
            yy = prev_y + 13
        prev_y = yy
        o.append(f'<circle cx="{xs[-1]:.1f}" cy="{y(val):.1f}" r="2.6" fill="{c[key]}"/>')
        o.append(f'<text x="{xs[-1] + 8:.1f}" y="{yy + 4:.1f}" fill="{c[key]}" '
                 f'font-size="12" font-weight="600">{label} {val}</text>')

    # 날짜 — 처음·가운데·끝만(라벨이 겹치지 않는 최소한)
    picks = {0, len(days) // 2, len(days) - 1}
    for i in sorted(picks):
        anchor = "start" if i == 0 else ("end" if i == len(days) - 1 else "middle")
        o.append(f'<text x="{xs[i]:.1f}" y="{SVG_H - 8}" fill="{c["text"]}" '
                 f'font-size="10" text-anchor="{anchor}">{days[i][5:].replace("-", ".")}</text>')

    o += ["</g>", "</svg>", ""]
    return "\n".join(o)


def svg_runs(runs: list[tuple[str, float, int]], theme: str) -> str:
    """일별 실행 추정 — 막대. 누적 그래프(선)와 형태를 달리해 다른 값임을 알린다."""
    c = THEMES[theme]
    vals = [v for _, v, _ in runs]
    top, step = _axis(int(max([*vals, 1]) + 0.999))
    h = SVG_H - PAD_T - PAD_B
    xs = _x_positions([d for d, _, _ in runs])
    # 막대 폭 — 이웃 간격의 70%, 너무 얇지도 굵지도 않게
    gapx = min((xs[i + 1] - xs[i] for i in range(len(xs) - 1)), default=12)
    bw = max(2.0, min(14.0, gapx * 0.7))
    avg = sum(vals[-7:]) / max(len(vals[-7:]), 1)

    def y(v: float) -> float:
        return PAD_T + h * (1 - v / top)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
         f'viewBox="0 0 {SVG_W} {SVG_H}" role="img" '
         f'aria-label="일별 앱 실행 추정 — 최근 7일 평균 하루 {avg:.0f}회">',
         f'<g font-family="{FONT}" font-size="11">']
    for v in range(0, top + 1, step):
        yy = y(v)
        o.append(f'<line x1="{PAD_L}" y1="{yy:.1f}" x2="{SVG_W - PAD_R}" y2="{yy:.1f}" '
                 f'stroke="{c["grid"]}" stroke-width="1"/>')
        o.append(f'<text x="{PAD_L - 8}" y="{yy + 3.5:.1f}" fill="{c["text"]}" '
                 f'font-size="10" text-anchor="end">{v}</text>')
    base = y(0)
    for (d, v, gap), x in zip(runs, xs):
        yy = y(v)
        # 스냅숏이 빠져 나눠 그린 막대는 옅게 — 관측이 아니라 배분한 값이다
        op = ' opacity="0.55"' if gap > 1 else ""
        # 첫·마지막 막대는 축 밖으로 반쪽이 나간다 — 그림 안으로 물린다
        left = min(max(x - bw / 2, PAD_L), SVG_W - PAD_R - bw)
        o.append(f'<rect x="{left:.1f}" y="{yy:.1f}" width="{bw:.1f}" '
                 f'height="{max(base - yy, 0.8):.1f}" fill="{c["setup"]}"{op}/>')
    o.append(f'<line x1="{PAD_L}" y1="{y(avg):.1f}" x2="{SVG_W - PAD_R}" y2="{y(avg):.1f}" '
             f'stroke="{c["ink"]}" stroke-width="1" stroke-dasharray="4 3" opacity="0.6"/>')
    o.append(f'<text x="{SVG_W - PAD_R + 8}" y="{y(avg) + 4:.1f}" fill="{c["ink"]}" '
             f'font-size="12" font-weight="600">7일 평균 {avg:.0f}</text>')
    picks = sorted({0, len(runs) // 2, len(runs) - 1})
    for i in picks:
        anchor = "start" if i == 0 else ("end" if i == len(runs) - 1 else "middle")
        o.append(f'<text x="{xs[i]:.1f}" y="{SVG_H - 8}" fill="{c["text"]}" '
                 f'font-size="10" text-anchor="{anchor}">{runs[i][0][5:].replace("-", ".")}</text>')
    o += ["</g>", "</svg>", ""]
    return "\n".join(o)


def write_svgs(days: list[str], per_day) -> list[str]:
    """라이트·다크 두 벌을 쓴다. README 는 <picture> 로 갈라 쓴다."""
    if len(days) < 2:
        return []
    out = []
    runs = daily_runs(days, per_day)
    for theme in ("light", "dark"):
        p = CSV.parent / f"downloads-{theme}.svg"
        p.write_text(svg_chart(days, per_day, theme), encoding="utf-8")
        out.append(p.name)
        if runs:
            q = CSV.parent / f"runs-{theme}.svg"
            q.write_text(svg_runs(runs, theme), encoding="utf-8")
            out.append(q.name)
    return out


def chart_block(days: list[str], per_day, base: str = "stats/downloads") -> list[str]:
    """README 에 넣을 그래프 조각. 실제 그림은 write_svgs 가 만든 파일이다.

    점이 하나면 그리지 않는다(선이 성립하지 않고 축도 못 잡는다).
    """
    if len(days) < 2:
        return ["> 스냅숏이 하나뿐이라 아직 그래프를 그릴 수 없습니다 — 내일부터 채워집니다.", ""]
    return [
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{base}-dark.svg">',
        f'  <img alt="누적 다운로드 추이 — 설치 프로그램과 무설치 zip" src="{base}-light.svg" width="760">',
        "</picture>",
        "",
        "> 설치 프로그램은 **새로 설치한 사람**에 가깝고, zip 은 **인앱 업데이트**가 섞입니다.",
        "",
    ]


def runs_block(runs: list[tuple[str, float, int]], base: str = "runs") -> list[str]:
    """일별 실행 추정 절 — 그래프 + 요약 + 이 수치를 어떻게 읽어야 하는지."""
    if not runs:
        return ["> 스냅숏이 하나뿐이라 아직 실행 추정을 낼 수 없습니다.", ""]
    vals = [v for _, v, _ in runs]
    r7 = vals[-7:]
    avg7 = sum(r7) / len(r7)
    avg_all = sum(vals) / len(vals)
    return [
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{base}-dark.svg">',
        f'  <img alt="일별 앱 실행 추정" src="{base}-light.svg" width="760">',
        "</picture>",
        "",
        f"- 최근 7일 평균 **하루 {avg7:.0f}회** · 전체 기간 평균 하루 {avg_all:.0f}회"
        f" · 마지막 관측 **{runs[-1][1]:.0f}회**({runs[-1][0]})",
        "- **실행 횟수이지 사람 수가 아니다.** 한 사람이 하루 세 번 켜면 3으로 잡힌다.",
        "- 앱은 켜질 때 업데이트를 확인하고, 그 과정에서 `.sha256` 을 실제로 내려받는다"
        " — 업데이트가 없어도 받는다. 그래서 이 계열이 곧 실행 횟수다.",
        "- 스캐너·크롤러도 자산을 훑으므로 **상한으로** 읽는다. 옅은 막대는 스냅숏이 빠진"
        " 구간을 날수로 나눈 값이라 관측이 아니라 배분값이다.",
        "- 사람 수를 알 길은 아직 없다. 앱은 아무것도 보내지 않고(공개 README 의 약속),"
        " 클라우드는 로그인한 사람만 보이는데 그 수가 아직 개발 계정뿐이다.",
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
    write_svgs(days, per_day)          # README 가 가리키는 그림 — 매번 다시 그린다

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
              ("checksum", "체크섬 (앱이 켜질 때마다 1 — 아래 '사용 현황')")]
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

    out += ["## 사용 현황 — 일별 실행 추정", ""]
    out += runs_block(daily_runs(days, per_day))

    if len(days) > 1:
        out += ["## 일별 증가", "", "| 날짜 | 설치 | zip | 합계 |", "|---|---:|---:|---:|"]
        for i in range(1, len(days)):
            a, b = days[i - 1], days[i]
            ds = per_day[b].get("setup", 0) - per_day[a].get("setup", 0)
            dz = per_day[b].get("zip", 0) - per_day[a].get("zip", 0)
            out.append(f"| {b} | {ds:+d} | {dz:+d} | {ds + dz:+d} |")
        out.append("")

    out += ["## 누적 그래프", ""] + chart_block(days, per_day, base="downloads")

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
