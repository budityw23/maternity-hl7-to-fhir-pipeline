import json
import logging

from app.logging_setup import JsonFormatter, correlation_id_var, setup_logging


class TestJsonFormatter:
    def test_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"

    def test_includes_correlation_id_from_context(self):
        formatter = JsonFormatter()
        token = correlation_id_var.set("abc-123")
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["correlationId"] == "abc-123"
        finally:
            correlation_id_var.reset(token)

    def test_empty_correlation_id_when_not_set(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["correlationId"] == ""

    def test_includes_timestamp(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed

    def test_includes_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="error",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "ValueError: boom" in parsed["exception"]


class TestSetupLogging:
    def test_sets_root_level(self):
        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG
        setup_logging("INFO")

    def test_suppresses_uvicorn_access(self):
        setup_logging("INFO")
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
