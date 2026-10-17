"""《艾希：续》摩点众筹自动统计（GitHub Actions 版，双模式）。

支持两个互相独立的数据集，各写各的表：

  --mode 8h      每天 08:00 / 16:00 / 23:58（北京时间）
                 → data/records-8h.tsv + index.html
  --mode hourly  每小时整点
                 → data/records-hourly.tsv + hourly.html

单次运行做的事：
  1. 抓取摩点项目页当前总金额 / 总人数
  2. 读取对应 TSV 最后一行，计算「较上次净增长」
  3. 追加一行（数据源 / 归档）
  4. 重建对应 HTML（手机可看的网页表格）
  5. 若数据无变化则跳过写入，避免刷空提交

时区统一用 Asia/Shanghai（UTC+8）。本脚本只依赖标准库，可在任意环境运行。
"""

import argparse
import datetime as dt
import io
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_URL = "https://zhongchou.modian.com/item/160465.html"
PROJECT_ID = "160465"
TZ = ZoneInfo("Asia/Shanghai")

BASE = Path(__file__).resolve().parent

MODES = {
    "8h": {
        "tsv": BASE / "data" / "records-8h.tsv",
        "html": BASE / "index.html",
        "title": "《艾希：续》众筹统计表（每天 3 次）",
        "note": "每天 08:00 / 16:00 / 23:58（北京时间）自动统计",
        "other": "hourly.html",
        "other_label": "切换到「每小时」表",
    },
    "hourly": {
        "tsv": BASE / "data" / "records-hourly.tsv",
        "html": BASE / "hourly.html",
        "title": "《艾希：续》众筹统计表（每小时）",
        "note": "每小时整点自动统计",
        "other": "index.html",
        "other_label": "切换到「每天 3 次」表",
    },
}
MODE = "8h"

TSV = MODES[MODE]["tsv"]
HTML = MODES[MODE]["html"]

HEADERS = ["统计时间", "众筹总人数", "较上一次统计净增长人数",
           "众筹总金额", "较上一次统计净增长金额",
           "较前一日最后一次净增长人数", "较前一日最后一次净增长金额"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

RE_RAISED = re.compile(
    rf"backer_money\s*=\s*['\"]{re.escape(PROJECT_ID)}['\"][^>]*>\s*([\d,]+(?:\.\d+)?)")
RE_BACKERS = re.compile(
    rf"backer_count\s*=\s*['\"]{re.escape(PROJECT_ID)}['\"][^>]*>\s*([\d,]+)")
RE_GOAL = re.compile(r"目标金额\s*¥\s*([\d,]+)")

DASH = "\u2014"


# ---------------------------------------------------------------- 抓取
def fetch_current() -> tuple[dt.datetime, int, float, float | None]:
    req = urllib.request.Request(PROJECT_URL, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=40) as resp:
        raw = resp.read().decode("utf-8", "replace")

    m = RE_RAISED.search(raw)
    b = RE_BACKERS.search(raw)
    if not m or not b:
        raise RuntimeError("页面解析失败：找不到 backer_money / backer_count")

    goal = RE_GOAL.search(raw)
    return (
        dt.datetime.now(TZ),
        int(b.group(1).replace(",", "")),
        float(m.group(1).replace(",", "")),
        float(goal.group(1).replace(",", "")) if goal else None,
    )


# ---------------------------------------------------------------- TSV 读写
def read_tsv() -> list[tuple[str, int, float]]:
    if not TSV.exists():
        return []
    rows = []
    with TSV.open(encoding="utf-8-sig", newline="") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 4:
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", cols[0]):
                continue
            try:
                rows.append((cols[0], int(cols[1].replace(",", "")),
                             float(cols[3].replace("¥", "").replace(",", ""))))
            except ValueError:
                continue
    return rows


def fmt_int(v: int) -> str:
    return f"{v:+,}"


def fmt_money(v: float) -> str:
    return f"+¥{v:,.2f}" if v >= 0 else f"-¥{abs(v):,.2f}"


def daily_delta_map(rows: list[tuple[str, int, float]]) -> dict[int, tuple[str, str]]:
    """返回 {行索引: (当日人数净增文本, 当日金额净增文本)}，仅当日最后一行有值。"""
    out: dict[int, tuple[str, str]] = {}
    last_of_day: dict[str, int] = {}
    for i, (ts, _, _) in enumerate(rows):
        last_of_day[ts[:10]] = i

    days = sorted(last_of_day)
    for pos, day in enumerate(days):
        i = last_of_day[day]
        if pos == 0:
            out[i] = (DASH, DASH)
            continue
        prev_i = last_of_day[days[pos - 1]]
        out[i] = (fmt_int(rows[i][1] - rows[prev_i][1]),
                  fmt_money(rows[i][2] - rows[prev_i][2]))
    return out


def write_tsv(rows: list[tuple[str, int, float]]) -> None:
    daily = daily_delta_map(rows)
    buf = io.StringIO()
    buf.write("\t".join(HEADERS) + "\n")
    prev = None
    for i, (ts, backers, raised) in enumerate(rows):
        if prev is None:
            d_people, d_money = DASH, DASH
        else:
            d_people = fmt_int(backers - prev[1])
            d_money = fmt_money(raised - prev[2])
        dd = daily.get(i, ("", ""))
        buf.write("\t".join([ts, f"{backers:,}", d_people,
                             f"¥{raised:,.2f}", d_money, dd[0], dd[1]]) + "\n")
        prev = (ts, backers, raised)
    TSV.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------- HTML
def build_html(rows: list[tuple[str, int, float]], latest_ts: str) -> str:
    daily = daily_delta_map(rows)
    body = []
    prev = None
    for i, (ts, backers, raised) in enumerate(rows):
        if prev is None:
            dp = dm = f'<td class="none">{DASH}</td>'
        else:
            dvp, dvm = backers - prev[1], raised - prev[2]
            dp = f'<td class="{"up" if dvp >= 0 else "down"}">{fmt_int(dvp)}</td>'
            dm = f'<td class="{"up" if dvm >= 0 else "down"}">{fmt_money(dvm)}</td>'
        dd = daily.get(i, ("", ""))
        if dd == ("", ""):
            ddp = ddm = "<td></td>"
        elif dd[0] == DASH:
            ddp = ddm = f'<td class="none">{DASH}</td>'
        else:
            ddp = f'<td class="up">{dd[0]}</td>'
            ddm = f'<td class="up">{dd[1]}</td>'
        body.append(
            "      <tr>\n"
            f'        <td class="time">{ts}</td>\n'
            f'        <td>{backers:,}</td>\n'
            f"        {dp}\n"
            f'        <td>¥{raised:,.2f}</td>\n'
            f"        {dm}\n"
            f"        {ddp}\n"
            f"        {ddm}\n"
            "      </tr>"
        )
        prev = (ts, backers, raised)

    thead = ("    <thead>\n      <tr>\n"
             + "\n".join(f"        <th>{h}</th>" for h in HEADERS)
             + "\n      </tr>\n    </thead>")
    tbody = "    <tbody>\n" + "\n".join(body) + "\n    </tbody>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>《艾希：续》众筹统计表</title>
<style>
  body {{ margin: 16px; font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
         background: #fff; color: #1a1a1a; }}
  h1 {{ font-size: 19px; font-weight: 600; margin: 0 0 4px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 12px; }}
  .wrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; font-variant-numeric: tabular-nums; min-width: 720px; }}
  th, td {{ padding: 9px 13px; border-bottom: 1px solid #e3e3e3; white-space: nowrap; font-size: 14px; }}
  th {{ text-align: center; background: #f5f7fa; border-bottom: 2px solid #c9d2dd; font-weight: 600; }}
  td {{ text-align: right; }}
  tbody tr:nth-child(even) {{ background: #fafbfc; }}
  .time {{ font-family: Consolas, "Courier New", monospace; }}
  .up {{ color: #1f7a3d; }}
  .down {{ color: #b3261e; }}
  .none {{ color: #999; }}
  .nav {{ margin: 0 0 12px; font-size: 13.5px; }}
  .nav a {{ color: #0969da; text-decoration: none; border: 1px solid #d0d7de;
            border-radius: 6px; padding: 3px 10px; }}
  .nav a:hover {{ background: #f3f4f6; }}
</style>
</head>
<body>
  <h1>{MODES[MODE]["title"]}</h1>
  <div class="sub">数据来源：摩点项目页 160465 &nbsp;|&nbsp; 最新统计：{latest_ts} &nbsp;|&nbsp; {MODES[MODE]["note"]}（GitHub Actions 自动更新）</div>
  <div class="nav"><a href="{MODES[MODE]["other"]}">{MODES[MODE]["other_label"]} →</a></div>
  <div class="wrap">
  <table>
    {thead}
    {tbody}
  </table>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------- 主流程
def parse_mode() -> None:
    """解析 --mode，把全局路径切换到对应数据集。"""
    global MODE, TSV, HTML
    ap = argparse.ArgumentParser(description="艾希：续 摩点众筹统计")
    ap.add_argument("--mode", choices=sorted(MODES), default=None,
                    help="8h=每天3次；hourly=每小时")
    args, _ = ap.parse_known_args()
    if args.mode:
        MODE = args.mode
        TSV = MODES[MODE]["tsv"]
        HTML = MODES[MODE]["html"]


def main() -> int:
    parse_mode()
    TSV.parent.mkdir(parents=True, exist_ok=True)

    now, backers, raised, goal = fetch_current()
    rows = read_tsv()

    # 无历史：写入首条（首次启用某个 mode 时走这里）
    if not rows:
        rows = [(now.strftime("%Y-%m-%d %H:%M:%S"), backers, raised)]
        write_tsv(rows)
        HTML.write_text(build_html(rows, rows[-1][0]), encoding="utf-8")
        print(f"[{MODE}] initialized {TSV.name}: {rows[-1]}")
        return 0

    last_ts, last_backers, last_raised = rows[-1]

    # 数据没变化：跳过，避免空提交
    if backers == last_backers and abs(raised - last_raised) < 0.005:
        print(f"[{MODE}] no change since {last_ts}; skip")
        return 0

    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    rows.append((stamp, backers, raised))
    write_tsv(rows)
    HTML.write_text(build_html(rows, stamp), encoding="utf-8")

    dp, dm = backers - last_backers, raised - last_raised
    print(f"[{MODE}] appended {stamp}: {backers:,} people / ¥{raised:,.2f} "
          f"({fmt_int(dp)} / {fmt_money(dm)}) -> {TSV.name} + {HTML.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
