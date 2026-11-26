# aningneo-workbench｜搭一个 AI 运营团队

![一个人做号，配一支 AI 运营团队](assets/aningneo-workbench-overview.png)

在你电脑上搭一个自媒体工作台：每天刷热点挑题、写稿、出晨报、排商单、剪辑自检、给别的 AI 派活、每周学运营。它能做什么、搭好以后每天怎么跑，见 [仓库首页](../../README.md#搭一个-ai-运营团队)。这一页讲怎么用。

## 装

```bash
npx -y skills@latest add 8533502-dev/aningneo-workbench --skill aningneo-workbench -y
```

或者去 [Releases](https://github.com/8533502-dev/aningneo-workbench/releases/latest) 下载 ZIP，把 `aningneo-workbench` 文件夹放进 Agent 的 Skill 目录。Claude Code、Codex、WorkBuddy 都能用。

## 第一次：复制给你的 Agent

```text
用 aningneo-workbench 帮我搭一个自媒体工作台，放在「这里换成文件夹路径」。
我做的是「这里写你做什么内容」，现在大概「N」粉，想在「多久」涨到「N」粉。
我手上有这些 AI 和工具：「这里列出来」。我用的是「Claude Code / Codex / WorkBuddy」。
先问我缺的信息，再给我看要建哪些文件，我说可以了再建。建好以后帮我把定时任务设好。
```

它会按这个顺序走：问清 6 件事 → 预览骨架 → 你说可以再建 → 填「我是谁」和目标 → 登记你的工具和其他 AI → 设定时任务 → 体检 → 当场试跑一遍热点、写稿、晨报。

## 日常怎么说

| 你说 | 它做 |
| --- | --- |
| 今日热点 / 帮我找选题 | 刷热点、挑题打分，写进 `03-调研/热点/<日期>/` |
| 这个题帮我写 / 明天发什么 | 定明天那条，写好 `文稿/发布包.md` |
| 「这句不对」「太 AI 了」 | 只改那句，当场记一条纠正 |
| 出今天的晨报 / 今天做什么 | 写 `00-总台/晨报/<日期>.md` |
| 接了个商单，帮我排期 | 每期节点和竞品期进日程表，同步日历 |
| D003 录好了，帮我剪 | 粗剪、字幕对稿、出预览、自检，改完再给你 |
| 让员工去查一下 X | 按岗位表派活，核实后再给你 |
| 看看待升级 / 同意第 N 条 | 列出建议，你点头才改规则 |
| 体检一下工作台 | 跑 `check_workbench.py` |

## 包里有什么

| 位置 | 是什么 |
| --- | --- |
| `SKILL.md` | 总流程：第一次怎么搭、8 个功能摘要、规矩 |
| `references/00-搭建.md`、`定时任务.md` | 第一次搭的完整步骤；Claude Code / Codex / WorkBuddy 各自怎么设定时 |
| `references/01-选题.md` … `08-每周学习.md` | 8 个功能，每个一份详细步骤 |
| `assets/骨架/` | 工作台初始目录：总台规则、纠正记录、待升级、效果账本、岗位表、授权、日程表、目标…… |
| `assets/模板/` | 今日热点、选题卡、发布包、晨报、周报、商单、剪辑项目、派活单、学习要点 |
| `scripts/` | 6 个小脚本，见下面 |
| `evals/evals.json` | 11 个测试场景 |

## 脚本也能单独用

都在 `scripts/` 里，默认只看不写，加参数才动手。

```bash
# 建骨架：默认只预览，--apply 才写，已有文件不覆盖
python3 scripts/init_workbench.py --root ~/自媒体工作台 --name "账号名" [--agent claude-code] [--apply]

# 体检：缺文件、密钥、断路径、该升级的纠正、定时任务断没断
python3 scripts/check_workbench.py --root ~/自媒体工作台

# 日程表转 .ics，导入苹果 / Google / Outlook 日历
python3 scripts/schedule_to_ics.py --root ~/自媒体工作台 --out 05-选题与排期/日程.ics

# 口播粗剪：按停顿去空白，先看切点，--apply 才出片（要 ffmpeg）
python3 scripts/rough_cut.py 口播.mp4 [--apply --out 粗剪.mp4]

# 拿口播稿查字幕：对不上的字、写错的专有名词、太长的行
python3 scripts/subtitle_check.py --srt 粗剪.srt --script 文稿/发布包.md --terms 专有名词.txt

# 剪完自检：响度、静音、黑场，抽首帧和总览图（要 ffmpeg）
python3 scripts/check_video.py 预览v1.mp4 --out 自检
```

## 花钱和密钥

- 按次收费的接口（抓数据、生图生视频、转写）你自己开通、自己付；每次先报价，同意才跑。长期授权记在工作台的 `00-总台/授权.md`。
- 也能全免费跑：网页搜索找热点、后台截图记粉丝、本地 Whisper 类工具转字幕。
- 密钥放环境变量或系统钥匙串，不进工作台文件，不进仓库。

## 起步版

给的是骨架、流程、模板和检查表。说话卡、钩子库、爆款规律、剪辑风格、员工提示词都留空，由你的纠正记录和数据长出来。想按自己账号定制整套，可以在仓库提 Issue 联系作者。
