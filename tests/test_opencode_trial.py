import importlib.util
import json
from pathlib import Path
import sys
import os
import tempfile
import unittest
from unittest.mock import patch, Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('opencode_trial',ROOT/'scripts/run_opencode_trial.py')
trial=importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class OpenCodeTrialTests(unittest.TestCase):
    def test_config_uses_secret_reference_and_denies_tools_and_other_providers(self):
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        result=trial.tool_config(cfg,32000)
        self.assertEqual(result['permission'],{'*':'deny'})
        self.assertEqual(result['enabled_providers'],['trial'])
        self.assertEqual(result['provider']['trial']['options']['apiKey'],'{env:SYNTHETIC_KEY}')
        self.assertEqual(result['provider']['trial']['models']['example']['limit']['output'],32000)

    def test_reasoning_is_not_collected_and_incomplete_finish_is_not_success(self):
        events=[{'type':'reasoning','part':{'text':'private reasoning'}},{'type':'text','part':{'text':'{"answer":1}'}},{'type':'step_finish','part':{'reason':'length'}}]
        text,summary,tools,finished=trial.collect_events('\n'.join(json.dumps(x) for x in events),'synthetic-secret')
        self.assertEqual(text,'{"answer":1}')
        self.assertFalse(finished)
        self.assertNotIn('private reasoning',json.dumps(summary))

    def test_project_task_only_allows_selected_interface(self):
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        result=trial.tool_config(cfg,32000,'low',{'name':'paper_project','command':['python','server.py','--workspace','work']})
        self.assertEqual(result['permission'],{'*':'deny','paper_project_*':'allow'})
        self.assertEqual(set(result['mcp']),{'paper_project'})
        self.assertEqual(result['provider']['trial']['models']['example']['options']['reasoningEffort'],'low')
        with self.assertRaises(ValueError):trial.tool_config(cfg,32000,project_tools={'name':'arbitrary','command':['shell']})

    def test_error_key_is_redacted_and_tool_calls_are_counted(self):
        events=[{'type':'error','error':{'message':'synthetic-secret'}},{'type':'tool_use'}]
        _,summary,tools,_=trial.collect_events('\n'.join(json.dumps(x) for x in events),'synthetic-secret')
        self.assertNotIn('synthetic-secret',json.dumps(summary))
        self.assertEqual(tools,1)

    def test_full_material_task_only_allows_readonly_input_interface(self):
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        result=trial.tool_config(cfg,16000,project_tools={'name':'case_materials','command':['python','case_materials_server.py','--materials','packet']})
        self.assertEqual(result['permission'],{'*':'deny','case_materials_*':'allow'})
        self.assertEqual(set(result['mcp']),{'case_materials'})
        self.assertNotIn('paper_project_*',result['permission'])
        with self.assertRaises(ValueError):
            trial.tool_config(cfg,16000,project_tools={'name':'case_materials','command':['python'],'extra':'unexpected'})

    def test_workflow_task_only_allows_its_selected_reviewed_interface(self):
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        result=trial.tool_config(cfg,16000,project_tools={'name':'workflow_project','command':['python','workflow_project_server.py']})
        self.assertEqual(result['permission'],{'*':'deny','workflow_project_*':'allow'})
        self.assertEqual(set(result['mcp']),{'workflow_project'})

    def test_responses_uses_official_sdk_without_changing_selected_tools(self):
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        result=trial.tool_config(cfg,8000,'low',{'name':'workflow_project','command':['python','server.py']},'responses')
        self.assertEqual(result['provider']['trial']['npm'],'@ai-sdk/openai')
        self.assertEqual(result['permission'],{'*':'deny','workflow_project_*':'allow'})
        self.assertEqual(result['provider']['trial']['options']['apiKey'],'{env:SYNTHETIC_KEY}')
        with self.assertRaises(ValueError):trial.tool_config(cfg,8000,protocol='unreviewed-protocol')

    def _record_trial(self, answer, tool_events=0):
        events=[{'type':'text','part':{'text':answer}}]
        events.extend({'type':'tool_use'} for _ in range(tool_events))
        events.append({'type':'step_finish','part':{'reason':'stop'}})
        proc=Mock(returncode=0)
        proc.communicate.return_value=('\n'.join(json.dumps(e) for e in events),'')
        cfg={'model':'example','base_url':'https://example.org','env_key':'SYNTHETIC_KEY'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            prompt=root/'prompt.txt'
            prompt.write_text('Read the source through the selected interface.',encoding='utf-8')
            with patch.dict(os.environ,{'SYNTHETIC_KEY':'synthetic-secret'}),patch.object(trial.subprocess,'Popen',return_value=proc):
                report=trial.run_trial('synthetic-opencode',cfg,prompt,root/'run',8000,
                                       project_tools={'name':'workflow_project','command':['python','server.py']},protocol='responses')
            self.assertEqual((root/'run'/'answer.txt').read_text(encoding='utf-8'),answer)
            self.assertEqual(json.loads((root/'run'/'run.json').read_text(encoding='utf-8')),report)
            self.assertNotIn('synthetic-secret',json.dumps(report))
            return report

    def test_text_pretending_to_call_a_tool_is_preserved_but_not_accepted(self):
        report=self._record_trial('<seed:tool_call><function name="bash">read sources</function></seed:tool_call>')
        self.assertTrue(report['successful_session'])
        self.assertTrue(report['simulated_tool_call_text_detected'])
        self.assertTrue(report['unexecuted_tool_intent'])
        self.assertFalse(report['answer_delivery_valid'])
        self.assertFalse(report['task_accepted'])

    def test_real_client_completion_does_not_certify_artifacts_or_science(self):
        report=self._record_trial('The input inventory was read.',tool_events=2)
        self.assertTrue(report['answer_delivery_valid'])
        self.assertEqual(report['tool_events'],2)
        self.assertFalse(report['unexecuted_tool_intent'])
        self.assertFalse(report['task_accepted'])


if __name__=='__main__':unittest.main()
