# 示例图来源与重建

这里的流程示意图和数据图展示图件接口与排版能力。它们使用本仓库的匿名合成数据或通用算法符号，不是实际赛题的计算结果，不提供比赛评分或预测能力证明。

## 数据图

原先的 `scientific/correlation`、`scientific/prediction` 和 `scientific/surface` 由 [generate_advanced_figure_examples.py](../../scripts/generate_advanced_figure_examples.py) 及对应 [CSV 合同](../../examples/scientific-figures/README.md) 生成。

新增两图均使用 [render_scientific_data.py](../../scripts/render_scientific_data.py) 直接读取固定 CSV，输出 PNG、矢量 PDF/SVG 与数据报告：

| 图目录 | 合同与数据 | 实际计算范围 |
| --- | --- | --- |
| `scientific/paired` | [paired.json](../../examples/scientific-figures/paired.json)、[paired-values.csv](../../examples/scientific-figures/paired-values.csv) | 24 对完整配对，均值差 1.1416666667 mg；描述性分布，不含显著性检验/置信区间 |
| `scientific/binary-roc` | [binary-roc.json](../../examples/scientific-figures/binary-roc.json)、[binary-scores.csv](../../examples/scientific-figures/binary-scores.csv) | 同一 16 个样本、8 正/8 负；三组给定分数的 AUC 为 0.9296875、0.734375、0.5；未训练模型，不含交叉验证或置信区间 |

```sh
python scripts/render_scientific_data.py --help
```

按合同中的 data 路径读取数据；将 `--manifest` 与 `--output` 替换为需要的合同和新目录。字体从本机已授权字体或许可允许的测试字体中选择，仓库不分发宋体、黑体等商业字体文件。数字与绘图来源在生成的报告中核对，绘图成功不替代科学解释。

## 流程示意图

`flowcharts/` 的四组图由 [render_flowchart.py](../../scripts/render_flowchart.py) 和 [四个坐标/连接合同](../../examples/flowcharts) 生成：

- `numerical_iteration`：多输入、内层收敛判定与时间循环
- `optimization_feedback`：约束判定及模型反馈
- `data_split_no_leakage`：训练、验证、测试的信息边界
- `parallel_model_structure`：并行子模块与汇合

本次原生导出使用本机 draw.io CLI，PNG 按 160 mm 宽测得约 327–428 dpi；PDF 为一页矢量图，保留可编辑 `.drawio`。这是这些示例的观测值，不能保证新的标签、坐标或缩放仍满足相同条件。合同需要显式坐标和回路路径，渲染器不自动规划任意拓扑。

```sh
python scripts/render_flowchart.py --help
```

本机 draw.io 导出的原始 SVG 仍含 `foreignObject` / 动态样式。此处只发布 `.drawio`、PNG 和 PDF；Typst 使用同源 PNG，LaTeX 优先矢量 PDF。导出后的图仍须在实际论文宽度下查看标签、箭头、重叠和留白。
