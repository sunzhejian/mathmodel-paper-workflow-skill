# 固定版本的上游技能文件

本目录中的 `MathModelAgent/`、`sci-box/`、`BZD/`、`EditaPlot/` 是 **Git 子模块**，分别指向 [历史版本锁](../examples/upstream-lock.json) 的提交。执行 `git clone --recurse-submodules`，或在已有仓库中执行 `git submodule update --init --recursive` 后，上游的实际项目文件会出现在这些目录中。本仓库不把这些文件改标为自己的 MIT 作品，也不暗示缺少明确许可的上游允许另行复制或商业再分发。

本仓库选用的具体入口在 [skill-integrations.json](skill-integrations.json)。例如：

| 用途 | 本地文件 |
| --- | --- |
| 赛题分析与模型设计 | `MathModelAgent/skills/2analysis-modeling/SKILL.md` |
| 独立求解与数据图 | `MathModelAgent/skills/3coding-visual/SKILL.md` |
| 可编辑示意图 | `sci-box/skills/scibox-diagram/SKILL.md` |
| 论文撰写与验证 | `MathModelAgent/skills/5writing/SKILL.md`、`MathModelAgent/skills/6verity/SKILL.md` |
| 假设、求解专项审查 | `BZD/skills/论文自查类/bzd-model-assumption-checker/SKILL.md`、`BZD/skills/论文自查类/bzd-model-solution-checker/SKILL.md` |
| 可选 Origin 绘图 | `EditaPlot/skill/editaplot/SKILL.md` |

运行 `python scripts/check_vendor_skills.py` 可验证四个提交、所选入口与 frontmatter `name`。子模块中的技能不会因为放在此目录就自动注册为顶层 Codex skill；使用某个阶段时需读取相应 `SKILL.md` 及其引用文件。按需运行，不要把“文件存在”记作“已执行”。

`sci-box/skills/scibox-figure/SKILL.md` 的 frontmatter 名称与 MathModelAgent 的 `mathmodel-figure-templates` 相同。本仓库默认选用后者；不要同时注册这两个同名入口。BZD 中的同名副本也只选择清单指定的一份。

`mma-paper` 属于历史项目本地入口，未核实可公开拉取的上游地址，因此未加入子模块。需要时只使用用户当前项目已有的文件。
