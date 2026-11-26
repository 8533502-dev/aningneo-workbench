#!/usr/bin/env python3
"""口播粗剪：按停顿切掉空白，两边留一点气口。

默认只预览切点和剪完的时长；加 --apply --out 才出片。原片不动。
口误、重说这类要对着稿子判断的，用剪辑软件删，或者把要留的片段写进项目.md。

需要 ffmpeg 和 ffprobe。

例：
    python3 rough_cut.py 素材/原片/口播.mp4
    python3 rough_cut.py 素材/原片/口播.mp4 --min-silence 0.6 --keep 0.15 --apply --out 剪辑/项目/粗剪.mp4
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def duration_of(video: Path) -> float:
    result = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)])
    return float(json.loads(result.stdout or "{}").get("format", {}).get("duration", 0) or 0)


def detect_silences(video: Path, noise_db: float, min_silence: float) -> list[tuple[float, float]]:
    log = run(["ffmpeg", "-nostats", "-i", str(video), "-af",
               f"silencedetect=n={noise_db}dB:d={min_silence}", "-f", "null", "-"]).stderr
    return parse_silences(log)


def parse_silences(log: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", log)]
    return [(max(0.0, s), e) for s, e in zip(starts, ends)]


def keep_segments(silences: list[tuple[float, float]], duration: float, keep: float,
                  min_segment: float) -> list[tuple[float, float]]:
    """把停顿去掉、两边各留 keep 秒，返回要保留的 [(开始, 结束)]。"""
    segments, cursor = [], 0.0
    for start, end in sorted(silences):
        cut_from, cut_to = start + keep, end - keep
        if cut_to - cut_from <= 0.05:
            continue
        if cut_from > cursor:
            segments.append((cursor, cut_from))
        cursor = max(cursor, cut_to)
    if duration - cursor > 0:
        segments.append((cursor, duration))
    return [(round(a, 3), round(b, 3)) for a, b in segments if b - a >= min_segment]


def build_filter(segments: list[tuple[float, float]]) -> str:
    parts, labels = [], []
    for i, (a, b) in enumerate(segments):
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]")
    return ";".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="口播粗剪：去停顿（默认只预览）")
    parser.add_argument("video")
    parser.add_argument("--min-silence", type=float, default=0.6, help="超过几秒的停顿要切，默认 0.6")
    parser.add_argument("--noise", type=float, default=-35.0, help="低于多少 dB 算安静，默认 -35")
    parser.add_argument("--keep", type=float, default=0.15, help="切口两边各留几秒气口，默认 0.15")
    parser.add_argument("--min-segment", type=float, default=0.2, help="短于几秒的碎片丢掉，默认 0.2")
    parser.add_argument("--apply", action="store_true", help="真的出片")
    parser.add_argument("--out", help="出片路径（--apply 时必填）")
    parser.add_argument("--plan", help="把切点存成 JSON（可选）")
    args = parser.parse_args(argv)

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("出错：没装 ffmpeg / ffprobe（macOS：brew install ffmpeg）", file=sys.stderr)
        return 3
    video = Path(args.video).expanduser()
    if not video.is_file():
        print(f"出错：找不到 {video}", file=sys.stderr)
        return 2

    total = duration_of(video)
    silences = detect_silences(video, args.noise, args.min_silence)
    segments = keep_segments(silences, total, args.keep, args.min_segment)
    kept = sum(b - a for a, b in segments)
    print(f"{'APPLY' if args.apply else 'PREVIEW（只预览，不出片）'}")
    print(f"原片 {total:.2f} 秒，找到 {len(silences)} 段停顿，保留 {len(segments)} 段，剪完约 {kept:.2f} 秒（省 {total - kept:.2f} 秒）")
    for a, b in segments[:40]:
        print(f"  留 {a:8.2f} → {b:8.2f}")
    if len(segments) > 40:
        print(f"  ……还有 {len(segments) - 40} 段")
    if args.plan:
        Path(args.plan).write_text(json.dumps({"source": str(video), "segments": segments},
                                              ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.apply:
        print("\n看着合适，再加 --apply --out <文件> 出片。")
        return 0
    if not args.out:
        print("出错：--apply 要配 --out", file=sys.stderr)
        return 2
    if not segments:
        print("出错：没有可保留的片段，调小 --noise 或 --min-silence 再试", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser()
    if out.resolve() == video.resolve():
        print("出错：输出不能覆盖原片", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    result = run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-filter_complex", build_filter(segments),
                  "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                  "-c:a", "aac", "-b:a", "192k", str(out)])
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        return 1
    print(f"出好了：{out}（{duration_of(out):.2f} 秒）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
