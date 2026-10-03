import importlib.util
import json
from pathlib import Path
import sys
import unittest
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


if __name__=='__main__':unittest.main()
