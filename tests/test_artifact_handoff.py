import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

PATH = Path(__file__).resolve().parents[1] / "scripts/check_artifact_handoff.py"
SPEC = importlib.util.spec_from_file_location("check_artifact_handoff", PATH)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "user-project"
        self.candidate = self.root / "execution-snapshot"
        self.download = self.root / "actual-download"
        for root in (self.project, self.candidate, self.download):root.mkdir()
        self.data = b"time,value\n0,2.55\n1,2.54\n"
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.contract = {"schema_version": 1, "artifacts": [{"path": "result/result1.csv", "sha256": self.sha}]}
        self.listing = {"files": [{"path": "result/result1.csv", "sha256": self.sha}]}

    def put(self, root, name="result/result1.csv", data=None):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.data if data is None else data)
        return p

    def run_check(self, **kwargs):
        return m.check(self.contract, self.project, self.listing, candidate_root=self.candidate, **kwargs)

    def test_candidate_snapshot_and_exit_success_are_not_delivery(self):
        self.put(self.candidate)
        self.listing = {"files": []}
        result = self.run_check()
        self.assertFalse(result["handoff_verified"])
        self.assertEqual(result["artifacts"][0]["status"], "candidate_only")
        self.assertTrue(result["artifacts"][0]["candidate"]["hash_matches"])
        self.assertFalse((self.project / "result/result1.csv").exists())

    def test_project_file_not_listed_by_host_is_not_registered(self):
        self.put(self.project)
        self.listing = {"files": []}
        result = self.run_check()
        self.assertEqual(result["artifacts"][0]["status"], "host_registration_missing")
        self.assertFalse(result["handoff_verified"])

    def test_listed_project_file_still_needs_delivery_readback(self):
        self.put(self.project)
        result = self.run_check()
        self.assertEqual(result["artifacts"][0]["status"], "delivery_readback_missing")

    def test_registered_custom_output_directory_and_download_pass(self):
        for name in ("result/q1.csv", "results_full/q1.csv", "code/outputs/q1.csv"):
            with self.subTest(name=name):
                self.contract["artifacts"][0]["path"] = name
                self.listing = {"files": [{"path": name}]}
                self.put(self.project, name)
                self.put(self.download, name)
                result = self.run_check(download_root=self.download)
                self.assertTrue(result["handoff_verified"])
                self.assertFalse(result["scientific_correctness_verified"])

    def test_archive_matching_bytes_pass_without_download(self):
        self.put(self.project)
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("result/result1.csv", self.data)
        self.assertTrue(self.run_check(archive=archive)["handoff_verified"])

    def test_wrong_archive_or_download_bytes_fail(self):
        self.put(self.project)
        self.put(self.download, data=b"stale download")
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("result/result1.csv", b"stale archive")
        self.assertFalse(self.run_check(download_root=self.download, archive=archive)["handoff_verified"])

    def test_good_download_cannot_hide_stale_archive(self):
        self.put(self.project)
        self.put(self.download)
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("result/result1.csv", b"stale archive")
        result = self.run_check(download_root=self.download, archive=archive)
        self.assertTrue(result["artifacts"][0]["download"]["hash_matches"])
        self.assertFalse(result["handoff_verified"])

    def test_stale_current_file_or_listing_hash_fails(self):
        self.put(self.project, data=b"stale current")
        self.put(self.download)
        self.assertFalse(self.run_check(download_root=self.download)["handoff_verified"])
        self.put(self.project)
        self.listing["files"][0]["sha256"] = "0" * 64
        self.assertFalse(self.run_check(download_root=self.download)["handoff_verified"])

    def test_explicit_candidate_and_archive_name_mapping(self):
        self.contract["artifacts"][0].update(candidate_path="results_full/q1.csv", archive_path="support/q1.csv")
        self.put(self.candidate, "results_full/q1.csv")
        self.put(self.project)
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("support/q1.csv", self.data)
        result = self.run_check(archive=archive)
        self.assertTrue(result["handoff_verified"])
        self.assertTrue(result["artifacts"][0]["candidate"]["hash_matches"])

    def test_missing_archive_member_fails(self):
        self.put(self.project)
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("other.csv", self.data)
        self.assertFalse(self.run_check(archive=archive)["handoff_verified"])

    def test_case_collisions_or_traversal_are_rejected(self):
        self.contract["artifacts"].append({"path": "Result/RESULT1.csv", "sha256": self.sha})
        with self.assertRaises(ValueError):self.run_check()
        self.contract["artifacts"] = [{"path": "../outside.csv", "sha256": self.sha}]
        with self.assertRaises(ValueError):self.run_check()
        self.contract["artifacts"] = [{"path": "result/result1.csv", "sha256": self.sha}]
        archive = self.root / "support.zip"
        with zipfile.ZipFile(archive, "w") as z:z.writestr("../outside.csv", self.data)
        with self.assertRaises(ValueError):self.run_check(archive=archive)

    def test_host_listing_case_different_from_contract_does_not_silently_pass(self):
        self.put(self.project)
        self.put(self.download)
        self.listing = {"files": [{"path": "Result/result1.csv", "sha256": self.sha}]}
        self.assertFalse(self.run_check(download_root=self.download)["handoff_verified"])

    def test_inspection_never_changes_existing_files(self):
        original = self.put(self.project)
        self.put(self.candidate)
        self.put(self.download)
        self.assertTrue(self.run_check(download_root=self.download)["handoff_verified"])
        self.assertEqual(original.read_bytes(), self.data)


if __name__ == "__main__":
    unittest.main()
