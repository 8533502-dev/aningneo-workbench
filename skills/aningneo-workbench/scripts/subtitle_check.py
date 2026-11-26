#!/usr/bin/env python3
"""拿口播稿查字幕：口播稿是字幕的标准答案。

列出三类问题：
  必须改：字幕和稿子里最像的那句对不上（附哪几个字不一样）、专有名词写错或漏了
  建议：  稿子里找不到的句子（可能是临场多说的，确认一下）、一行太长要拆

例：
    python3 subtitle_check.py --srt 粗剪.srt --script 文稿/发布包.md --terms 专有名词.txt

退出码：有「必须改」返回 1，否则 0。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

PUNCT = re.compile(r"[\s　，。、！？；：“”‘’（）《》【】「」『』…—·,.!?;:'\"()\[\]<>~\-_/\\|*#`]+")
TIME = re.compile(r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})")


def normalize(text: str) -> str:
    return PUNCT.sub("", text).lower()


def parse_srt(text: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        for i, line in enumerate(lines):
            m = TIME.search(line)
            if m:
                cues.append({"index": len(cues) + 1, "start": m.group(1), "end": m.group(2),
                             "lines": lines[i + 1:]})
                break
    return cues


def script_text(markdown: str) -> str:
    """优先取「照着念」一节；没有就取「口播稿」表格的最后一列；再没有就用全文。"""
    section = re.search(r"^##\s*照着念\s*$(.*?)(?=^##\s|\Z)", markdown, re.M | re.S)
    hint = re.compile(r"^\s*（[^）]*）\s*$", re.M)  # 模板里的提示行
    if section and normalize(hint.sub("", section.group(1))):
        body = hint.sub("", section.group(1))
    else:
        table = re.search(r"^##\s*口播稿\s*$(.*?)(?=^##\s|\Z)", markdown, re.M | re.S)
        rows = []
        if table:
            for line in table.group(1).splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if line.strip().startswith("|") and len(cells) >= 2 and not set(cells[-1]) <= set("-: "):
                    rows.append(cells[-1])
            rows = rows[1:]  # 去掉表头
        body = "\n".join(rows) if rows else markdown
    body = re.sub(r"【[^】]*】", "", body)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    return body


def best_window(cue: str, script: str) -> tuple[float, int, int]:
    """在稿子里找和这句字幕最像的一段，返回 (相似度, 起点, 终点)。"""
    if not script:
        return 0.0, 0, 0
    length = len(cue)
    votes: dict[int, int] = {}
    for i in range(len(cue) - 1):
        gram = cue[i:i + 2]
        pos = script.find(gram)
        while pos != -1:
            start = max(0, pos - i)
            votes[start] = votes.get(start, 0) + 1
            pos = script.find(gram, pos + 1)
    if votes:  # 只细看命中最多的几个起点，长稿子也很快
        starts = sorted(votes, key=votes.get, reverse=True)[:12]
    else:
        starts = list(range(0, max(1, len(script) - length + 1), max(1, length // 2)))
    best = (0.0, 0, 0)
    for s in starts:
        for delta in (-2, -1, 0, 1, 2):
            a = max(0, s + delta)
            for extra in (-1, 0, 1, 2):
                b = min(len(script), a + length + extra)
                ratio = difflib.SequenceMatcher(None, cue, script[a:b], autojunk=False).ratio()
                if ratio > best[0]:
                    best = (ratio, a, b)
    return best


def diff_pieces(cue: str, ref: str) -> list[str]:
    pieces = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, cue, ref, autojunk=False).get_opcodes():
        if op != "equal":
            pieces.append(f"字幕「{cue[a1:a2] or '（无）'}」↔ 稿子「{ref[b1:b2] or '（无）'}」")
    return pieces


def check(cues: list[dict], script_raw: str, terms: list[str], max_chars: int,
          match_floor: float = 0.6) -> list[dict]:
    script = normalize(script_raw)
    norm_terms = [(t, normalize(t)) for t in terms if normalize(t)]
    issues = []
    for cue in cues:
        raw = "".join(cue["lines"])
        text = normalize(raw)
        where = f"第 {cue['index']} 条 {cue['start']}"
        for line in cue["lines"]:
            if len(line.strip()) > max_chars:
                issues.append({"level": "建议", "where": where,
                               "message": f"一行 {len(line.strip())} 个字，超过 {max_chars}，拆成两行或两条：{line.strip()}"})
        if not text:
            continue
        ratio, a, b = best_window(text, script)
        ref = script[a:b]
        if ratio < match_floor:
            issues.append({"level": "建议", "where": where,
                           "message": f"稿子里找不到这句（可能是临场多说的，确认一下）：{raw}"})
            continue
        if text != ref and ratio < 0.999:
            pieces = diff_pieces(text, ref)
            if pieces:
                issues.append({"level": "必须改", "where": where,
                               "message": f"和稿子对不上：{'；'.join(pieces)}（字幕：{raw}）"})
        for term, norm in norm_terms:
            if norm in ref and norm not in text:
                issues.append({"level": "必须改", "where": where,
                               "message": f"专有名词「{term}」写错或漏了（字幕：{raw}）"})
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拿口播稿查字幕")
    parser.add_argument("--srt", required=True)
    parser.add_argument("--script", required=True, help="口播稿（发布包.md 或纯文本）")
    parser.add_argument("--terms", help="专有名词表，一行一个")
    parser.add_argument("--max-chars", type=int, default=18, help="一行最多几个字，默认 18")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    cues = parse_srt(Path(args.srt).read_text(encoding="utf-8-sig"))
    script_raw = script_text(Path(args.script).read_text(encoding="utf-8"))
    terms = []
    if args.terms:
        terms = [line.strip() for line in Path(args.terms).read_text(encoding="utf-8").splitlines() if line.strip()]
    issues = check(cues, script_raw, terms, args.max_chars)
    must = sum(i["level"] == "必须改" for i in issues)

    if args.format == "json":
        print(json.dumps({"cues": len(cues), "must_fix": must, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        print(f"字幕 {len(cues)} 条 · 必须改 {must} · 建议 {len(issues) - must}")
        for issue in issues:
            print(f"  [{issue['level']}] {issue['where']}：{issue['message']}")
        if not issues:
            print("  字幕和稿子对得上。")
    return 1 if must else 0


if __name__ == "__main__":
    sys.exit(main())
