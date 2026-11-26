#!/usr/bin/env python3
"""剪完自检：量响度、静音、黑场，抽首帧和总览图，写一份自检报告。

AI 听不到声音：这里量出来的是数，画面靠看抽出来的截图判断。
报告里「看截图判断的」那一节留给 AI 照 02-方法/剪辑自检表.md 逐条填。

需要 ffmpeg 和 ffprobe。

例：
    python3 check_video.py 剪辑/项目/输出/预览v1.mp4 --out 剪辑/项目/自检
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


def probe(video: Path) -> dict:
    result = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)])
    data = json.loads(result.stdout or "{}")
    info = {"duration": float(data.get("format", {}).get("duration", 0) or 0),
            "width": None, "height": None, "fps": None, "has_audio": False}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and info["width"] is None:
            info["width"], info["height"] = stream.get("width"), stream.get("height")
            num, _, den = (stream.get("avg_frame_rate") or "0/1").partition("/")
            try:
                info["fps"] = round(float(num) / float(den or 1), 2)
            except (ValueError, ZeroDivisionError):
                info["fps"] = None
        if stream.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def parse_ebur128(text: str) -> dict:
    """从 ffmpeg ebur128 的汇总里取整体响度和真峰值。"""
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else text
    loud = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summary)
    peak = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summary)
    value = lambda m: None if not m or m.group(1) == "-inf" else float(m.group(1))
    return {"lufs": value(loud), "true_peak": value(peak)}


def parse_ranges(text: str, start_key: str, end_key: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}:\s*(-?[\d.]+)", text)]
    ends = [float(x) for x in re.findall(rf"{end_key}:\s*(-?[\d.]+)", text)]
    return list(zip(starts, ends))


def measure(video: Path, has_audio: bool, silence_db: float, silence_d: float) -> dict:
    out = {"lufs": None, "true_peak": None, "silences": [], "blacks": []}
    if has_audio:
        out.update(parse_ebur128(run(["ffmpeg", "-nostats", "-i", str(video), "-af", "ebur128=peak=true",
                                      "-f", "null", "-"]).stderr))
        sil = run(["ffmpeg", "-nostats", "-i", str(video), "-af",
                   f"silencedetect=n={silence_db}dB:d={silence_d}", "-f", "null", "-"]).stderr
        out["silences"] = parse_ranges(sil, "silence_start", "silence_end")
    black = run(["ffmpeg", "-nostats", "-i", str(video), "-vf", "blackdetect=d=0.2:pix_th=0.1",
                 "-an", "-f", "null", "-"]).stderr
    out["blacks"] = parse_ranges(black, "black_start", "black_end")
    return out


def grab_frames(video: Path, folder: Path, duration: float) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for name, t in (("首帧", 0), ("第1秒", 1), ("第3秒", 3), ("第5秒", 5)):
        if t and t >= duration:
            continue
        target = folder / f"{name}.jpg"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
             "-vf", "scale=960:-2", str(target)])
        if target.exists():
            made.append(target.name)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", "fps=1/3,scale=480:-2,tile=4x4",
         str(folder / "总览_%02d.jpg")])
    made += sorted(p.name for p in folder.glob("总览_*.jpg"))
    return made


def fmt(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def report(video: Path, info: dict, m: dict, frames: list[str], target: float, tp_max: float) -> tuple[str, int]:
    must = []
    lines = [f"# 自检报告 · {video.name}", "",
             f"- 时长 {fmt(info['duration'])}，{info['width']}×{info['height']}，{info['fps']} fps", "",
             "## 量出来的", "", "| 项 | 结果 | 判断 |", "| --- | --- | --- |"]
    if not info["has_audio"]:
        lines.append("| 声音 | 没有音轨 | 必须改 |")
        must.append("没有音轨")
    else:
        lufs, tp = m["lufs"], m["true_peak"]
        ok = lufs is not None and abs(lufs - target) <= 1.5
        lines.append(f"| 响度 | {lufs} LUFS（目标 {target}） | {'通过' if ok else '必须改'} |")
        if not ok:
            must.append("响度")
        ok_tp = tp is not None and tp <= tp_max
        lines.append(f"| 峰值 | {tp} dBTP（不超过 {tp_max}） | {'通过' if ok_tp else '必须改'} |")
        if not ok_tp:
            must.append("峰值")
        sil = [f"{fmt(a)}–{fmt(b)}" for a, b in m["silences"]]
        lines.append(f"| 静音段 | {len(sil)} 段 {'、'.join(sil[:8])} | {'通过' if not sil else '必须看：多半没切干净'} |")
    blacks = [f"{fmt(a)}–{fmt(b)}" for a, b in m["blacks"]]
    lines.append(f"| 黑场 | {len(blacks)} 段 {'、'.join(blacks[:8])} | {'通过' if not blacks else '必须看'} |")
    lines += ["", "## 抽出来的截图", ""] + [f"- `帧/{name}`" for name in frames]
    lines += ["", "## 看截图判断的（AI 照 02-方法/剪辑自检表.md 逐条填）", "",
              "| 项 | 结果 | 判断 |", "| --- | --- | --- |",
              "| 第 1 秒是结果画面 | | |", "| 首帧大字 = 封面主字 | | |",
              "| 字幕、字不出框不挡脸 | | |", "| 没有超过 8 秒没新东西的段落 | | |",
              "", "## 必须改", ""]
    lines += [f"- {item}" for item in must] or ["- 量出来的没有"]
    return "\n".join(lines) + "\n", len(must)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="剪完自检（只读视频，报告和截图写进 --out）")
    parser.add_argument("video")
    parser.add_argument("--out", help="报告和截图放哪，默认视频旁边的「自检」文件夹")
    parser.add_argument("--target", type=float, default=-14.0, help="目标响度 LUFS，默认 -14")
    parser.add_argument("--true-peak", type=float, default=-1.0, help="峰值上限 dBTP，默认 -1")
    parser.add_argument("--silence-db", type=float, default=-40.0)
    parser.add_argument("--silence-d", type=float, default=0.8, help="超过几秒算静音段，默认 0.8")
    parser.add_argument("--no-frames", action="store_true", help="不抽截图")
    args = parser.parse_args(argv)

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("出错：没装 ffmpeg / ffprobe（macOS：brew install ffmpeg）", file=sys.stderr)
        return 3
    video = Path(args.video).expanduser()
    if not video.is_file():
        print(f"出错：找不到 {video}", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser() if args.out else video.parent / "自检"
    out.mkdir(parents=True, exist_ok=True)

    info = probe(video)
    m = measure(video, info["has_audio"], args.silence_db, args.silence_d)
    frames = [] if args.no_frames else grab_frames(video, out / "帧", info["duration"])
    text, must = report(video, info, m, frames, args.target, args.true_peak)
    (out / "自检报告.md").write_text(text, encoding="utf-8")
    (out / "自检数据.json").write_text(json.dumps({"info": info, "measure": m, "must_fix": must},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    print(f"报告：{out / '自检报告.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
