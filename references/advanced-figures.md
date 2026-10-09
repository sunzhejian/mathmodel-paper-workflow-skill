# 主动使用科研绘图技能

适用于建模结果图、数据分析、模型比较和用户要求“多用高级图”的任务。结果已具备时，主动检查哪些结论适合组合图、分布图或响应面，不等使用者逐张点名；只修文字、首页或排版时，仍按该次范围处理。图的数量由解题信息决定，不设每问必须若干张的配额。

## 入口与实际能力

截图中的相关矩阵、预测边缘分布、TPE曲面、半边小提琴、环形热图等对应 `mathmodel-figure-templates`。本项目默认入口为 `vendor/MathModelAgent/skills/mathmodel-figure-templates/SKILL.md`；sci-box 的 `scibox-figure` 声明同名，选择一个来源即可。先读所选入口及 `references/figure-catalog.md`，再调用具体模板。

当前固定版本有 **11个可直接运行的上游模拟样式脚本**，本项目已接通 **30种CSV数据入口**和5类带实际图源的流程模板。它们与参考软件的95款菜单分别计数：菜单数不等于可跑脚本数，可跑模拟样式也不等于已验证的数据接口。选中模板、复制脚本、成功运行和绑定真实数据分别记录，模板说明不构成统计检验或模型已经执行的证据。

在已接入本工作流绘图工具的桌面/网页宿主中，先查询真实可用的图件资源，再读取具体资源返回的指导与 example 合同。只把 example 字段的值保存为合同，不混入工具返回的 scientific_verified、操作说明或来源元数据。已有用户确认的字段、单位、数据版本不得静默改写；材料使用宿主返回的项目路径，不猜原始文件名。没有这组工具的环境继续使用下文真实 CSV 脚本入口，不能伪造工具调用或要求用户更换 IDE。

| 模板 | 适合回答什么 | 使用前需要什么 |
| --- | --- | --- |
| correlation-pairgrid | 多变量关系、原始分布和异常点 | 同一批样本的数值变量、含义与单位；剔除索引/编号，说明Pearson或其他口径 |
| prediction-marginal-grid | 多模型预测误差和训练/验证分布 | 真实参考值、预测值、模型名、划分与样本ID；相同评价样本和指标定义 |
| rf-tpe-surface | 参数对目标的响应、真实调参采样 | 参数及实际目标值；网格可画连接面，稀疏试验用点云，不凭模板造连续RMSE面 |
| grouped-corr-split-violin | 特征组关系与分组分布差异 | 原始特征、分组依据和各组样本；对数轴及相关系数方法须明确 |
| paired-raincloud | 重复测量、处理前后或配对方案变化 | 配对ID、阶段及测量值；配对连线与均值趋势区分 |
| grouped-circular-heatmap | 多指标、多对象的分组概览 | 对象/指标矩阵、类别顺序及每环单位/色标；和普通热图比较可读性 |
| multiclass-shap-combo | 已训练模型的实际特征贡献 | 真实解释值、模型/类别和样本特征；不能用随机蜂群宣称计算过SHAP |
| cv-roc-ci | 分类模型的验证辨别表现 | 标签、真实验证概率、折ID；折间标准差带不能直接改称95%置信区间 |
| taylor-diagram | 同一参考序列下比较多个模型 | 对齐序列和明确标准差、相关、误差口径；常量及负相关情形先检查 |
| urban-park-cooling-combo | 类别组成、分布与组间比较 | 本题类别数量与实际测量；复用组合布局，替换城市/降温等不属于本题的名称 |
| nature-chord-diagram | 有含义的流量、转移或网络联系 | 真实关系矩阵、方向与单位；不要把一般相关系数任意画成流量 |

药材传热传质等物理题通常优先场分布、中心/表面/平均值联图、误差收敛和参数响应；分类题才考虑ROC和SHAP。已有算法和数据不足时用更直接的图，不能为了模板额外改成机器学习问题。数据图与教材式几何线稿分工：边界、遮挡和控制体用 `scibox-diagram`、TikZ 或已有矢量路径。

## 主动调用流程

1. 从逐问结果和要支持的结论列一个简短图示清单，写明数据来源、变量/单位、分组、比较口径和放置位置。通常先推荐两三类最能补足信息的图；不是一次展示全部图库。
2. 数据含义和风格已清楚时直接选合适模板或数据入口。只有分组、统计量、变量转换或目标格式影响科学含义且未明确时才补问；用户已选布局不重复询问。
3. 首次套用可运行原模板看布局。用当前可用Python及实际技能路径，不照抄Linux沙箱路径；用新工作目录，子模块保持只读。
4. 正式图用真实结果替换全部模拟输入、模型名称、指标文字、范围和色标。统计量从数据或已有结果读取/计算，保存计算口径。平滑、拟合、归一化、误差条和显著性需有依据并记录，不作为美化偷偷加入。
5. 导出PNG、矢量PDF/SVG及可编辑代码，检查独立图和嵌入论文后的实际尺寸。图注短，主要解读写正文，过程日志和哈希留后台。

原模板的已识别风险：预测组合图的指标文字写死；调参面使用模拟试验并与解析造面函数混合；相关图有演示拟合/近似显著性和固定范围；ROC样式预设AUC及波动并由它们反造曲线，图例带固定p值；部分排名实现不处理并列。上述内容须按本题数据和统计方法适配，不能只把CSV塞进去就称为正式结果。本项目提供下面的原创数据入口，只吸收布局，不复制模拟指标或解析造面实现。

## 已接通的CSV数据入口

`scripts/render_scientific_data.py` 当前支持30种布局及网格/点云两种响应表示，角色合同示例见 [examples/scientific-figures](../examples/scientific-figures)与[新增图库](../examples/scientific-figures/gallery)。原数据只读；输出目录必须新建。图中不绘制默认显著性星号或拟合置信带；需要这些内容时先取得对应分析证据再改图源。

| template_id | 合同字段 | 实际行为 |
| --- | --- | --- |
| correlation-pairgrid | `columns` 数组，每项 `key/label/unit` | 原始散点、直方图、Pearson系数；拒绝常量、缺失和非有限值，不默默标准化 |
| prediction-marginal-grid | `roles` 映射 `model/split/sample_id/actual/predicted`，共同 `unit` | 每组重算n、RMSE、MAE、R²；恒定参考值的R²显示NA；比较默认核对同样本、划分和参考值，坐标范围统一 |
| rf-tpe-surface | `x/y/z` 三个 `key/label/unit`，`surface_mode` 为 `grid` 或 `scatter` | 完整网格连接已给节点；稀疏试验可直接画原始点云；不启动优化器、不混入解析造面函数 |
| paired-raincloud | `roles` 精确映射 `sample_id/condition/value`，`conditions` 为两个不同阶段的有序名称，共同 `unit` | 按ID对齐完整两阶段配对，半边密度、箱线、原始点与每对连线；另画真实配对差值分布，重算均值/中位数/标准差与四分位数；不生成p值或CI |
| binary-roc-comparison | `roles` 精确映射 `model/sample_id/label/score` | 同一批样本及相同0/1标签上的2–6个方案，按分数整组处理并列阈值，ROC及梯形积分AUC从原始分数计算；不训练、不启动交叉验证，不生成置信带 |

新增15项仍从主渲染器调用，数值轴使用`axes={角色:{label,unit}}`，分布、柱状和矩阵使用共同`unit`。实现模块为`scientific_chart_extensions.py`，随主脚本一并复制进复现目录并记录SHA，不依赖用户另装Origin。

| template_id | 角色与额外输入 | 实际用途 |
| --- | --- | --- |
| grouped-line | group/x/y；axes x/y | 按给定横轴排序连接观测，不拟合趋势模型 |
| uncertainty-band | group/x/estimate/lower/upper；axes x/estimate；interval_note | 画已给区间，说明是场景、观测范围还是已算CI；拒绝倒置或不含估计的边界 |
| grouped-scatter | group/sample_id/x/y；axes x/y | 原始二维散点；不加未计算拟合线 |
| grouped-box、grouped-violin | group/sample_id/value；unit | 原始点、四分位或描述性KDE；常量组省略密度 |
| distribution-histogram、ecdf-distribution | group/sample_id/value；unit | 共同分箱频数或经验累计比例；直方图可显式选择bins |
| grouped-bar、stacked-bar | category/series/value；unit | 完整类别系列表；不默默汇总或用0填缺格，堆积拒绝负数 |
| matrix-heatmap | row/column/value；unit | 完整矩阵与统一色标，不推算缺失单元 |
| residual-diagnostics | model/split/sample_id/actual/predicted；axes actual/predicted且单位相同 | 对齐同评价样本，重算误差、RMSE/MAE/R²并展示残差 |
| binary-pr-comparison | model/sample_id/label/score | 同人群的PR与平均精确率AP，按相同分数组移动；不拿ROC面积代替AP |
| confusion-matrix | model/sample_id/actual/predicted，类别为文本；可显式classes | 同样本类别计数；缺类分母为0的指标记null，不填成0分 |
| optimization-convergence | group/iteration/objective；axes iteration/objective | 已供迭代轨迹，不宣称实际运行优化器或证明收敛 |
| pareto-front | group/sample_id/x/y；axes x/y；x_direction/y_direction为min或max | 已供点集中的非支配候选，不宣称全局最优或可行性已验证 |

字段缺失、非有限数值、重复样本/横轴/矩阵格、比较人群或观测不一致均拒绝。原始精度保留在`figure-data.json`，绘图仅按显示需求舍入。15份合成示例和生成脚本在新增图库内；正式使用替换CSV并确认字段、单位及来源。

另10项仍由同一渲染器和复现源码导出，并分别提供同名CSV/JSON及真实渲染预览；不会把渲染器没有执行的回归、情景求解、重校准或地图分析写成已经完成。

| template_id | 角色与额外输入 | 实际用途 |
| --- | --- | --- |
| hexbin-density | sample_id/x/y；axes x/y；gridsize可选（4–80整数，默认24） | 从原始点计算六边形分箱计数，渲染后回读每格计数并核对总数；颜色不是概率密度 |
| density-contour | sample_id/x/y；axes x/y；density_method=histogram；bins可选（4–60整数，默认16） | 计算矩形分箱的密度与等高线，保留原始点；记录边界、计数、密度积分，不声称KDE或空间插值 |
| coefficient-forest | term/estimate/lower/upper；axes estimate；interval_note；reference_value可选 | 展示给定系数和包含估计值的有限区间，默认参考线0；不拟合回归或推导CI/p值 |
| sensitivity-tornado | parameter/baseline/lower_case/upper_case；axes baseline；scenario_note | 给定各参数低/高情景的输出减共同基准，输出方向可反转；不代跑参数扰动实验 |
| multimetric-profile | series/metric/value；unit；scale_min/scale_max/scale_note | 完整3–12指标、1–6系列在显式共同量尺上画轮廓，拒绝越界；不归一化、不推断排名 |
| bubble-matrix | row/column/value；unit | 完整非负矩阵，圆面积与数值成正比，色标和面积标尺明确，0用x标示；不静默汇总/填缺格 |
| ridge-distribution | group/sample_id/value；unit | 共同数值轴与共同密度高度比例的分组描述性KDE、原始刻痕；常数组只画原值，不捏造密度宽度 |
| qq-normal | group/sample_id/value；unit | 原样本排序值与标准正态(i−0.5)/n理论分位比较；参考线采用样本均值/标准差，不报告正态性检验p值 |
| calibration-curve | model/sample_id/label/score；bin_edges显式数组 | 同样本0/1实际标签与[0,1]概率，按共同边界计算均值概率、正例率、Brier和该分箱ECE；不重校准、不生成CI |
| spatial-point-values | sample_id/x/y/value；axes x/y/value；coordinate_system=planar或lonlat | 给定点位置与数值；平面x/y同单位，经纬度x/y采用degree并核对范围；无底图、投影或插值 |

密度图要求两个轴均有变化；六边形统计为格内观测数，矩形密度为`计数/(总数×格面积)`，不能互换色标解释。系数图的区间性质和情景图的参数范围由`interval_note`/`scenario_note`明确提供，绘图不补造统计依据。雷达式轮廓仅展示使用者已经定义的共同量尺，不同单位指标须先在分析阶段取得明确可比较的输入；不在绘图时偷偷归一化。

校准的`bin_edges`为3–31个有限边界，严格从0递增到1；采用`[lower,upper)`，仅最后一格包含1。空分箱保留`n=0`和null，不画成正例率0；重复样本、标签不一致或不同评价人群拒绝。分箱ECE依赖当前边界，不能称为不依赖分箱的模型性质；给定概率也不自动证明独立验证。空间图不接受重复坐标的未说明叠加；lonlat限定经度[-180,180]、纬度[-90,90]，原生经纬轴展示不等于投影地图。

流程目录包含迭代推进、全文技术路线、数据质量分支、模型模块关系与验证回路。各合同保留实际节点、条件、箭头和坐标；复用的是图示组织方式，需替换成该题算法，不能把样式预览认作实验或求解证据。

`paired-raincloud` 继承上游的半边小提琴、箱线、散点和均值布局，配对依据来自实际ID。输入是长表，每个ID在两个合同阶段各出现一次，至少有两个完整配对；缺配对、重复、未知阶段、空ID和非有限值直接拒绝。阶段顺序定义差值方向为第二阶段减第一阶段，图中的个体连线与均值菱形/趋势线分别表达个体和总体变化。抖动只是按ID确定的水平显示偏移，两阶段共用偏移，不修改测量值。常量阶段保留点和箱线、注明省略KDE，避免造一个不存在的分布宽度。

`binary-roc-comparison` 是本项目独立数据适配项，**不是** `cv-roc-ci` 的已验证置信区间入口。每个方案/样本ID只能有一行，每个方案必须包含同一组ID和相同标签；单类、非0/1标签、重复、非有限分数或不同评价人群均拒绝。分数可以是概率或任意有限排序分数，方向固定为分数越高越倾向标签1。相同分数同时更新TP/FP，图中连接实际阈值点，AUC按梯形面积计算、并列贡献半分；起点阈值用报告中的`null`表示高于所有给定分数，避免输出无穷数。没有折ID、重采样或抽样依据时不报告折间波动、p值或CI，也不把给定分数自动认作来自独立验证集。

通用字段为 `schema_version=1`、`template_id`、`data`（相对合同的CSV路径）、`data_kind`（real/synthetic）、`title`；可用 `source_note` 记录数据说明。`real` 是来源声明，需要与项目证据核对；没有数据时不能拿示例填正式图。未知合同字段直接拒绝，防止忽略未实现的分析要求。图内数值只按显示需要舍入，报告保留完整精度。

```sh
# 从skill根目录，在本次选择的环境中安装可选绘图依赖。
python -m pip install -r requirements-figures.txt
python -X utf8 scripts/template_inventory.py --project-root 项目目录 --category data-figure

# 只核对合同与计算值，不绘图。
python -X utf8 scripts/render_scientific_data.py --manifest 真实项目/figure-contract.json --validate-only

# 输入需要中文时选已有字体；可用本项目的固定开源字体下载工具。
python -X utf8 scripts/render_scientific_data.py --manifest 真实项目/figure-contract.json --output 真实项目/figures/advanced-01 --font 字体目录/NotoSansSC.ttf
```

输出为 `figure.png/pdf/svg`、`figure-data.json`，以及 `reproduce/` 中的输入CSV、合同和原创渲染脚本。报告记录输入、源码和成品哈希、软件版本及数值；输入或脚本在绘制途中改变会拒绝该轮。重新绘图用新目录，不覆写用户图源。

变量字体在输出的私有 `.fonts` 中实例化正常/粗体字重，保持源字体只读；已知OFL许可证一并保留，字体不安装到系统。正文或公开图库不分发这些字体缓存。独立命令进程结束后可移动图件；同进程批量绘制复用已注册字体。

## 示例与验收

可运行 `generate_advanced_figure_examples.py --output qa/advanced-figure-demo --font 字体目录/NotoSansSC.ttf` 生成原先三类合成CSV和图。新增配对和ROC接口使用冻结的匿名合成合同：[paired.json](../examples/scientific-figures/paired.json) 与 [binary-roc.json](../examples/scientific-figures/binary-roc.json)，可以直接由上述CLI核验与绘制。配对示例有24个完整ID、明确的两阶段顺序与单位；ROC示例有3组预先给定分数、相同16个样本和8/8正负标签，其中常量分数方案用于核对并列AUC=0.5。图内明确标注“合成数据示例”；这些例子均不是真实实验、模型训练或正式论文结果。公开例图及来源见 [README](../README.md#科研绘图示例)。

按实际版心检查中文、上下标、单位、色标、样本数量、图例和统计标注。高密度联图优先减少变量/拆组，不将字缩到不可读；3D必须有真实第三维，不能让透视遮住极值或用它替代必要的2D比较。数据匹配、标签与单位、统计量及导出检查通过才记为数据图完成；模板运行、代码存在或SVG可编辑均不能代替这项验收。
