# 科研图的合成输入合同

三份CSV与相应JSON由 `scripts/generate_advanced_figure_examples.py` 使用种子20261002生成并冻结；用于展示绘图输入和计算口径，**不是真实赛题数据**。没有训练预测模型，也没有运行TPE。合同保留 `data_kind=synthetic`，图件显式显示合成标记。

| 合同 | 数据 | 展示内容 |
| --- | --- | --- |
| [correlation.json](correlation.json) | [features.csv](features.csv) | 180行、四个无量纲变量的分布与Pearson相关 |
| [prediction.json](prediction.json) | [predictions.csv](predictions.csv) | 两个模拟方案各140个train、70个test参考/预测对；现场计算误差与R² |
| [surface.json](surface.json) | [response-grid.csv](response-grid.csv) | 90个已给响应节点的10×9网格；展示连接面，不是优化器的搜索结果 |

从skill根目录用 `render_scientific_data.py --manifest examples/scientific-figures/prediction.json --output qa/prediction-demo-new --font 字体目录/NotoSansSC.ttf` 可实际复现该图。生产使用时另建合同，选择本项目真实CSV、变量名/单位、样本ID与科学标题，并核对来源；不能只把这里的状态改成real。

输入文件按原始字节保留，便于核对公开图件的输入哈希；重新生成时用新目录。输出图的合格不等于模型、数据来源或整篇论文已经通过审查。
