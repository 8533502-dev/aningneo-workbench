#!/usr/bin/env python3
"""建一个新的自媒体工作台骨架。

默认只预览，打印要建哪些文件；加 --apply 才写。已有的文件一个都不覆盖。

例：
    python3 init_workbench.py --root ~/自媒体工作台 --name "我的账号"
    python3 init_workbench.py --root ~/自媒体工作台 --name "我的账号" --agent claude-code --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKELETON = SKILL_ROOT / "assets" / "骨架"
TEMPLATES = SKILL_ROOT / "assets" / "模板"
TEMPLATE_TARGET = Path("00-总台") / "模板"
CLAUDE_ENTRY = "@AGENTS.md\n"
AGENT_CHOICES = ("generic", "claude-code", "codex", "workbuddy", "all")


def plan_files(name: str, today: str, agent: str) -> list[tuple[Path, str]]:
    """返回 [(相对路径, 内容)]。"""
    plan: list[tuple[Path, str]] = []
    for source in sorted(SKELETON.rglob("*")):
        if source.is_file() and source.name != ".DS_Store":
            plan.append((source.relative_to(SKELETON), render(source, name, today)))
    for source in sorted(TEMPLATES.glob("*.md")):
        plan.append((TEMPLATE_TARGET / source.name, render(source, name, today)))
    if agent in ("claude-code", "all"):
        plan.append((Path("CLAUDE.md"), CLAUDE_ENTRY))
    return plan


def render(source: Path, name: str, today: str) -> str:
    text = source.read_text(encoding="utf-8")
    return text.replace("{{账号名}}", name).replace("{{今天}}", today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建自媒体工作台骨架（默认只预览）")
    parser.add_argument("--root", required=True, help="工作台文件夹")
    parser.add_argument("--name", default="我的账号", help="账号名")
    parser.add_argument("--agent", choices=AGENT_CHOICES, default="generic",
                        help="claude-code / all 会多建一个 CLAUDE.md（内容只有 @AGENTS.md）")
    parser.add_argument("--date", help="写进文件的日期，默认今天，格式 YYYY-MM-DD")
    parser.add_argument("--apply", action="store_true", help="真的写入（不加就只预览）")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    if root.exists() and not root.is_dir():
        print(f"出错：{root} 已经存在，而且不是文件夹", file=sys.stderr)
        return 2
    today = args.date or dt.date.today().isoformat()

    plan = plan_files(args.name, today, args.agent)
    create = [(rel, text) for rel, text in plan if not (root / rel).exists()]
    skip = [rel for rel, _ in plan if (root / rel).exists()]

    mode = "APPLY（写入）" if args.apply else "PREVIEW（只预览，没有写任何文件）"
    print(f"{mode}")
    print(f"工作台：{root}")
    print(f"账号名：{args.name}　Agent：{args.agent}　日期：{today}")
    print(f"要新建 {len(create)} 个文件，已存在跳过 {len(skip)} 个")
    for rel, _ in create:
        print(f"  + {rel.as_posix()}")
    for rel in skip:
        print(f"  = {rel.as_posix()}（已存在，不动）")

    if not args.apply:
        print("\n看过没问题，再加 --apply 写入。")
        return 0

    for rel, text in create:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:  # x：已存在就报错，绝不覆盖
            handle.write(text)
    print(f"\n已写入 {len(create)} 个文件。下一步：填 01-我/我是谁.md，再跑 check_workbench.py 体检。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
