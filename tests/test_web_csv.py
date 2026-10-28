import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for CSV helper comparison")
class WebCSVTests(unittest.TestCase):
    def test_direct_cli_collection_rejects_changed_raw_before_cleaning_and_sentiment(self):
        script = """import{collectPublicMain,crawlPublicData}from'./scripts/collect_public_web.mjs';
import{corpusMain}from'./scripts/prepare_text_corpus.mjs';
import{sentimentMain}from'./scripts/text_sentiment_baseline.mjs';
import{writeFile,readFile,appendFile,stat}from'node:fs/promises';import assert from'node:assert/strict';
const dir=process.argv[1],config=dir+'/request.json',collected=dir+'/collected',clean=dir+'/clean';
await writeFile(config,JSON.stringify({urls:['https://example.test/answers.csv'],csv_text_column:'comment'}));
const result=await collectPublicMain([config,collected],{crawl:input=>crawlPublicData(input,{request:async url=>({status:200,headers:{'content-type':url.endsWith('/robots.txt')?'text/plain':'text/csv'},bytes:Buffer.from(url.endsWith('/robots.txt')?'User-agent: *':'id,comment\\n1,好用\\n2,不好用')})})});
assert.equal(result.records,2);const source=JSON.parse(await readFile(collected+'/texts.json','utf8'));
assert.equal(source.web_collection.inputs.length,1);await corpusMain([collected+'/texts.json',clean]);
await corpusMain([clean+'/texts.json',dir+'/reclean']);
await appendFile(source.web_collection.inputs[0].path,'\\nchanged');
await assert.rejects(corpusMain([collected+'/texts.json',dir+'/bad-clean']),/source changed/);
await assert.rejects(corpusMain([clean+'/texts.json',dir+'/bad-reclean']),/source changed/);
await assert.rejects(sentimentMain([clean+'/texts.json',dir+'/bad-sentiment']),/source changed/);
await assert.rejects(stat(dir+'/bad-clean'));await assert.rejects(stat(dir+'/bad-reclean'));await assert.rejects(stat(dir+'/bad-sentiment'));
console.log(JSON.stringify({direct_raw_bound:true,both_stages_reject_changed_raw:true}));"""
        with tempfile.TemporaryDirectory(prefix="mathmodel-csv-source-test-") as out:
            p = subprocess.run(["node", "--input-type=module", "-e", script, out],
                               text=True, encoding="utf-8", capture_output=True, cwd=ROOT, check=True)
            self.assertTrue(json.loads(p.stdout)["both_stages_reject_changed_raw"])

    def extract(self, text, options):
        script = """import{csvOptions,parseCSVText}from'./scripts/web_csv.mjs';
let s='';for await(const c of process.stdin)s+=c;const x=JSON.parse(s);
console.log(JSON.stringify(parseCSVText(x.text,csvOptions(x.options))));"""
        p = subprocess.run(["node", "--input-type=module", "-e", script],
                           input=json.dumps(dict(text=text, options=options), ensure_ascii=False),
                           text=True, encoding="utf-8", capture_output=True, cwd=ROOT, check=True)
        return json.loads(p.stdout)

    def test_rfc_fields_match_python_csv_without_dropping_duplicate_or_empty_answers(self):
        text = 'id,评价\r\n1,"好用,便宜"\r\n2,"他说""满意"""\r\n3,"跨行\r\n文本"\r\n4,0\r\n5,\r\n6,重复\r\n7,重复\r\n\r\n'
        expected = [r for r in csv.reader(io.StringIO(text, newline="")) if r]
        actual = self.extract(text, dict(csv_text_column="评价"))
        self.assertEqual(actual["columns"], expected[0])
        self.assertEqual(actual["rows"], expected[1:])
        self.assertEqual(actual["metadata"]["skipped_blank_lines"], 1)

    def test_explicit_headerless_semicolon_and_tab_match_python(self):
        for delimiter, text in [(";", '1;"好用;满意"\n2;"不好用"\n'),
                                ("\t", '1\t"含\t制表符"\r\n2\t0')]:
            actual = self.extract(text, dict(csv_text_column_index=1, csv_has_header=False,
                                            csv_delimiter=delimiter))
            self.assertEqual(actual["rows"], list(csv.reader(io.StringIO(text, newline=""),
                                                             delimiter=delimiter)))
            self.assertIsNone(actual["columns"])


if __name__ == "__main__":
    unittest.main()
