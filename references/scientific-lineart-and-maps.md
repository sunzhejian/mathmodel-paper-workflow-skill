# 科学线稿与研究地图

## 科学单线矢量图
需要控制体、边界条件、几何结构、装置或科技线稿时，读取 `scripts/render_scientific_lineart.py`。它接受毫米坐标的可编辑 JSON 场景，支持线、箭头、尺寸线、圆、环带、矩形与文字，生成 SVG、PDF、PNG 和源场景。示例是有限体积机制示意，不代表本题已经求解。按本题真实几何、符号、法向和边界条件修改场景，再在项目内运行。

不要用生成式位图或自动描摹代替线稿。检查箭头方向、环带中径与厚度、中心/表面半控制体、法向导数和单位；在最终论文尺寸看 PNG/PDF，保留 SVG 与 scene.json。数学公式使用 mathtext，不执行用户提供的 TeX 命令。

## Shapefile 与地图
先核对同名 .shp/.shx/.dbf/.prj，不能根据数字范围猜坐标系。GeoJSON 使用显式 CRS 参数（RFC 7946 为 EPSG:4326）；投影用 PyProj，几何与孔洞用 Shapely，字段需来自完整属性表。使用 `scripts/render_research_map.py`，在本项目保留源 SHA、输入/输出 CRS、字段与导出记录。对缺失、无效几何和字段中断并报告，不默默修补或编造。

中国国界、行政边界与世界图必须遵照自然资源部《公开地图内容表示规范》（自然资规〔2023〕2号）。使用自然资源部标准地图服务下载原图，保留完整图幅、台湾及重要岛屿、南海诸岛与审图号；不能用 Natural Earth、模型生成国界或未经核验的网络边界替代。

严格底图模式接受 manifest：file、source_url、sha256、review_number。工具将本地字节与官方 HTTPS 下载比对，完整保留原图，不裁切、不重绘边界。官方来源不可访问或字节不符时停止；不得写“已自动审查合规”。公开使用前仍核对底图适用范围及需履行的地图审查。一般研究区矢量模式不认证其行政边界；大范围涉中国图幅会被阻止。缺少官方底图时可完成数据分析和布局，不能生成替代中国国界。

- 官方标准地图：https://bzdt.ch.mnr.gov.cn/
- 内容规范：https://www.fmprc.gov.cn/web/wjb_673085/zzjg_673183/bjhysws_674671/bhflfg/dtdmxgfl/202303/P020230313585504979937.pdf
- PyShp：https://github.com/GeospatialPython/pyshp
- PyProj：https://pyproj4.github.io/pyproj/stable/
