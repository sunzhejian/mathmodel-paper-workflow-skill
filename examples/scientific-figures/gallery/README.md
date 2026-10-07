# 合成科研图表图库样例

这里保存15种统计图的固定合成CSV、明确字段合同和640px JPEG预览，以及5种通用流程机制图的JPEG预览。图内标示“合成示例”，不对应真实实验、训练、优化运行或赛题结论。

`generate_gallery.py::datasets` 给出全部数据生成规则，随机部分使用 NumPy `default_rng`，基础种子为 `20261007`，不同图型采用脚本明确列出的种子偏移。分组柱图和矩阵是明示的聚合/单元格输入；残差、PR和混淆矩阵采用同一模型比较人群。范围带使用给定上下界，合同中的 `interval_note` 说明它不是从样本推算的置信区间。Pareto合同明确两个目标均最小化，非支配点由适配器根据给定候选重新计算。

`gallery_assets.json` 提供合同、CSV、缩略图、渲染报告和可复现生成脚本的相对路径索引。统计图使用实际 `prepare_extension` 和 `render_extension`；流程图使用现有 `render_flowchart.py` 及安装的draw.io执行程序，保存原生文本、形状和连接线。

从skill根目录运行（输出必须为不存在的新目录）：

```powershell
python -X utf8 examples/scientific-figures/gallery/generate_gallery.py --only charts --output qa/gallery-reproduction-charts --font C:/Windows/Fonts/simsun.ttc
python -X utf8 examples/scientific-figures/gallery/generate_gallery.py --only flowcharts --output qa/gallery-reproduction-flows --font C:/Windows/Fonts/simsun.ttc --drawio E:/draw.io/draw.io.exe
```

生成器需要当前环境已可用的NumPy、Matplotlib、Pillow、fontTools。draw.io仅流程导出需要，路径应替换成已有安装。字体使用本机宋体，不分发系统字体文件。高清PNG/PDF/SVG、统计量、来源哈希和导出证据留在所选QA目录；网页用JPEG保持宽度640px与质量88，优化色度采样以减小体积。高密度残差与长迭代图可超过40KiB，以保存全部文字和图形。

统计图：grouped-line、uncertainty-band、grouped-scatter、grouped-box、grouped-violin、distribution-histogram、ecdf-distribution、grouped-bar、stacked-bar、matrix-heatmap、residual-diagnostics、binary-pr-comparison、confusion-matrix、optimization-convergence、pareto-front。

流程合同在 `examples/flowcharts`：research_roadmap.json、data_pipeline.json、model_structure.json、validation_decision.json，以及保留原件的 numerical_iteration.json。第五份缩略图名为 numerical-iteration.jpg，其他四份缩略图与合同名一致。
