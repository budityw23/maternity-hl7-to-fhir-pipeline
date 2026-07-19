import json
import os
import tempfile

from app.errors import problem_response, write_deadletter


class TestProblemResponse:
    def test_status_code(self):
        resp = problem_response(422, "Validation Error", "Missing field")
        assert resp.status_code == 422

    def test_content_type(self):
        resp = problem_response(422, "Validation Error", "Missing field")
        assert resp.media_type == "application/problem+json"

    def test_body_structure(self):
        resp = problem_response(
            422, "Validation Error", "Missing field", correlation_id="abc-123"
        )
        body = json.loads(resp.body)
        assert body["type"] == "about:blank"
        assert body["title"] == "Validation Error"
        assert body["status"] == 422
        assert body["detail"] == "Missing field"
        assert body["correlationId"] == "abc-123"

    def test_body_without_correlation_id(self):
        resp = problem_response(500, "Error", "Something broke")
        body = json.loads(resp.body)
        assert "correlationId" not in body

    def test_body_with_errors(self):
        errors = [{"field": "mrn", "message": "required"}]
        resp = problem_response(422, "Validation Error", "Bad input", errors=errors)
        body = json.loads(resp.body)
        assert len(body["errors"]) == 1
        assert body["errors"][0]["field"] == "mrn"


class TestWriteDeadletter:
    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("DEADLETTER_DIR")
            os.environ["DEADLETTER_DIR"] = tmpdir
            try:
                filename = write_deadletter(
                    payload={"mrn": "123"},
                    error_detail="test error",
                    correlation_id="corr-001",
                )
                assert filename is not None
                filepath = os.path.join(tmpdir, filename)
                assert os.path.exists(filepath)
                with open(filepath, encoding="utf-8") as file:
                    content = json.load(file)
                assert content["error"] == "test error"
                assert content["correlationId"] == "corr-001"
                assert content["payload"] == {"mrn": "123"}
            finally:
                if previous is None:
                    os.environ.pop("DEADLETTER_DIR", None)
                else:
                    os.environ["DEADLETTER_DIR"] = previous

    def test_filename_contains_correlation_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("DEADLETTER_DIR")
            os.environ["DEADLETTER_DIR"] = tmpdir
            try:
                filename = write_deadletter(
                    payload={},
                    error_detail="err",
                    correlation_id="abcdef12-rest-of-uuid",
                )
                assert filename is not None
                assert "abcdef12" in filename
            finally:
                if previous is None:
                    os.environ.pop("DEADLETTER_DIR", None)
                else:
                    os.environ["DEADLETTER_DIR"] = previous

    def test_handles_no_correlation_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("DEADLETTER_DIR")
            os.environ["DEADLETTER_DIR"] = tmpdir
            try:
                filename = write_deadletter(
                    payload={},
                    error_detail="err",
                    correlation_id=None,
                )
                assert filename is not None
            finally:
                if previous is None:
                    os.environ.pop("DEADLETTER_DIR", None)
                else:
                    os.environ["DEADLETTER_DIR"] = previous
