import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('mechanism',Path(__file__).resolve().parents[1]/'scripts/check_mechanism_figure.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MechanismTests(unittest.TestCase):
    def run_fixture(self,edge,extra=''):
        with tempfile.TemporaryDirectory() as folder:
            r=Path(folder);d=r/'figure.drawio';c=r/'contract.json'
            d.write_text('<mxfile><mxCell id="a" vertex="1"/><mxCell id="b" vertex="1"/>'+edge+extra+'</mxfile>',encoding='utf-8')
            c.write_text(json.dumps({'nodes':['a','b'],'edges':[['a','b']]}),encoding='utf-8')
            return m.inspect(d,c)
    def test_native_endpoint_topology(self):
        self.assertTrue(self.run_fixture('<mxCell id="e" edge="1" source="a" target="b"/>')['passed'])
    def test_reversed_connector_is_not_equivalent(self):
        self.assertFalse(self.run_fixture('<mxCell id="e" edge="1" source="b" target="a"/>')['passed'])
    def test_duplicate_native_id_and_raster_fail(self):
        r=self.run_fixture('<mxCell id="e" edge="1" source="a" target="b"/>','<mxCell id="a" style="image=data:image/png;"/>')
        self.assertFalse(r['passed']);self.assertEqual(len(r['errors']),2)
    def test_absent_connector_endpoint_fails(self):
        r=self.run_fixture('<mxCell id="e" edge="1" source="a" target="missing"/>')
        self.assertFalse(r['passed']);self.assertEqual(len(r['errors']),2)
if __name__=='__main__':unittest.main()
