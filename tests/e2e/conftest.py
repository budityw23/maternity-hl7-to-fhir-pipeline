"""E2E test fixtures — requires live Docker stack (./scripts/up.sh)."""

import os
import socket
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "fastapi"))

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
HAPI_URL = os.getenv("HAPI_URL", "http://localhost:8081/fhir")
MLLP_HOST = os.getenv("MLLP_HOST", "localhost")
MLLP_PORT = int(os.getenv("MLLP_PORT", "6661"))

VT = b"\x0b"
FS = b"\x1c"
CR = b"\x0d"


def _check_stack_health() -> bool:
    """Return True if FastAPI health endpoint is reachable."""
    try:
        r = httpx.get(f"{FASTAPI_URL}/health", timeout=5)
        return r.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def pytest_configure(config):  # type: ignore[no-untyped-def]
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests requiring live Docker stack (Mirth + FastAPI + HAPI)",
    )


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """Skip E2E tests if the Docker stack is not running."""
    if not _check_stack_health():
        skip = pytest.mark.skip(reason="Docker stack not running (FastAPI health check failed)")
        for item in items:
            if "e2e" in item.keywords or "tests/e2e" in str(item.fspath):
                item.add_marker(skip)


def _mllp_send(hl7_path: str) -> str:
    """Send an HL7 file via MLLP and return the raw ACK response."""
    msg = Path(hl7_path).read_bytes().replace(b"\n", b"\r")
    frame = VT + msg + FS + CR
    with socket.create_connection((MLLP_HOST, MLLP_PORT), timeout=30) as s:
        s.sendall(frame)
        buf = b""
        while not buf.endswith(FS + CR):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    return buf.strip(VT + FS + CR).decode("latin-1")


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return REPO_ROOT / "samples"


@pytest.fixture(scope="session")
def deadletter_dir() -> Path:
    return REPO_ROOT / "deadletter"


@pytest.fixture(scope="module")
def hapi() -> httpx.Client:
    with httpx.Client(base_url=HAPI_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="module")
def fastapi_http() -> httpx.Client:
    with httpx.Client(base_url=FASTAPI_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="session")
def mllp():
    """Return a callable that sends an HL7 file via MLLP."""
    return _mllp_send
