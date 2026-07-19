# Phase 5: Blood Pressure Panel Merging (ORU^R01)

## Objective

Modify the Observation transformer to detect consecutive OBX segments with LOINC codes `8480-6` (systolic) and `8462-4` (diastolic), and merge them into a single FHIR Observation with code `85354-9` (Blood pressure panel) and two `component[]` entries. Non-BP observations remain unchanged.

**No endpoint changes.** Only `observation.py` and tests are modified.

## Pre-conditions

- Phase 4 complete — `POST /fhir/Observation/bundle` works with individual observations
- BP constants already defined in `hl7_to_fhir_observation.py` (BP_CODES, BP_PANEL_CODE, BP_PANEL_DISPLAY)

## FHIR Structure — Target BP Observation

```json
{
  "resourceType": "Observation",
  "meta": { "profile": ["http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"] },
  "status": "final",
  "category": [{ "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs" }] }],
  "code": { "coding": [{ "system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel" }] },
  "subject": { "reference": "Patient/2" },
  "encounter": { "reference": "Encounter/4" },
  "effectiveDateTime": "2026-04-20T10:30:00+10:00",
  "component": [
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure" }] },
      "valueQuantity": { "value": 118, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]" },
      "interpretation": [{ "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "N", "display": "Normal" }] }]
    },
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure" }] },
      "valueQuantity": { "value": 76, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]" },
      "interpretation": [{ "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "N", "display": "Normal" }] }]
    }
  ]
}
```

**Key differences from simple Observation:**
- No top-level `valueQuantity` — values live inside `component[]`
- Code is `85354-9` (panel), not individual systolic/diastolic
- Each component has its own `code`, `valueQuantity`, and optionally `interpretation`
- AU Base BP profile in `meta.profile`

## Tasks

Execute in order.

---

### Task 1: Update `fastapi/app/valuesets/hl7_to_fhir_observation.py`

Add AU BP profile constant. Existing constants stay unchanged.

Add at the end of the file:

```python
AU_BP_PROFILE = "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"
```

---

### Task 2: Update `fastapi/app/transformers/observation.py`

Replace `build_observations()` with BP-aware version. Keep `_build_single_observation()` and `_hl7_datetime_to_iso()` unchanged.

Add new import at top (add to existing import block from `hl7_to_fhir_observation`):

```python
from app.valuesets.hl7_to_fhir_observation import (
    AU_BP_PROFILE,
    BP_CODES,
    BP_DIASTOLIC_CODE,
    BP_PANEL_CODE,
    BP_PANEL_DISPLAY,
    BP_SYSTOLIC_CODE,
    LOINC_SYSTEM,
    UCUM_SYSTEM,
    VITAL_SIGNS_CATEGORY_SYSTEM,
    map_abnormal_flag,
    map_observation_status,
)
```

Add new imports for FHIR types needed by BP panel (add to existing R4B import block):

```python
from fhir.resources.R4B.meta import Meta
from fhir.resources.R4B.observation import ObservationComponent
```

Add new function `_build_bp_panel_observation()` after `_build_single_observation()`:

```python
def _build_bp_panel_observation(
    systolic: ObservationPayload,
    diastolic: ObservationPayload,
    patient_reference: str,
    encounter_reference: str | None,
) -> Observation:
    """Build a BP panel Observation from paired systolic + diastolic OBX segments."""
    category = [
        CodeableConcept(
            coding=[Coding(system=VITAL_SIGNS_CATEGORY_SYSTEM, code="vital-signs")]
        )
    ]

    code = CodeableConcept(
        coding=[Coding(system=LOINC_SYSTEM, code=BP_PANEL_CODE, display=BP_PANEL_DISPLAY)]
    )

    def _make_component(obs: ObservationPayload) -> ObservationComponent:
        comp_code = CodeableConcept(
            coding=[Coding(system=LOINC_SYSTEM, code=obs.code, display=obs.display)]
        )
        numeric_value = float(obs.value) if isinstance(obs.value, str) else obs.value
        comp_value = Quantity(
            value=numeric_value,
            unit=obs.unitDisplay or obs.unitCode,
            system=UCUM_SYSTEM,
            code=obs.unitCode,
        )
        comp_interpretation = None
        if obs.abnormalFlag:
            flag_coding = map_abnormal_flag(obs.abnormalFlag)
            if flag_coding:
                comp_interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]

        return ObservationComponent(
            code=comp_code,
            valueQuantity=comp_value,
            interpretation=comp_interpretation,
        )

    components = [_make_component(systolic), _make_component(diastolic)]

    # Use systolic datetime; fall back to diastolic if systolic empty
    effective_src = systolic.observationDatetime or diastolic.observationDatetime
    effective_dt = _hl7_datetime_to_iso(effective_src) if effective_src else None

    # Use systolic status; if either is preliminary, use preliminary
    status_priority = {"preliminary": 0, "registered": 1, "final": 2, "corrected": 3}
    sys_status = map_observation_status(systolic.status)
    dia_status = map_observation_status(diastolic.status)
    panel_status = sys_status if status_priority.get(sys_status, 99) <= status_priority.get(dia_status, 99) else dia_status

    # Panel-level interpretation from systolic abnormal flag (if both normal → normal)
    panel_interpretation = None
    for obs_item in [systolic, diastolic]:
        if obs_item.abnormalFlag and obs_item.abnormalFlag.upper() not in ("N", ""):
            flag_coding = map_abnormal_flag(obs_item.abnormalFlag)
            if flag_coding:
                panel_interpretation = [CodeableConcept(coding=[Coding(**flag_coding)])]
                break

    encounter_ref = None
    if encounter_reference:
        encounter_ref = Reference(reference=encounter_reference)

    observation = Observation(
        meta=Meta(profile=[AU_BP_PROFILE]),
        text=Narrative(
            status="generated",
            div='<div xmlns="http://www.w3.org/1999/xhtml">Blood pressure panel</div>',
        ),
        status=panel_status,
        category=category,
        code=code,
        subject=Reference(reference=patient_reference),
        encounter=encounter_ref,
        effectiveDateTime=effective_dt,
        interpretation=panel_interpretation,
        component=components,
    )

    return observation
```

Replace `build_observations()` with this version:

```python
def build_observations(
    payload: OruPayload,
    patient_reference: str,
    encounter_reference: str | None = None,
) -> list[Observation]:
    """Build Observation resources from ORU payload.

    Detects paired systolic (8480-6) + diastolic (8462-4) OBX segments
    and merges them into a single BP panel Observation (85354-9).
    All other OBX segments are built as individual Observations.
    """
    observations: list[Observation] = []
    bp_systolic: ObservationPayload | None = None
    bp_diastolic: ObservationPayload | None = None

    for obs in payload.observations:
        if obs.code == BP_SYSTOLIC_CODE:
            bp_systolic = obs
        elif obs.code == BP_DIASTOLIC_CODE:
            bp_diastolic = obs
        else:
            observations.append(
                _build_single_observation(obs, patient_reference, encounter_reference)
            )

    if bp_systolic and bp_diastolic:
        observations.insert(
            0,
            _build_bp_panel_observation(
                bp_systolic, bp_diastolic, patient_reference, encounter_reference
            ),
        )
    else:
        # Orphaned BP component — build individually
        if bp_systolic:
            observations.append(
                _build_single_observation(bp_systolic, patient_reference, encounter_reference)
            )
        if bp_diastolic:
            observations.append(
                _build_single_observation(bp_diastolic, patient_reference, encounter_reference)
            )

    return observations
```

---

### Task 3: Update `tests/unit/test_observation_transformer.py`

Keep all existing test classes. Add new import and new test classes. Update one existing test.

Add to imports:

```python
from app.transformers.observation import _build_bp_panel_observation
```

**Modify** `TestBuildObservations::test_bp_codes_still_built_individually` — rename and update to test merging:

```python
def test_bp_codes_merged_into_panel(self):
    """Phase 5: BP OBX segments are merged into a single panel observation."""
    payload = _sample_payload([
        _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
        _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
    ])
    results = build_observations(payload, "Patient/2", None)
    assert len(results) == 1
    assert results[0].code.coding[0].code == "85354-9"
```

Add new test class `TestBuildBpPanelObservation`:

```python
class TestBuildBpPanelObservation:
    def _sys(self, **overrides):
        return _sample_obs(code="8480-6", display="Systolic blood pressure",
                           value=118, unitCode="mm[Hg]", unitDisplay="mmHg", **overrides)

    def _dia(self, **overrides):
        return _sample_obs(code="8462-4", display="Diastolic blood pressure",
                           value=76, unitCode="mm[Hg]", unitDisplay="mmHg", **overrides)

    def test_resource_type(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert _resource_type(obs) == "Observation"

    def test_panel_code(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.code.coding[0].code == "85354-9"
        assert obs.code.coding[0].display == "Blood pressure panel"
        assert obs.code.coding[0].system == "http://loinc.org"

    def test_no_top_level_value_quantity(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.valueQuantity is None

    def test_two_components(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert len(obs.component) == 2

    def test_systolic_component(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        sys_comp = obs.component[0]
        assert sys_comp.code.coding[0].code == "8480-6"
        assert sys_comp.valueQuantity.value == 118
        assert sys_comp.valueQuantity.code == "mm[Hg]"

    def test_diastolic_component(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        dia_comp = obs.component[1]
        assert dia_comp.code.coding[0].code == "8462-4"
        assert dia_comp.valueQuantity.value == 76
        assert dia_comp.valueQuantity.code == "mm[Hg]"

    def test_component_interpretation(self):
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="H"), self._dia(abnormalFlag="N"), "Patient/2", None
        )
        assert obs.component[0].interpretation[0].coding[0].code == "H"
        assert obs.component[1].interpretation[0].coding[0].code == "N"

    def test_au_bp_profile(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        obs_dict = _resource_json(obs)
        assert "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure" in obs_dict["meta"]["profile"]

    def test_status_both_final(self):
        obs = _build_bp_panel_observation(self._sys(status="F"), self._dia(status="F"), "Patient/2", None)
        assert obs.status == "final"

    def test_status_one_preliminary(self):
        obs = _build_bp_panel_observation(self._sys(status="P"), self._dia(status="F"), "Patient/2", None)
        assert obs.status == "preliminary"

    def test_effective_datetime(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.effectiveDateTime.isoformat() == "2026-04-20T10:30:00+10:00"

    def test_subject_reference(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.subject.reference == "Patient/2"

    def test_encounter_reference(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", "Encounter/4")
        assert obs.encounter.reference == "Encounter/4"

    def test_no_encounter(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.encounter is None

    def test_category_vital_signs(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None)
        assert obs.category[0].coding[0].code == "vital-signs"

    def test_panel_interpretation_abnormal(self):
        """Panel-level interpretation picks up non-normal flag from either component."""
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="N"), self._dia(abnormalFlag="H"), "Patient/2", None
        )
        assert obs.interpretation[0].coding[0].code == "H"

    def test_panel_interpretation_both_normal(self):
        """No panel-level interpretation when both components are normal."""
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="N"), self._dia(abnormalFlag="N"), "Patient/2", None
        )
        assert obs.interpretation is None
```

Add new test class `TestBpMergingInBuildObservations`:

```python
class TestBpMergingInBuildObservations:
    def test_mixed_bp_and_simple(self):
        """BP pair merges; non-BP observations remain individual."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
            _sample_obs(code="29463-7", display="Body weight", value=68.5, unitCode="kg"),
            _sample_obs(code="55283-6", display="Fetal heart rate", value=145, unitCode="/min"),
        ])
        results = build_observations(payload, "Patient/2", "Encounter/4")
        assert len(results) == 3  # 1 BP panel + 2 simple
        codes = [r.code.coding[0].code for r in results]
        assert "85354-9" in codes
        assert "29463-7" in codes
        assert "55283-6" in codes

    def test_bp_panel_first_in_results(self):
        """BP panel is inserted at position 0."""
        payload = _sample_payload([
            _sample_obs(code="29463-7", display="Body weight"),
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None)
        assert results[0].code.coding[0].code == "85354-9"

    def test_orphan_systolic_built_individually(self):
        """Systolic without diastolic → individual observation."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None)
        assert len(results) == 1
        assert results[0].code.coding[0].code == "8480-6"

    def test_orphan_diastolic_built_individually(self):
        """Diastolic without systolic → individual observation."""
        payload = _sample_payload([
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None)
        assert len(results) == 1
        assert results[0].code.coding[0].code == "8462-4"
```

---

## Verification

```bash
# 1. Run all unit tests
venv/bin/python -m pytest tests/unit/ -v

# Expected: Phase 1 (19) + Phase 2 (15) + Phase 3 (24) + Phase 4 (29, one test replaced) + Phase 5 (~21) ≈ 108+ tests

# 2. Rebuild FastAPI
docker compose up -d --build fastapi
sleep 10

# 3. Ensure Patient and Encounter exist (idempotent from prior phases)
curl -s -X POST http://localhost:8000/fhir/Patient \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/adt_a01_payload.json

curl -s -X POST http://localhost:8000/fhir/Encounter \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/orm_o01_payload.json

# 4. Send full ORU payload (has systolic, diastolic, weight, fetal HR)
curl -s -X POST http://localhost:8000/fhir/Observation/bundle \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/oru_r01_payload.json

# Expected: {"observationIds": ["<id1>","<id2>","<id3>"], "correlationId": "..."}
# 3 observations now (not 4): 1 BP panel + weight + fetal HR

# 5. Verify BP panel in HAPI
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?code=85354-9" | python3 -c "
import sys, json
b = json.load(sys.stdin)
if b.get('entry'):
    o = b['entry'][0]['resource']
    print('code:', o['code']['coding'][0]['code'], o['code']['coding'][0]['display'])
    print('components:', len(o.get('component', [])))
    for c in o.get('component', []):
        print(f'  {c[\"code\"][\"coding\"][0][\"code\"]}: {c[\"valueQuantity\"][\"value\"]} {c[\"valueQuantity\"][\"code\"]}')
    print('profile:', o.get('meta', {}).get('profile', []))
    print('status:', o['status'])
    print('valueQuantity:', o.get('valueQuantity', 'absent'))
"

# Expected:
# code: 85354-9 Blood pressure panel
# components: 2
#   8480-6: 118 mm[Hg]
#   8462-4: 76 mm[Hg]
# profile: ['http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure']
# status: final
# valueQuantity: absent

# 6. Verify simple observations still correct
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?code=29463-7" | python3 -c "
import sys, json
b = json.load(sys.stdin)
if b.get('entry'):
    o = b['entry'][0]['resource']
    print('code:', o['code']['coding'][0]['code'])
    print('value:', o['valueQuantity']['value'], o['valueQuantity']['code'])
"

# Expected: code: 29463-7, value: 68.5 kg

# 7. Verify no individual systolic/diastolic observations were created
docker exec fastapi curl -s "http://hapi:8080/fhir/Observation?code=8480-6" | python3 -c "
import sys, json
b = json.load(sys.stdin)
print('systolic individuals:', b.get('total', 0))
"

# Expected: 0 (merged into panel)
```

## Definition of Done

- [ ] BP pair (8480-6 + 8462-4) merged into single Observation with code 85354-9
- [ ] Panel has `component[0]` = systolic with valueQuantity 118 mm[Hg]
- [ ] Panel has `component[1]` = diastolic with valueQuantity 76 mm[Hg]
- [ ] No top-level `valueQuantity` on panel Observation
- [ ] `meta.profile` includes AU BP profile URL
- [ ] Component-level interpretation preserved (N, H, L per component)
- [ ] Panel-level interpretation reflects worst-case from components
- [ ] Panel status = most conservative of systolic/diastolic status
- [ ] effectiveDateTime from systolic (fallback to diastolic)
- [ ] Orphan systolic or diastolic (without pair) built as individual Observation
- [ ] Mixed payload (BP pair + weight + fetal HR) → 3 Observations (1 panel + 2 simple)
- [ ] Non-BP observations unchanged from Phase 4
- [ ] All prior phase tests still pass
- [ ] Endpoint response now returns 3 observationIds (not 4) for the standard fixture

## Notes

- This completes the core HL7→FHIR transformation pipeline (Phases 1-5)
- Phases 6-10 focus on cross-cutting concerns: validation, error handling, logging, testing, polish
