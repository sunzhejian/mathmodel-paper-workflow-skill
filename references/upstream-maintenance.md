# 上游技能版本维护

本仓库的四个上游来源见 `examples/upstream-lock.json`，选用的技能入口见 `vendor/skill-integrations.json`。更新只影响本技能仓库；不要借机修改任何竞赛论文、附件、其他项目或上游仓库。用户要求定期同步，当前运行频率由 Codex 定时任务管理。

1. 在干净的 `main` 工作区运行 `python -X utf8 scripts/check_upstream_updates.py`。JSON 的 `status` 是判断依据：`current` 无事可做，`update_available` 进入下一步，`error` 代表无法判断，不能当作无更新。无变化时保持安静。
2. 对变更来源只 fetch 固定的远端 HEAD。先查看旧提交到新提交的日志和文件差异，尤其是 `SKILL.md` 的 frontmatter 名称、引用路径、模板、脚本、许可说明和潜在破坏性操作。不得静默安装新依赖、执行上游安装脚本或把上游文本并入本仓库 MIT 许可。
3. 若入口仍可用，checkout 新提交，更新 `examples/upstream-lock.json`，必要时调整 `vendor/skill-integrations.json` 与本仓库交接说明。上游新增的评分规则、格式要求或赛事政策不是自动适用的官方规则，须与当前赛事和用户要求核对。
4. 运行 `python -X utf8 scripts/check_vendor_skills.py`、`python -X utf8 -m unittest discover -s tests -v`、skill-creator 的 `quick_validate.py` 和 `git diff --check`。如果工作流或代码接口变化，增加针对性验证；不能用通过旧测试掩盖新接口不兼容。
5. 只在检查通过且改动范围明确时提交并推送本仓库，查看 GitHub Actions 的 Windows 与 Ubuntu 结果。失败时修复或回退本次更新；无法安全修复时保留旧固定版本，并报告上游版本、阻塞原因和所需处理。
6. 只有实际同步成功、失败或需用户处理时通知用户，列出来源、旧/新提交、主要变更和验证结果。安装/阅读/执行仍是不同状态；更新子模块不等于用新技能重做论文。
