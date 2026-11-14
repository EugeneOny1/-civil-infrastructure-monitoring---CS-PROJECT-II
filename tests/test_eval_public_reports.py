import unittest
import subprocess
import json
import sys

class TestEvalPublicReports(unittest.TestCase):
    def run_eval(self, payload_str, limit="3"):
        res = subprocess.run(
            [sys.executable, 'backend/scripts/eval_public_reports.py', payload_str, limit],
            capture_output=True, text=True
        )
        return res.returncode, res.stdout.strip()

    def test_01_empty_database_response_is_valid(self):
        empty_payload = json.dumps({"reports": [], "count": 0})
        rc, out = self.run_eval(empty_payload)
        self.assertEqual(rc, 0)
        self.assertIn("VALID", out)

    def test_02_populated_reports_are_valid(self):
        pop_payload = json.dumps({
            "reports": [
                {"report_id": "rep_1", "display_id": "REP-2026-0001", "status": "Received", "defect_class": "Pothole"},
                {"report_id": "rep_2", "display_id": "REP-2026-0002", "status": "Under Review", "defect_class": "Crack"}
            ],
            "count": 2
        })
        rc, out = self.run_eval(pop_payload, "3")
        self.assertEqual(rc, 0)
        self.assertIn("VALID", out)

    def test_03_error_payload_fails_explicitly(self):
        err_payload = json.dumps({"error": "Database unreachable"})
        rc, out = self.run_eval(err_payload)
        self.assertEqual(rc, 5)
        self.assertIn("API_ERROR", out)

    def test_04_bare_list_fails_contract_check(self):
        bare_list = json.dumps([{"report_id": "rep_1"}])
        rc, out = self.run_eval(bare_list)
        self.assertEqual(rc, 4)
        self.assertIn("CONTRACT_MISMATCH", out)

    def test_05_limit_exceeded_fails(self):
        overflow_payload = json.dumps({
            "reports": [{"report_id": f"rep_{i}", "display_id": f"REP-{i}"} for i in range(5)],
            "count": 5
        })
        rc, out = self.run_eval(overflow_payload, "3")
        self.assertEqual(rc, 11)
        self.assertIn("LIMIT_EXCEEDED", out)

    def test_06_privacy_leak_fails(self):
        pii_payload = json.dumps({
            "reports": [{"report_id": "rep_1", "display_id": "REP-1", "user_id": "6732a..."}],
            "count": 1
        })
        rc, out = self.run_eval(pii_payload)
        self.assertEqual(rc, 13)
        self.assertIn("PRIVACY_VIOLATION", out)

if __name__ == '__main__':
    unittest.main()
