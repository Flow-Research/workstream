"""Isolation checks for the live guide drill; these do not certify product APIs."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/scripts"))
SPEC = importlib.util.spec_from_file_location("guide_document_api_drill", ROOT / "backend/scripts/guide_document_api_drill.py")
guide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guide)


class IsolationTests(unittest.TestCase):
    def test_sufficiency_response_rejects_empty_duplicate_or_foreign_lineage(self):
        setup = {"id": "setup-a", "output_sufficiency_report_id": "report-a",
                 "project_id": "project-a", "guide_id": "guide-a", "guide_version": "initial",
                 "source_snapshot_id": "snapshot-a", "setup_generation": 1}
        expected = {"id": "report-a", "project_setup_run_id": "setup-a",
                    **{key: value for key, value in setup.items()
                       if key not in {"id", "output_sufficiency_report_id"}}}
        self.assertTrue(guide.sufficiency_matches([expected], setup))
        invalid = [[], {}, [expected, expected], [None], [expected | {"setup_generation": True}]]
        invalid.extend([expected | {key: "foreign"}] for key in expected)
        invalid.extend([{key: value for key, value in expected.items() if key != omitted}]
                       for omitted in expected)
        import httpx
        for body in invalid:
            with self.subTest(body=body):
                with self.assertRaises(guide.api.ProbeFailure):
                    guide.api.verify_response(httpx.Response(200, json=body), 200, {},
                        checks={"$": lambda value: guide.sufficiency_matches(value, setup)})
        self.assertEqual(guide.api.verify_response(httpx.Response(200, json=[expected]), 200, {},
            checks={"$": lambda value: guide.sufficiency_matches(value, setup)}), [expected])

    def runtime(self):
        return {
            "WORKSTREAM_DRILL_PROVIDER_ENV": "/private/provider.env",
            "WORKSTREAM_TEST_MINIO_ENDPOINT": "http://127.0.0.1:9000",
            "WORKSTREAM_DRILL_BROKER_URL": "redis://127.0.0.1:12345/0",
            "WORKSTREAM_TEST_MINIO_BUCKET": "owned-bucket",
            "WORKSTREAM_TEST_MINIO_PREFIX": "owned-prefix",
            "WORKSTREAM_DRILL_SCRATCH_ROOT": "/private/owned-scratch",
        }

    def test_provider_file_cannot_override_isolated_database_identity_or_storage(self):
        provider = {"OPENAI_API_KEY": "not-a-real-key", "WORKSTREAM_PROJECT_AGENT_MODEL": "configured-model",
                    "WORKSTREAM_DATABASE_URL": "production-database", "WORKSTREAM_AUTH_PROVIDER": "unsafe",
                    "WORKSTREAM_ARTIFACT_S3_BUCKET": "production-bucket"}
        env = {"WORKSTREAM_DATABASE_URL": "isolated-database", "WORKSTREAM_AUTH_PROVIDER": "flow"}
        report = {}
        with patch.dict(guide.os.environ, self.runtime(), clear=True), patch.object(guide, "dotenv_values", return_value=provider):
            guide.environment(env, report)
        self.assertEqual(env["WORKSTREAM_DATABASE_URL"], "isolated-database")
        self.assertEqual(env["WORKSTREAM_AUTH_PROVIDER"], "flow")
        self.assertEqual(env["WORKSTREAM_ARTIFACT_S3_BUCKET"], "owned-bucket")
        self.assertEqual(env["WORKSTREAM_PROJECT_AGENT_MODEL"], "configured-model")
        for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
            self.assertGreater(int(env[f"WORKSTREAM_ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"]), 0)
        self.assertNotIn("not-a-real-key", str(report))

    def test_remote_runtime_is_rejected(self):
        for key in ("WORKSTREAM_TEST_MINIO_ENDPOINT", "WORKSTREAM_DRILL_BROKER_URL"):
            with self.subTest(key=key), patch.dict(guide.os.environ, self.runtime() | {key: "https://remote.example"}, clear=True), patch.object(guide, "dotenv_values", return_value={"OPENAI_API_KEY": "test"}):
                with self.assertRaises(guide.api.ProbeFailure):
                    guide.environment({}, {})


if __name__ == "__main__":
    unittest.main()
