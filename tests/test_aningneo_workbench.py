from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "aningneo-workbench"
SCRIPTS = SKILL_ROOT / "scripts"
INIT = SCRIPTS / "init_workbench.py"
CHECK = SCRIPTS / "check_workbench.py"
ICS = SCRIPTS / "schedule_to_ics.py"
SUBTITLE = SCRIPTS / "subtitle_check.py"
VIDEO = SCRIPTS / "check_video.py"
ROUGH = SCRIPTS / "rough_cut.py"

REFERENCES = [
    "00-搭建.md",
    "01-选题.md",
    "02-写稿.md",
    "03-知识库与纠正.md",
    "04-复盘与晨报.md",
    "05-商单与日历.md",
    "06-剪辑与自检.md",
    "07-AI员工.md",
    "08-每周学习.md",
    "定时任务.md",
]
TEMPLATES = ["今日热点.md", "选题卡.md", "发布包.md", "晨报.md", "周报.md", "商单.md",
             "剪辑项目.md", "派活单.md", "学习要点.md"]
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], check=False, text=True, capture_output=True)


def skill_text_files():
    for path in SKILL_ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".py", ".json"}:
            yield path


def build(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return run(str(INIT), "--root", str(root), "--name", "测试号", "--date", "2026-12-01", "--apply", *extra)


class PackageTests(unittest.TestCase):
    def test_skill_md_frontmatter_and_routes(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: aningneo-workbench\n"))
        self.assertLessEqual(len(text.splitlines()), 320)
        front = text.split("---", 2)[1]
        for trigger in ("搭自媒体工作台", "AI 运营团队", "知识库", "每天选题", "晨报", "复盘",
                        "商单排期", "剪辑自检", "AI 员工"):
            self.assertIn(trigger, front, trigger)
        for name in REFERENCES:
            self.assertIn(f"references/{name}", text, name)
            self.assertTrue((SKILL_ROOT / "references" / name).is_file(), name)
        for name in TEMPLATES:
            self.assertTrue((SKILL_ROOT / "assets" / "模板" / name).is_file(), name)

    def test_eight_features_are_covered(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for keyword in ("超过 5 天", "评论区第一条", "纠正记录", "没用过的工具", "晨报", "目标",
                        "竞品期", "同步", "自检", "字幕", "员工保底", "核实", "周三", "周日", "同意"):
            self.assertIn(keyword, text, keyword)
        for agent in ("Claude Code", "Codex", "WorkBuddy"):
            self.assertIn(agent, (SKILL_ROOT / "references" / "定时任务.md").read_text(encoding="utf-8"))

    def test_old_framework_is_gone(self) -> None:
        banned = ["Harness", "Guides", "Sensors", "企业三库", "enterprise"]
        for path in skill_text_files():
            text = path.read_text(encoding="utf-8")
            for word in banned:
                self.assertNotIn(word, text, f"{path.relative_to(SKILL_ROOT)} 里还有 {word}")
            for old_image in ("knowledge-audit", "knowledge-harness", "knowledge-panorama"):
                self.assertNotIn(old_image, text, f"{path} 还在引用旧图片")

    def test_readme_images_exist_and_are_small(self) -> None:
        images = sorted((SKILL_ROOT / "assets").glob("*.png"))
        self.assertGreaterEqual(len(images), 4)
        for image in images:
            self.assertLessEqual(image.stat().st_size, 500 * 1024, image.name)
        for readme in (REPO_ROOT / "README.md", SKILL_ROOT / "README.md"):
            text = readme.read_text(encoding="utf-8")
            refs = re.findall(r"!\[[^\]]*\]\(([^)]+\.png)\)", text)
            self.assertTrue(refs, readme)
            for ref in refs:
                self.assertTrue((readme.parent / ref).is_file(), f"{readme.name} 引用的 {ref} 不存在")

    def test_no_private_information(self) -> None:
        patterns = [r"/Volumes/", r"/Users/", r"@gmail\.com", r"@qq\.com", r"豆包",
                    r"sk-[A-Za-z0-9]{16,}", r"\b1[3-9]\d{9}\b"]
        for path in skill_text_files():
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                self.assertIsNone(re.search(pattern, text), f"{path.relative_to(SKILL_ROOT)} 命中 {pattern}")

    def test_evals_cover_new_scenarios(self) -> None:
        evals = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(evals["skill_name"], "aningneo-workbench")
        self.assertGreaterEqual(len(evals["evals"]), 10)
        self.assertTrue(all(item["assertions"] for item in evals["evals"]))
        prompts = " ".join(item["prompt"] for item in evals["evals"])
        for keyword in ("今日热点", "晨报", "商单", "剪", "Grok", "整理建议"):
            self.assertIn(keyword, prompts)


class InitTests(unittest.TestCase):
    def test_preview_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            result = run(str(INIT), "--root", str(root), "--name", "测试号")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PREVIEW", result.stdout)
            self.assertFalse(root.exists())

    def test_apply_builds_skeleton_and_templates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            result = build(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            for rel in ("AGENTS.md", "00-总台/成长/纠正记录.md", "00-总台/成长/待升级.md",
                        "00-总台/员工/岗位表.md", "00-总台/授权.md", "01-我/说话卡.md",
                        "01-我/我用过的工具.md", "05-选题与排期/日程表.md", "05-选题与排期/目标.md",
                        "06-复盘/粉丝记录.md"):
                self.assertTrue((root / rel).is_file(), rel)
            for name in TEMPLATES:
                self.assertTrue((root / "00-总台" / "模板" / name).is_file(), name)
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("测试号", agents)
            self.assertNotIn("{{", agents)
            self.assertIn("2026-12-01", (root / "01-我/我是谁.md").read_text(encoding="utf-8"))
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_claude_code_entry_points_to_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            self.assertEqual(build(root, "--agent", "claude-code").returncode, 0)
            self.assertEqual((root / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")

    def test_existing_files_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            root.mkdir()
            mine = root / "AGENTS.md"
            mine.write_text("# 我自己的规则\n", encoding="utf-8")
            original = root / "我的素材.txt"
            original.write_text("原文件\n", encoding="utf-8")
            self.assertEqual(build(root).returncode, 0)
            self.assertEqual(mine.read_text(encoding="utf-8"), "# 我自己的规则\n")
            self.assertEqual(original.read_text(encoding="utf-8"), "原文件\n")
            snapshot = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            again = build(root)
            self.assertEqual(again.returncode, 0)
            self.assertIn("要新建 0 个文件", again.stdout)
            self.assertEqual(snapshot, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})


class CheckTests(unittest.TestCase):
    def audit(self, root: Path, today: str = "2026-12-01") -> tuple[int, dict]:
        result = run(str(CHECK), "--root", str(root), "--format", "json", "--today", today)
        return result.returncode, json.loads(result.stdout)

    def test_fresh_workbench_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            build(root, "--agent", "claude-code")
            code, report = self.audit(root)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["status"], "healthy", report)
            self.assertEqual(report["summary"]["P0"], 0)
            self.assertEqual(report["summary"]["P1"], 0)

    def test_detects_problems(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            build(root)
            (root / "05-选题与排期/目标.md").unlink()
            (root / ".env").write_text("TOKEN=only-for-test\n", encoding="utf-8")
            (root / "01-我/笔记.md").write_text("api_key: abcdefghijklmnop1234\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("# 另一份规则\n", encoding="utf-8")
            with (root / "AGENTS.md").open("a", encoding="utf-8") as handle:
                handle.write("\n- 另见 `02-方法/不存在的文件.md`\n")
            entry = "\n## 2026-11-2{n} | 写稿 | 开头\n\n- 类别：写稿-开头（这类第 {n} 次）\n"
            with (root / "00-总台/成长/纠正记录.md").open("a", encoding="utf-8") as handle:
                for n in (1, 2, 3):
                    handle.write(entry.format(n=n))
            (root / "00-总台/晨报/2026-11-20.md").write_text("# 晨报\n", encoding="utf-8")

            code, report = self.audit(root)
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "broken")
            codes = {f["code"] for f in report["findings"]}
            for expected in ("MISSING_CORE_FILE", "SECRET_FILE", "SECRET_TEXT", "CLAUDE_ENTRY_MISMATCH",
                             "BROKEN_PATH", "CORRECTION_NEEDS_UPGRADE", "STALE"):
                self.assertIn(expected, codes)

    def test_correction_cleared_after_upgrade_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            build(root)
            with (root / "00-总台/成长/纠正记录.md").open("a", encoding="utf-8") as handle:
                for n in (1, 2, 3):
                    handle.write(f"\n## 2026-11-2{n} | 标题 | 太长\n\n- 类别：标题-太长（这类第 {n} 次）\n")
            with (root / "00-总台/成长/待升级.md").open("a", encoding="utf-8") as handle:
                handle.write("| U001 | 2026-11-30 | 标题不超过 20 字 | `02-方法/写稿手册.md` | 标题-太长 3 次 | 待定 |\n")
            _, report = self.audit(root)
            self.assertNotIn("CORRECTION_NEEDS_UPGRADE", {f["code"] for f in report["findings"]})


class ScheduleTests(unittest.TestCase):
    def test_ics_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "工作台"
            build(root)
            with (root / "05-选题与排期/日程表.md").open("a", encoding="utf-8") as handle:
                handle.write("| 2026-12-03 | 14:00 | 15:00 | 商单 | 第 1 期：交脚本 | 见商单, 文件夹 | ✅ |\n")
                handle.write("| 2026-12-08 | 18:00 | | 发布 | 第 1 期 | | |\n")
                handle.write("| 2026-12-08 | 全天 | 2026-12-15 | 竞品期 | 不接同类 | | |\n")
            result = run(str(ICS), "--root", str(root), "--out", "05-选题与排期/日程.ics")
            self.assertEqual(result.returncode, 0, result.stderr)
            ics = (root / "05-选题与排期/日程.ics").read_text(encoding="utf-8")
            self.assertEqual(ics.count("BEGIN:VEVENT"), 3)
            self.assertIn("SUMMARY:✅ [商单] 第 1 期：交脚本", ics)
            self.assertIn("DTSTART;VALUE=DATE:20261208", ics)
            self.assertIn("DTEND;VALUE=DATE:20261216", ics)
            self.assertIn("DTEND:20261208T183000", ics)
            self.assertIn("见商单\\, 文件夹", ics)
            again = run(str(ICS), "--root", str(root), "--out", "05-选题与排期/日程.ics")
            self.assertEqual(again.returncode, 0)
            uids = lambda text: sorted(re.findall(r"UID:(\S+)", text))
            self.assertEqual(uids(ics), uids((root / "05-选题与排期/日程.ics").read_text(encoding="utf-8")))


class SubtitleTests(unittest.TestCase):
    def test_flags_wrong_terms_and_unknown_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "发布包.md").write_text(
                "# 测试\n\n## 照着念\n\n今天教你用大肥鱼三分钟做出一个动效视频。\n第一个，打开设置，找到插件那一栏。\n\n## 标题\n\n1. x\n",
                encoding="utf-8")
            (folder / "a.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n今天教你用大鲸鱼\n\n"
                "2\n00:00:02,000 --> 00:00:04,000\n三分钟做出一个动效视频\n\n"
                "3\n00:00:04,000 --> 00:00:06,000\n第一个打开设置找到插件那一栏\n\n"
                "4\n00:00:06,000 --> 00:00:08,000\n顺便说一句我昨天去吃了火锅\n",
                encoding="utf-8")
            (folder / "terms.txt").write_text("大肥鱼\n", encoding="utf-8")
            result = run(str(SUBTITLE), "--srt", str(folder / "a.srt"), "--script", str(folder / "发布包.md"),
                         "--terms", str(folder / "terms.txt"), "--format", "json")
            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["cues"], 4)
            must = [i for i in payload["issues"] if i["level"] == "必须改"]
            self.assertTrue(all("第 1 条" in i["where"] for i in must), must)
            self.assertTrue(any("大肥鱼" in i["message"] for i in must))
            hints = [i for i in payload["issues"] if i["level"] == "建议"]
            self.assertTrue(any("第 4 条" in i["where"] for i in hints))

    def test_clean_subtitles_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "稿.md").write_text("## 照着念\n\n第一个，打开设置。\n", encoding="utf-8")
            (folder / "a.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n第一个，打开设置\n", encoding="utf-8")
            result = run(str(SUBTITLE), "--srt", str(folder / "a.srt"), "--script", str(folder / "稿.md"))
            self.assertEqual(result.returncode, 0, result.stdout)


class VideoTests(unittest.TestCase):
    def test_keep_segments_math(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import rough_cut  # noqa: PLC0415
        finally:
            sys.path.pop(0)
        log = "[silencedetect] silence_start: 1.0\n[silencedetect] silence_end: 2.5 | silence_duration: 1.5\n"
        silences = rough_cut.parse_silences(log)
        self.assertEqual(silences, [(1.0, 2.5)])
        self.assertEqual(rough_cut.keep_segments(silences, 4.0, 0.15, 0.2), [(0.0, 1.15), (2.35, 4.0)])

    @unittest.skipUnless(HAS_FFMPEG, "没装 ffmpeg")
    def test_rough_cut_and_check_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            clip = folder / "口播.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=4:r=25",
                 "-f", "lavfi", "-i", "aevalsrc='if(between(t,1,2.5),0,0.3*sin(2*PI*440*t))':s=48000:d=4",
                 "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)],
                check=True)
            preview = run(str(ROUGH), str(clip))
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("PREVIEW", preview.stdout)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["口播.mp4"])
            out = folder / "粗剪.mp4"
            cut = run(str(ROUGH), str(clip), "--apply", "--out", str(out))
            self.assertEqual(cut.returncode, 0, cut.stderr)
            self.assertTrue(out.is_file())

            report_dir = folder / "自检"
            checked = run(str(VIDEO), str(out), "--out", str(report_dir))
            self.assertEqual(checked.returncode, 0, checked.stderr)
            data = json.loads((report_dir / "自检数据.json").read_text(encoding="utf-8"))
            self.assertLess(data["info"]["duration"], 3.3)
            self.assertIsNotNone(data["measure"]["lufs"])
            self.assertTrue((report_dir / "自检报告.md").is_file())
            self.assertTrue((report_dir / "帧" / "首帧.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
