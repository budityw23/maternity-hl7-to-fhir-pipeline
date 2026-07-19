# Phase 0: Bootstrap

## Objective

Set up the project skeleton: git repo, directory structure, Docker Compose with all 3 services starting and healthy, FastAPI `/health` endpoint returning OK.

## Pre-conditions

- Docker and Docker Compose installed
- Python 3.11+ available
- Git available

## Tasks

Execute in order. Each task specifies exact files to create.

---

### Task 1: Initialize Git Repository

```bash
git init
```

---

### Task 2: Create `.gitignore`

**File**: `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.mypy_cache/
.ruff_cache/
.pytest_cache/

# Virtual environments
venv/
.venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Docker
*.log

# Runtime directories (kept with .gitkeep)
deadletter/*
!deadletter/.gitkeep
logs/*
!logs/.gitkeep

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local
```

---

### Task 3: Create Directory Structure

Create these directories with `.gitkeep` files where noted:

```bash
mkdir -p fastapi/app/models
mkdir -p fastapi/app/transformers
mkdir -p fastapi/app/clients
mkdir -p fastapi/app/valuesets
mkdir -p mirth/channels
mkdir -p mirth/code_templates
mkdir -p samples/invalid
mkdir -p scripts
mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p deadletter
mkdir -p logs
mkdir -p .github/workflows
```

Create `.gitkeep` in empty runtime dirs:

```bash
touch deadletter/.gitkeep
touch logs/.gitkeep
```

Create `__init__.py` files:

```bash
touch fastapi/app/__init__.py
touch fastapi/app/models/__init__.py
touch fastapi/app/transformers/__init__.py
touch fastapi/app/clients/__init__.py
touch fastapi/app/valuesets/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
```

---

### Task 4: Create `docker-compose.yml`

**File**: `docker-compose.yml`

```yaml
version: "3.9"

networks:
  maternity-net:
    driver: bridge

volumes:
  hapi-data:
  mirth-data:

services:
  mirth:
    image: nextgenhealthcare/connect:4.5
    container_name: mirth
    ports:
      - "6661:6661"
      - "8443:8443"
    environment:
      DATABASE: derby
      DATABASE_URL: jdbc:derby:/opt/connect/appdata/mirthdb;create=true
    volumes:
      - mirth-data:/opt/connect/appdata
      - ./mirth/channels:/opt/connect/channels:ro
      - ./deadletter:/opt/connect/deadletter
      - ./logs/mirth:/opt/connect/logs
    networks: [maternity-net]
    depends_on:
      fastapi:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fk", "https://localhost:8443/api/server/status"]
      interval: 30s
      retries: 5

  fastapi:
    build:
      context: ./fastapi
      dockerfile: Dockerfile
    container_name: fastapi
    ports:
      - "8000:8000"
    environment:
      HAPI_BASE_URL: http://hapi:8080/fhir
      LOG_LEVEL: INFO
      MRN_SYSTEM: http://hospital.local/mrn
      IHI_SYSTEM: http://ns.electronichealth.net.au/id/hi/ihi/1.0
    volumes:
      - ./logs/fastapi:/app/logs
      - ./deadletter:/app/deadletter
    networks: [maternity-net]
    depends_on:
      hapi:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      retries: 5

  hapi:
    image: hapiproject/hapi:v7.0.3
    container_name: hapi
    ports:
      - "8080:8080"
    environment:
      hapi.fhir.fhir_version: R4
      hapi.fhir.validation.requests_enabled: "true"
      hapi.fhir.validation.responses_enabled: "true"
      hapi.fhir.cors.allow_credentials: "true"
      hapi.fhir.cors.allowed_origin: "*"
    volumes:
      - hapi-data:/data/hapi
    networks: [maternity-net]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/fhir/metadata"]
      interval: 30s
      retries: 10
      start_period: 60s
```

---

### Task 5: Create FastAPI Dockerfile

**File**: `fastapi/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Task 6: Create `fastapi/pyproject.toml`

**File**: `fastapi/pyproject.toml`

```toml
[project]
name = "maternity-fhir-converter"
version = "0.1.0"
description = "HL7 v2 to FHIR R4 transformation service for Australian maternity care"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "fhir.resources>=7.1.0",
    "pydantic-settings>=2.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5.0",
    "mypy>=1.10",
]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM", "TCH"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

---

### Task 7: Create `fastapi/app/config.py`

**File**: `fastapi/app/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    hapi_base_url: str = "http://localhost:8080/fhir"
    log_level: str = "INFO"
    mrn_system: str = "http://hospital.local/mrn"
    ihi_system: str = "http://ns.electronichealth.net.au/id/hi/ihi/1.0"

    model_config = {"env_prefix": ""}


settings = Settings()
```

---

### Task 8: Create `fastapi/app/main.py`

**File**: `fastapi/app/main.py`

This is the Phase 0 scaffold — only `/health` endpoint. Future phases add transformation routes.

```python
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Maternity FHIR Converter",
    description="HL7 v2 to FHIR R4 transformation service for Australian maternity care",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    hapi_status = "unknown"
    try:
        client: httpx.AsyncClient = app.state.http_client
        response = await client.get(f"{settings.hapi_base_url}/metadata")
        hapi_status = "up" if response.status_code == 200 else "down"
    except httpx.HTTPError:
        hapi_status = "down"

    overall = "ok" if hapi_status == "up" else "degraded"

    return {
        "status": overall,
        "hapi": hapi_status,
        "version": "0.1.0",
    }
```

---

### Task 9: Create Sample HL7 Messages

**File**: `samples/adt_a01_normal_delivery.hl7`

```
MSH|^~\&|MAT_PAS|RPA_MATERNITY|MIRTH|INTEGRATION|20260527093000||ADT^A01^ADT_A01|MSG00001|P|2.5|||AL|NE|AUS
EVN|A01|20260527093000|||DR_JONES
PID|1||1234567^^^RPA^MR~8003608166690503^^^AUSHIC^NI||TEST^PATIENT^MARY^^MS||19920315|F|||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS||0412345678^PRN^CP~0298765432^PRN^PH|||M||||||||||||||
NK1|1|TEST^JOHN|SPO||0411111111
PV1|1|I|MAT_WARD^301^A^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS||||1|||DR_JONES^JAMES^B^^^DR|INP|VN00001|||||||||||||||||||||||||20260527093000
DG1|1|I10|O80^Encounter for full-term uncomplicated delivery^I10|Encounter for full-term uncomplicated delivery|20260527093000|A|
GT1|1||TEST^PATIENT^MARY||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS|0412345678|||||SELF
IN1|1|MEDICARE|MEDICARE|MEDICARE AUSTRALIA|||||||||||TEST^PATIENT^MARY|SELF|19920315|14 SAMPLE ST^^SYDNEY^NSW^2000^AUS
```

**File**: `samples/orm_o01_antenatal_28w.hl7`

```
MSH|^~\&|MAT_BOOKING|RPA_MATERNITY|MIRTH|INTEGRATION|20260420100000||ORM^O01^ORM_O01|MSG00002|P|2.5|||AL|NE|AUS
PID|1||1234567^^^RPA^MR||TEST^PATIENT^MARY^^MS||19920315|F|||14 SAMPLE ST^^SYDNEY^NSW^2000^AUS||0412345678^PRN^CP
PV1|1|O|MAT_CLINIC^OPD^^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS|||||||OUT|VN00012|||||||||||||||||||||||||20260420100000|20260420110000
ORC|NW|ORD0001^MAT_BOOKING|||SC||^^^20260420100000^^R||20260420100000|DR_SMITH^SARAH^A^^^DR|||||||||||||
OBR|1|ORD0001^MAT_BOOKING||ANC^Antenatal Checkup^L|||20260420100000|||||||||DR_SMITH^SARAH^A^^^DR
```

**File**: `samples/oru_r01_vitals.hl7`

```
MSH|^~\&|MAT_EMR|RPA_MATERNITY|MIRTH|INTEGRATION|20260420103000||ORU^R01^ORU_R01|MSG00003|P|2.5|||AL|NE|AUS
PID|1||1234567^^^RPA^MR||TEST^PATIENT^MARY^^MS||19920315|F
PV1|1|O|MAT_CLINIC^OPD^^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS|||||||OUT|VN00012
OBR|1|ORD0001^MAT_BOOKING||ANC^Antenatal Checkup^L|||20260420103000|||||||||DR_SMITH^SARAH^A^^^DR|||||||F
OBX|1|NM|8480-6^Systolic blood pressure^LN||118|mm[Hg]^millimeters of mercury^UCUM|90-140|N|||F|||20260420103000
OBX|2|NM|8462-4^Diastolic blood pressure^LN||76|mm[Hg]^millimeters of mercury^UCUM|60-90|N|||F|||20260420103000
OBX|3|NM|29463-7^Body weight^LN||68.5|kg^kilogram^UCUM|||N|||F|||20260420103000
OBX|4|NM|55283-6^Fetal heart rate^LN||145|/min^per minute^UCUM|110-160|N|||F|||20260420103000
```

**File**: `samples/invalid/adt_missing_mrn.hl7`

```
MSH|^~\&|MAT_PAS|RPA_MATERNITY|MIRTH|INTEGRATION|20260527093000||ADT^A01^ADT_A01|MSG00004|P|2.5|||AL|NE|AUS
EVN|A01|20260527093000|||DR_JONES
PID|1||||TEST^PATIENT^JANE^^MS||19880722|F|||10 OTHER ST^^MELBOURNE^VIC^3000^AUS||0400000000^PRN^CP
PV1|1|I|MAT_WARD^302^B^RPA||||DR_SMITH^SARAH^A^^^DR|||OBS||||1|||DR_JONES^JAMES^B^^^DR|INP|VN00002|||||||||||||||||||||||||20260527093000
DG1|1|I10|O80^Encounter for full-term uncomplicated delivery^I10|Encounter for full-term uncomplicated delivery|20260527093000|A|
```

---

### Task 10: Create `scripts/mllp_send.py`

**File**: `scripts/mllp_send.py`

```python
"""Minimal MLLP client for testing HL7 message delivery."""

import socket
import sys
from pathlib import Path

VT = b"\x0b"
FS = b"\x1c"
CR = b"\x0d"


def send(host: str, port: int, hl7_path: str) -> str:
    msg = Path(hl7_path).read_bytes().replace(b"\n", b"\r")
    frame = VT + msg + FS + CR
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(frame)
        buf = b""
        while not buf.endswith(FS + CR):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    return buf.strip(VT + FS + CR).decode("latin-1")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <hl7_file> [host] [port]")
        sys.exit(1)

    hl7_file = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 6661

    print(f"Sending {hl7_file} to {host}:{port}...")
    response = send(host, port, hl7_file)
    print(f"Response:\n{response}")
```

---

### Task 11: Create `scripts/reset.sh`

**File**: `scripts/reset.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Stopping and removing all containers and volumes..."
docker compose down -v

echo "Cleaning deadletter and logs..."
find deadletter -type f ! -name '.gitkeep' -delete 2>/dev/null || true
find logs -type f ! -name '.gitkeep' -delete 2>/dev/null || true

echo "Reset complete."
```

Make executable:
```bash
chmod +x scripts/reset.sh
```

---

### Task 12: Create GitHub Actions CI Skeleton

**File**: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./fastapi

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install ".[dev]"

      - name: Lint with ruff
        run: ruff check app/ tests/

      - name: Type check with mypy
        run: mypy app/

      - name: Run unit tests
        run: pytest tests/unit/ -v
```

---

## Verification

After all tasks complete, run these commands to verify:

```bash
# 1. Build and start all services
docker compose up -d --build

# 2. Wait for services to be healthy (HAPI takes ~60s to start)
echo "Waiting for services..."
sleep 70

# 3. Check FastAPI health
curl -s http://localhost:8000/health
# Expected: {"status":"ok","hapi":"up","version":"0.1.0"}

# 4. Check HAPI FHIR metadata
curl -s http://localhost:8080/fhir/metadata | head -c 200
# Expected: JSON starting with {"resourceType":"CapabilityStatement",...}

# 5. Check Mirth is running
curl -sk https://localhost:8443/api/server/status
# Expected: some response (may require auth)

# 6. Check all containers are healthy
docker compose ps
# Expected: all 3 services show "healthy" or "running"
```

## Definition of Done

- [ ] Git repo initialized
- [ ] All directories created with proper structure
- [ ] `docker compose up -d --build` succeeds — all 3 containers start
- [ ] `curl localhost:8000/health` returns `{"status":"ok","hapi":"up","version":"0.1.0"}`
- [ ] `curl localhost:8080/fhir/metadata` returns CapabilityStatement
- [ ] Sample HL7 files exist in `samples/`
- [ ] `scripts/mllp_send.py` exists and is syntactically valid
- [ ] `.github/workflows/ci.yml` exists
- [ ] `.gitignore` covers Python, Docker, IDE, runtime dirs

## Notes for Next Phase

Phase 1 will add the Patient transformation: `POST /fhir/Patient` endpoint, `AdtPayload` model, `build_patient()` transformer, and `hapi_client.py` for conditional create. The `/health` endpoint and Docker setup from Phase 0 will be the foundation.
