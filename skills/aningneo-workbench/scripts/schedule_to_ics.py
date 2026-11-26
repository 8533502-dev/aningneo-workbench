#!/usr/bin/env python3
"""把 05-选题与排期/日程表.md 转成 .ics，导入或订阅到苹果日历、Google 日历、Outlook。

- 每件事的编号按「日期 + 开始 + 事项」算，重复导入会更新原来那条，不会重复。
- 「开始」写「全天」的（例如竞品期）建成全天事件，「结束」写结束日期。
- 「完成」那一列有 ✅ 的，标题前加「✅ 」。
- 时间按本地时间写（不带时区），日历会按你电脑的时区显示。

例：
    python3 schedule_to_ics.py --root ~/自媒体工作台 --out 05-选题与排期/日程.ics
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

SCHEDULE = Path("05-选题与排期") / "日程表.md"
DONE_MARKS = ("✅", "已完成", "做完", "是")


def parse_table(text: str, must_have: str = "事项") -> list[dict[str, str]]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and must_have in line:
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                cells += [""] * (len(header) - len(cells))
                rows.append(dict(zip(header, cells)))
            return rows
    return []


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def fold(line: str) -> str:
    """按 iCalendar 规定，每行不超过 75 个字节，超出的折到下一行。"""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode("utf-8"))
            current = b""
        current += encoded
    out.append(current.decode("utf-8"))
    return "\r\n ".join(out)


def parse_time(value: str) -> dt.time | None:
    try:
        hour, minute = value.replace("：", ":").split(":")
        return dt.time(int(hour), int(minute))
    except ValueError:
        return None


def build_events(rows: list[dict[str, str]]) -> tuple[list[list[str]], list[str]]:
    events, warnings = [], []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for row in rows:
        date_text, start_text = row.get("日期", ""), row.get("开始", "")
        item = row.get("事项", "")
        try:
            day = dt.date.fromisoformat(date_text)
        except ValueError:
            if date_text:
                warnings.append(f"跳过：日期看不懂「{date_text}」")
            continue
        uid = hashlib.sha1(f"{date_text}|{start_text}|{item}".encode("utf-8")).hexdigest()[:20]
        done = any(mark in row.get("完成", "") for mark in DONE_MARKS)
        category = row.get("类别", "")
        summary = ("✅ " if done else "") + (f"[{category}] " if category else "") + item
        event = ["BEGIN:VEVENT", f"UID:{uid}@aningneo-workbench", f"DTSTAMP:{stamp}"]
        if start_text == "全天" or not start_text:
            try:
                last = dt.date.fromisoformat(row.get("结束", ""))
            except ValueError:
                last = day
            event += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{last + dt.timedelta(days=1):%Y%m%d}"]
        else:
            start = parse_time(start_text)
            if start is None:
                warnings.append(f"跳过：{date_text} 的开始时间看不懂「{start_text}」")
                continue
            begin = dt.datetime.combine(day, start)
            end_time = parse_time(row.get("结束", ""))
            finish = dt.datetime.combine(day, end_time) if end_time else begin + dt.timedelta(minutes=30)
            if finish <= begin:
                finish = begin + dt.timedelta(minutes=30)
            event += [f"DTSTART:{begin:%Y%m%dT%H%M%S}", f"DTEND:{finish:%Y%m%dT%H%M%S}"]
        event.append(f"SUMMARY:{escape(summary)}")
        if row.get("说明"):
            event.append(f"DESCRIPTION:{escape(row['说明'])}")
        event.append("END:VEVENT")
        events.append(event)
    return events, warnings


def to_ics(events: list[list[str]], calendar_name: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//aningneo-workbench//schedule//ZH",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{escape(calendar_name)}"]
    for event in events:
        lines += event
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日程表.md → .ics")
    parser.add_argument("--root", help="工作台文件夹（读里面的 05-选题与排期/日程表.md）")
    parser.add_argument("--schedule", help="直接指定日程表文件")
    parser.add_argument("--out", required=True, help="输出的 .ics；相对路径按 --root 算")
    parser.add_argument("--calendar-name", default="自媒体排期")
    args = parser.parse_args(argv)

    if not args.schedule and not args.root:
        parser.error("要给 --root 或 --schedule")
    root = Path(args.root).expanduser() if args.root else Path.cwd()
    schedule = Path(args.schedule).expanduser() if args.schedule else root / SCHEDULE
    if not schedule.is_file():
        print(f"出错：找不到日程表 {schedule}", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = root / out

    events, warnings = build_events(parse_table(schedule.read_text(encoding="utf-8")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_ics(events, args.calendar_name), encoding="utf-8", newline="")
    print(f"写好了：{out}（{len(events)} 件事）")
    for warning in warnings:
        print(f"  ! {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
