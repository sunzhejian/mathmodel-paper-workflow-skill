"""Check declared node/edge coverage against an actual editable draw.io file.

Topology agreement is not proof that scientific claims or rendered labels are correct.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def inspect(diagram,contract):
    c=json.loads(contract.read_text(encoding='utf-8'))
    root=ET.parse(diagram).getroot();cells=list(root.iter('mxCell'));ids=[x.get('id') for x in cells]
    nodes={x.get('id') for x in cells if x.get('vertex')=='1'}
    edges=[(x.get('source'),x.get('target')) for x in cells if x.get('edge')=='1']
    expected_nodes=set(c['nodes']);expected_edges=[tuple(x) for x in c['edges']];errors=[]
    if len(ids)!=len(set(ids)):errors.append('Duplicate cell identifiers')
    if nodes!=expected_nodes:errors.append('Missing or unexpected declared nodes: '+str(sorted(nodes^expected_nodes)))
    if sorted(edges)!=sorted(expected_edges):errors.append('Missing, extra or reversed declared edges')
    if any(a not in nodes or b not in nodes for a,b in edges):errors.append('Connector references a non-native or absent endpoint')
    if any(x.tag.endswith('image') or 'image=' in (x.get('style') or '') for x in root.iter()):errors.append('Raster content in a declared native-only mechanism')
    return {'passed':not errors,'errors':errors,'native_nodes':len(nodes),'native_edges':len(edges),
            'scope':'contract topology and native cells only; scientific/source review and renderer checks remain separate'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('diagram',type=Path);p.add_argument('--contract',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();r=inspect(a.diagram,a.contract)
    with a.report.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(r,ensure_ascii=False));return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
