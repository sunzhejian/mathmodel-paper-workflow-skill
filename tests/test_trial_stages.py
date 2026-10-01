import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('merge_stages',ROOT/'scripts/merge_trial_stages.py')
stages=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stages)


def stage(root,part,round_name='clarified',exit_code=0):
    parent=root/part
    directory=parent/'model'
    directory.mkdir(parents=True)
    prompt=parent/'prompt.txt'
    prompt.write_text('anonymous '+part,encoding='utf-8')
    answer=directory/'answer.json'
    answer.write_text(json.dumps({part:{'result':42}}),encoding='utf-8')
    (parent/'manifest.json').write_text(json.dumps({'part':part,'round':round_name,'task_schema_version':2,'task_sha256':'task','context_sha256':{'skill':'context'}}),encoding='utf-8')
    (directory/'run.json').write_text(json.dumps({'exit_code':exit_code,'timed_out':False,'answer_present':True,'tool_events':0,'answer_sha256':hashlib.sha256(answer.read_bytes()).hexdigest(),'prompt_sha256':hashlib.sha256(prompt.read_bytes()).hexdigest(),'model':'synthetic','base_url':'https://example.org','reasoning_effort':'low'}),encoding='utf-8')
    return directory


class TrialStageTests(unittest.TestCase):
    def test_matching_stages_assemble_without_claiming_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            a=stage(root,'transport')
            b=stage(root,'inference')
            before=(a/'answer.json').read_bytes()
            r=stages.merge(a,b,root/'assembled')
            self.assertEqual(set(json.loads((root/'assembled/answer.json').read_text())),{'transport','inference'})
            self.assertEqual(before,(a/'answer.json').read_bytes())
            self.assertFalse(r['code_executed'])
            self.assertFalse(r['numeric_checks_executed'])

    def test_different_rounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):stages.merge(stage(root,'transport'),stage(root,'inference','new_data'),root/'assembled')
            self.assertFalse((root/'assembled').exists())

    def test_changed_answer_and_prompt_are_rejected(self):
        for changed in ['answer','prompt']:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                a=stage(root,'transport')
                b=stage(root,'inference')
                path=a/'answer.json' if changed=='answer' else a.parent/'prompt.txt'
                path.write_text('{}',encoding='utf-8')
                with self.assertRaises(ValueError):stages.merge(a,b,root/'assembled')

    def test_incomplete_stage_is_not_patched_into_a_complete_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):stages.merge(stage(root,'transport',exit_code=1),stage(root,'inference'),root/'assembled')


if __name__=='__main__':unittest.main()
