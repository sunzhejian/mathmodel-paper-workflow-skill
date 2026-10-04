# MiniMax M Plan 接入与首轮源码复核

2026-10-04使用者授权加入 MiniMax M Plan 的 **MiniMax-M3.1-Flash-Preview**。模型名、订阅可用范围和协议按[中国官方调用说明](https://platform.minimax.cn/docs/guides/text-generation)与[国际说明](https://platform.minimax.io/docs/guides/text-generation)核对，不把普通API或其他模型当成所选订阅路线。

[路线示例](../examples/model-trials/providers.json)分别提供 `minimax-cn-mplan-flash`（`api.minimax.cn/v1`）与 `minimax-mplan-flash`（`api.minimax.io/v1`），都只引用 `MM_MINIMAX_MPLAN_API_KEY` 环境变量。按账号地区明确选择，不猜密钥。当前本机账号在国际路线上返回401；中国官方路线上正常完成同一任务，地区鉴权失败不算模型解题失败，也未静默修改原失败记录。

实际通过已安装 OpenCode 1.18.34、Chat Completions兼容SDK与独立客户端状态执行；没有直接把模型API接到协会网站或共享订阅账户。首轮只读我们的网站JS/HTML/CSS、README与开发/融合计划，返回严格JSON复核意见，38.9秒正常结束，无工具事件、无模拟调用。它没有浏览网页、执行程序、读取外部上游全文或完成科学建模。

意见中实际采用了图件“预览/生成”口径澄清、模板在本次项目中未核验的明确标记、静态首屏六方向未确认状态及许可/合成资产来源记录。后台未接通本就是计划项，不因意见再次出现就说它新发现了已实现功能缺陷；字体/OFL与模板仓库未给模型的内容，不由其文本猜测代替实际检查。源码修订后由宿主做语法与浏览器核对，分别记录模型审读与宿主验证。

调用方法与[其他客户端分项验收](../references/model-trials.md#可选客户端与分项验收)相同，示例无凭据：

```sh
python scripts/run_opencode_trial.py --routes examples/model-trials/providers.json --route minimax-cn-mplan-flash --prompt /path/to/research/prompt.txt --output /path/to/research/new-run --opencode /path/to/opencode --protocol chat --effort low
```

凭据与原答复留在本机私有配置/研究目录，不进入提示词、公开文档、命令参数或网站前端。此次是文本源码复核，不补记为完整人口题、20页以上论文、真实制图或PDF编译成绩。`--effort low`是客户端配置；请求模型名不是后台精确版本的独立证明。
