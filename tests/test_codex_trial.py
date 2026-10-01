import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codex_trial',ROOT/'scripts/run_codex_trial.py')
trial=importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class CodexTrialTests(unittest.TestCase):
    def test_report_omits_reasoning_and_redacts_errors(self):
        secret='synthetic-test-credential-not-a-provider-key'
        events=[{'type':'item.completed','item':{'type':'reasoning','text':'private reasoning'}},
                {'type':'item.completed','item':{'type':'command_execution'}},
                {'type':'error','message':'Auth failed '+secret},
                {'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':3}}]
        result,tools=trial.safe_events('\n'.join(json.dumps(x) for x in events),secret)
        rendered=json.dumps(result)
        self.assertNotIn(secret,rendered)
        self.assertNotIn('private reasoning',rendered)
        self.assertEqual(tools,1)
        self.assertEqual(result[-1]['usage']['input_tokens'],12)

    def test_routes_reject_inline_credentials_and_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'routes.json'
            for config in [{'base_url':'https://example.org','model':'example','env_key':'TEST','api_key':'forbidden'},
                           {'base_url':'http://example.org','model':'example','env_key':'TEST'},
                           {'base_url':'https://secret@example.org','model':'example','env_key':'TEST'}]:
                path.write_text(json.dumps({'route':config}),encoding='utf-8')
                with self.assertRaises(ValueError):trial.route_config(path,'route')

    def test_missing_key_or_key_in_prompt_makes_no_request(self):
        cfg={'base_url':'https://example.org','model':'example','env_key':'MM_TEST_ONLY_KEY'}
        with tempfile.TemporaryDirectory() as temp:
            prompt=Path(temp)/'prompt.txt'
            output=Path(temp)/'out'
            prompt.write_text('test',encoding='utf-8')
            with patch.dict(os.environ,{},clear=True),patch.object(trial.subprocess,'Popen') as process:
                with self.assertRaises(ValueError):trial.run_trial('unused',cfg,prompt,output,'low',30)
                process.assert_not_called()
            prompt.write_text('contains synthetic-private-secret',encoding='utf-8')
            with patch.dict(os.environ,{'MM_TEST_ONLY_KEY':'synthetic-private-secret'},clear=True),patch.object(trial.subprocess,'Popen') as process:
                with self.assertRaises(ValueError):trial.run_trial('unused',cfg,prompt,output,'low',30)
                process.assert_not_called()
            self.assertFalse(output.exists())

    def test_existing_trial_is_preserved(self):
        cfg={'base_url':'https://example.org','model':'example','env_key':'MM_TEST_ONLY_KEY'}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            prompt=root/'prompt.txt'
            prompt.write_text('test',encoding='utf-8')
            output=root/'out'
            output.mkdir()
            sentinel=output/'keep.txt'
            sentinel.write_text('preserve',encoding='utf-8')
            with patch.dict(os.environ,{'MM_TEST_ONLY_KEY':'synthetic-private-secret'}),patch.object(trial.subprocess,'Popen') as process:
                with self.assertRaises(FileExistsError):trial.run_trial('unused',cfg,prompt,output,'low',30)
                process.assert_not_called()
            self.assertEqual(sentinel.read_text(),'preserve')

    def test_incomplete_response_does_not_become_success(self):
        cfg={'base_url':'https://example.org','model':'example','env_key':'MM_TEST_ONLY_KEY'}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            prompt=root/'prompt.txt'
            prompt.write_text('test',encoding='utf-8')
            with patch.dict(os.environ,{'MM_TEST_ONLY_KEY':'synthetic-private-secret'}),patch.object(trial.subprocess,'Popen') as mocked:
                process=mocked.return_value
                process.communicate.return_value=(json.dumps({'type':'turn.failed','error':{'message':'Incomplete response returned, reason: length'}}),'')
                process.returncode=1
                result=trial.run_trial('unused',cfg,prompt,root/'out','low',30)
                self.assertFalse(result['answer_present'])
                self.assertEqual(result['exit_code'],1)
                self.assertNotIn('synthetic-private-secret',json.dumps(mocked.call_args.args))


if __name__=='__main__':unittest.main()
