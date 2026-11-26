#!/usr/bin/env python3
"""给自媒体工作台体检。只读，不改任何文件。

查这些：
  P0（必须修）：核心文件缺了、工作台里有密钥文件或密钥文本
  P1（该修）：推荐文件缺了、AGENTS.md 里写的路径不存在、CLAUDE.md 没指向 AGENTS.md、
              同一类纠正到 3 次还没进待升级、晨报 / 热点超过 2 天没更新
  P2（提醒）：还有【待补充】、还没有晨报 / 热点、日程过了时间没确认做完

例：
    python3 check_workbench.py --root ~/自媒体工作台
    python3 check_workbench.py --root ~/自媒体工作台 --format json

退出码：有 P0 返回 2，否则返回 0。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

CORE_FILES = [
    "AGENTS.md",
    "01-我/我是谁.md",
    "01-我/说话卡.md",
    "00-总台/成长/纠正记录.md",
    "00-总台/成长/待升级.md",
    "00-总台/授权.md",
    "05-选题与排期/目标.md",
    "05-选题与排期/日程表.md",
]
RECOMMENDED_FILES = [
    "01-我/账号定位.md",
    "01-我/我用过的工具.md",
    "00-总台/成长/效果账本.md",
    "00-总台/员工/岗位表.md",
    "00-总台/员工/任务记录.md",
    "00-总台/定时任务.md",
    "02-方法/写稿手册.md",
    "02-方法/选题标准.md",
    "02-方法/剪辑自检表.md",
    "05-选题与排期/选题池.md",
    "05-选题与排期/内容总表.md",
    "06-复盘/粉丝记录.md",
    "00-总台/模板/晨报.md",
    "00-总台/模板/发布包.md",
    "00-总台/模板/今日热点.md",
]
PLACEHOLDER_FILES = ["01-我/我是谁.md", "01-我/账号定位.md", "05-选题与排期/目标.md"]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
SECRET_NAME = re.compile(
    r"(^\.env(\..+)?$|\.pem$|\.p12$|\.key$|^id_rsa|api[_-]?key|credentials.*\.json$|secret)",
    re.IGNORECASE,
)
SECRET_TEXT = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
]
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".toml", ".ini", ".env"}
DATED_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
DATED_DIR = re.compile(r"^(\d{4}-\d{2}-\d{2})")
FENCE = re.compile(r"```.*?```", re.DOTALL)
CATEGORY = re.compile(r"类别[:：]\s*([^\s（(]+)")
PATH_IN_TICKS = re.compile(r"`((?:0\d-|AGENTS|CLAUDE)[^`\s]*)`")


def finding(level: str, code: str, path: str, message: str) -> dict:
    return {"level": level, "code": code, "path": path, "message": message}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def parse_table(text: str, must_have: str) -> list[dict[str, str]]:
    """找第一张表头里有 must_have 这一列的 Markdown 表，返回每行 {列名: 值}。"""
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


def check_files(root: Path) -> list[dict]:
    out = []
    for rel in CORE_FILES:
        if not (root / rel).is_file():
            out.append(finding("P0", "MISSING_CORE_FILE", rel, "核心文件缺了，跑 init_workbench.py --apply 补上"))
    for rel in RECOMMENDED_FILES:
        if not (root / rel).is_file():
            out.append(finding("P1", "MISSING_RECOMMENDED_FILE", rel, "推荐文件缺了"))
    claude = root / "CLAUDE.md"
    if claude.is_file() and "AGENTS.md" not in read(claude):
        out.append(finding("P1", "CLAUDE_ENTRY_MISMATCH", "CLAUDE.md", "CLAUDE.md 没有指向 AGENTS.md，两份规则可能打架"))
    return out


def check_secrets(root: Path) -> list[dict]:
    out = []
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if SECRET_NAME.search(path.name):
            out.append(finding("P0", "SECRET_FILE", rel, "像是密钥文件，挪出工作台，放环境变量或钥匙串"))
            continue
        if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size < 2_000_000:
            text = read(path)
            if any(p.search(text) for p in SECRET_TEXT):
                out.append(finding("P0", "SECRET_TEXT", rel, "文件里像是写了密钥，删掉，只记放在哪"))
    return out


def check_paths(root: Path) -> list[dict]:
    out = []
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return out
    for match in PATH_IN_TICKS.finditer(read(agents)):
        ref = match.group(1).rstrip("/，。")
        if any(ch in ref for ch in "<>{}*") or "YYYY" in ref or "编号" in ref:
            continue
        if not (root / ref).exists():
            out.append(finding("P1", "BROKEN_PATH", "AGENTS.md", f"写了 `{ref}`，但这个路径不存在"))
    return out


def check_corrections(root: Path) -> list[dict]:
    log = root / "00-总台/成长/纠正记录.md"
    upgrades = read(root / "00-总台/成长/待升级.md")
    if not log.is_file():
        return []
    counts = Counter(CATEGORY.findall(FENCE.sub("", read(log))))
    out = []
    for category, n in sorted(counts.items()):
        if n >= 3 and category not in upgrades:
            out.append(finding("P1", "CORRECTION_NEEDS_UPGRADE", "00-总台/成长/纠正记录.md",
                               f"「{category}」已经纠正 {n} 次，还没写进待升级"))
    return out


def latest_date(folder: Path, pattern: re.Pattern, want_dir: bool) -> dt.date | None:
    if not folder.is_dir():
        return None
    dates = []
    for child in folder.iterdir():
        if child.is_dir() != want_dir:
            continue
        m = pattern.match(child.name)
        if m:
            try:
                dates.append(dt.date.fromisoformat(m.group(1)))
            except ValueError:
                pass
    return max(dates) if dates else None


def check_freshness(root: Path, today: dt.date) -> list[dict]:
    out = []
    for rel, pattern, want_dir, label in (
        ("00-总台/晨报", DATED_FILE, False, "晨报"),
        ("03-调研/热点", DATED_DIR, True, "今日热点"),
    ):
        last = latest_date(root / rel, pattern, want_dir)
        if last is None:
            out.append(finding("P2", "NOT_STARTED", rel, f"还没有{label}，定时任务设好后第二天会有"))
        elif (today - last).days > 2:
            out.append(finding("P1", "STALE", rel, f"{label}最后一次是 {last}，已经 {(today - last).days} 天没更新，看看定时任务是不是断了"))
    return out


def check_placeholders(root: Path) -> list[dict]:
    out = []
    for rel in PLACEHOLDER_FILES:
        n = read(root / rel).count("【待补充")
        if n:
            out.append(finding("P2", "PLACEHOLDER", rel, f"还有 {n} 处【待补充】"))
    return out


def check_schedule(root: Path, today: dt.date) -> list[dict]:
    rows = parse_table(read(root / "05-选题与排期/日程表.md"), "事项")
    pending = []
    for row in rows:
        try:
            day = dt.date.fromisoformat(row.get("日期", ""))
        except ValueError:
            continue
        if day < today and row.get("类别") != "竞品期" and not row.get("完成"):
            pending.append(f"{row.get('日期')} {row.get('事项', '')}")
    if not pending:
        return []
    return [finding("P2", "UNCONFIRMED_SCHEDULE", "05-选题与排期/日程表.md",
                    f"{len(pending)} 件过了时间还没确认做完：" + "；".join(pending[:5]))]


def audit(root: Path, today: dt.date) -> dict:
    findings = (check_files(root) + check_secrets(root) + check_paths(root)
                + check_corrections(root) + check_freshness(root, today)
                + check_placeholders(root) + check_schedule(root, today))
    summary = {level: sum(f["level"] == level for f in findings) for level in ("P0", "P1", "P2")}
    status = "broken" if summary["P0"] else "needs_attention" if summary["P1"] else "healthy"
    return {"root": str(root), "date": today.isoformat(), "status": status,
            "summary": summary, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自媒体工作台体检（只读）")
    parser.add_argument("--root", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--today", help="按哪天算，默认今天，YYYY-MM-DD")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"出错：{root} 不是文件夹", file=sys.stderr)
        return 2
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    report = audit(root, today)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        names = {"healthy": "健康", "needs_attention": "有该修的", "broken": "有必须修的"}
        s = report["summary"]
        print(f"工作台体检 · {report['date']} · {names[report['status']]}（P0 {s['P0']} / P1 {s['P1']} / P2 {s['P2']}）")
        for f in report["findings"]:
            print(f"  [{f['level']}] {f['path']}：{f['message']}")
        if not report["findings"]:
            print("  没发现问题。")
    return 2 if report["summary"]["P0"] else 0


if __name__ == "__main__":
    sys.exit(main())
