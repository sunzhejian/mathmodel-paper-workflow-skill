"""Generate original editable explanatory draw.io diagrams (standard library only)."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


class Diagram:
    def __init__(self, title, subtitle):
        self.xml = ET.Element('mxfile', host='app.diagrams.net')
        page = ET.SubElement(self.xml, 'diagram', id='workflow', name='Page-1')
        model = ET.SubElement(page, 'mxGraphModel', page='1', pageWidth='1400', pageHeight='900',
                              grid='1', gridSize='10', background='#ffffff')
        self.root = ET.SubElement(model, 'root')
        ET.SubElement(self.root, 'mxCell', id='0')
        ET.SubElement(self.root, 'mxCell', id='1', parent='0')
        self.count = 1
        self.box(title, 45, 30, 1310, 55, fill='none', size=30, bold=True, border='none')
        self.box(subtitle, 45, 90, 1310, 42, fill='none', size=18, border='none')

    def box(self, text, x, y, w, h, fill='#eef6fd', size=20, bold=False, border='#3b547f'):
        self.count += 1
        cell = ET.SubElement(self.root, 'mxCell', id=str(self.count), value=text.replace('\n', '<br>'),
            style=f'rounded=0;whiteSpace=wrap;html=1;align=center;verticalAlign=middle;spacing=12;'
                  f'fontFamily=Microsoft YaHei;fontSize={size};fontColor=#172b43;fontStyle={1 if bold else 0};'
                  f'fillColor={fill};strokeColor={border};strokeWidth=1.4;', vertex='1', parent='1')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), **{'as': 'geometry'})

    def arrow(self, x1, y1, x2, y2, waypoints=(), dashed=False):
        self.count += 1
        cell = ET.SubElement(self.root, 'mxCell', id=str(self.count),
            style=f'edgeStyle=none;html=1;endArrow=block;endFill=1;strokeColor=#52697d;strokeWidth=2;dashed={int(dashed)};', edge='1', parent='1')
        geo = ET.SubElement(cell, 'mxGeometry', relative='1', **{'as': 'geometry'})
        ET.SubElement(geo, 'mxPoint', x=str(x1), y=str(y1), **{'as': 'sourcePoint'})
        ET.SubElement(geo, 'mxPoint', x=str(x2), y=str(y2), **{'as': 'targetPoint'})
        if waypoints:
            array = ET.SubElement(geo, 'Array', **{'as': 'points'})
            for x, y in waypoints:
                ET.SubElement(array, 'mxPoint', x=str(x), y=str(y))

    def save(self, path):
        ET.indent(self.xml)
        ET.ElementTree(self.xml).write(path, encoding='utf-8', xml_declaration=True)


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    d = Diagram('01  多技能怎样协作', '从现有成果接续；按任务选用技能，不把“已安装”当成“已执行”')
    xs = [45, 385, 725, 1065]
    stages = [
        ('题意与模型', 'MathModelAgent\n1start / 2analysis\n输入与假设 → 逐问方案'),
        ('求解与图形', '3coding / figure-templates\n4drawio / scibox-diagram\n原精度结果 → 数据图与线稿'),
        ('论文与编译', '5writing / 已有 mma-paper\n逐问公式、结果与解释\n源文件 → PDF / Word'),
        ('审查与交付', '6verity / 本仓库工具\n逐页检查 → 原附录接回\n验收报告 → 支撑包')]
    for x, (title, content) in zip(xs, stages):
        d.box(title, x, 185, 290, 65, bold=True)
        d.box(content, x, 270, 290, 150, size=18)
    for x in xs[:-1]:
        d.arrow(x+292, 217, x+338, 217)
    d.box('BZD 专项审查', 45, 480, 1310, 55, fill='#e5dfeb', border='#9b979f', bold=True)
    d.box('假设与模型求解\n有专项执行报告', 45, 555, 405, 95, fill='#e5dfeb', border='#9b979f')
    d.box('摘要、符号、格式、文献\n按需要调用并记录证据', 497, 555, 405, 95, fill='#e5dfeb', border='#9b979f')
    d.box('问题返回对应阶段\n模型错回求解，版式错回排版', 950, 555, 405, 95, fill='#e5dfeb', border='#9b979f')
    for x in xs:
        d.arrow(x+145, 478, x+145, 422, dashed=True)
    d.box('工具选择不是结果证明：Origin 为可选路线；该项目指定曲线最终由 Python 生成并核验', 45, 705, 1310, 65,
          fill='#fcead9', border='#c08b5c', size=20)
    d.box('技能入口去重：scibox-figure 的 name 可能就是 mathmodel-figure-templates', 45, 805, 1310, 45,
          fill='none', border='none', size=18)
    d.save(directory/'01-skill-map.drawio')

    d = Diagram('02  结果怎样进入论文', '保留完整精度的证据链：每个结论都能回到输入、脚本、参数和运行记录')
    top = [('题面与附件', '字段 · 单位 · 文件哈希'), ('逐问独立入口', '方程 · 假设 · 参数 · 环境'),
           ('原精度结果', '数组 · 元数据 · 收敛记录\n核验通过后再分流'), ('验证并反馈', '解析对照 · 网格 · 边界')]
    for x, (a, b) in zip(xs, top):
        d.box(a+'\n'+b, x, 190, 290, 130, bold=True, size=18)
    for x in xs[:-1]:
        d.arrow(x+292, 255, x+338, 255)
    d.arrow(1210, 188, 870, 188, [(1210, 155), (870, 155)], dashed=True)
    d.box('判据分支\n阈值、事件、误差计算\n始终使用未舍入值', 190, 425, 440, 135, fill='#dbeef4', border='#668d89')
    d.box('展示分支\n表格格式、坐标轴与摘要\n仅在显示时取约定小数位', 770, 425, 440, 135, fill='#dbeef4', border='#668d89')
    d.arrow(850, 322, 410, 423, [(850, 370), (410, 370)])
    d.arrow(895, 322, 990, 423, [(895, 385), (990, 385)])
    d.box('正文中的每一问\n方法 → 关键公式与范围 → 数值结果 → 物理/业务含义 → 适用边界', 190, 650, 1020, 110,
          fill='#e5dfeb', border='#9b979f')
    d.arrow(410, 562, 410, 648)
    d.arrow(990, 562, 990, 648)
    d.box('同一份结果驱动表格、数据图和文字；示意图单独标明几何关系，不伪装成实测图', 45, 805, 1310, 45,
          fill='none', border='none', size=18)
    d.save(directory/'02-evidence-chain.drawio')

    d = Diagram('03  排版验收与附录保真', '先完成正文迭代，再接回原附录；量化留白与人工视觉检查缺一不可')
    for x, text in [(45, '修改源文件\n段落、图宽、浮动体'), (385, '编译正文\n检查引用、缺字、越界'),
                    (725, '自动检查\n页数、公式文本、留白'), (1065, '逐页看图\n遮挡、透视、图文顺序')]:
        d.box(text, x, 190, 290, 120, size=20)
    for x in xs[:-1]:
        d.arrow(x+292, 250, x+338, 250)
    d.arrow(1210, 312, 190, 312, [(1210, 365), (190, 365)], dashed=True)
    d.box('未通过：返回源文件修改并重编译', 430, 385, 540, 50, fill='none', border='none', size=18)
    d.box('通过后接回原附录\n按原 PDF 物理页选取\n不重建用户手改内容', 45, 515, 370, 130, fill='#dbeef4', border='#668d89')
    d.box('逐页保真比对\n文字 + 渲染像素\n加页码只使用空白页脚', 515, 515, 370, 130, fill='#dbeef4', border='#668d89')
    d.box('最终交付\nPDF / 按需 Word / 源文件\n白名单 ZIP + 哈希清单', 985, 515, 370, 130, fill='#dbeef4', border='#668d89')
    d.arrow(417, 580, 513, 580)
    d.arrow(887, 580, 983, 580)
    d.arrow(1357, 250, 43, 580, [(1380, 250), (1380, 465), (25, 465), (25, 580)])
    d.box('留白口径：版心内“整行宽度连续空白高度” ÷ 版心高度\n20% 是示例阈值，不是整页白色像素比例；自动指标不能发现全部重叠', 45, 725, 1310, 100,
          fill='#fcead9', border='#c08b5c', size=20)
    d.save(directory/'03-layout-loop.drawio')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='docs/figures')
    generate(parser.parse_args().output)
