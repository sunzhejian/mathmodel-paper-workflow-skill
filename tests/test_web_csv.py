import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for CSV helper comparison")
class WebCSVTests(unittest.TestCase):
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
