from app.profiles.au_profile import AU_PROFILE
from app.models.oru_payload import ObservationPayload, OruPayload
from app.transformers.observation import (
    _build_bp_panel_observation,
    _build_single_observation,
    _hl7_datetime_to_iso,
    build_observations,
)
from app.valuesets.hl7_to_fhir_observation import (
    map_abnormal_flag,
    map_observation_status,
)


def _resource_type(resource) -> str | None:
    return getattr(resource, "__resource_type__", getattr(resource, "resource_type", None))


def _resource_json(resource) -> dict:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(mode="json", exclude_none=True)
    return resource.dict(by_alias=True, exclude_none=True)


def _sample_obs(**overrides) -> ObservationPayload:
    defaults = {
        "setId": 1,
        "valueType": "NM",
        "code": "29463-7",
        "display": "Body weight",
        "codeSystem": "LN",
        "value": 68.5,
        "unitCode": "kg",
        "unitDisplay": "kilogram",
        "referenceRange": "",
        "abnormalFlag": "N",
        "status": "F",
        "observationDatetime": "20260420103000",
    }
    defaults.update(overrides)
    return ObservationPayload(**defaults)


def _sample_payload(observations: list[ObservationPayload] | None = None) -> OruPayload:
    return OruPayload(
        correlationId="test-uuid-004",
        mrn="1234567",
        visitNumber="VN00012",
        observations=observations if observations is not None else [_sample_obs()],
    )


class TestBuildSingleObservation:
    def test_resource_type(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", "Encounter/4", AU_PROFILE)
        assert _resource_type(obs) == "Observation"

    def test_status_final(self):
        obs = _build_single_observation(_sample_obs(status="F"), "Patient/2", None, AU_PROFILE)
        assert obs.status == "final"

    def test_status_preliminary(self):
        obs = _build_single_observation(_sample_obs(status="P"), "Patient/2", None, AU_PROFILE)
        assert obs.status == "preliminary"

    def test_category_vital_signs(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        assert obs.category[0].coding[0].code == "vital-signs"

    def test_code_loinc(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        coding = obs.code.coding[0]
        assert coding.system == "http://loinc.org"
        assert coding.code == "29463-7"
        assert coding.display == "Body weight"

    def test_value_quantity(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        vq = obs.valueQuantity
        assert vq.value == 68.5
        assert vq.code == "kg"
        assert vq.unit == "kilogram"
        assert vq.system == "http://unitsofmeasure.org"

    def test_subject_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        assert obs.subject.reference == "Patient/2"

    def test_encounter_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", "Encounter/4", AU_PROFILE)
        assert obs.encounter.reference == "Encounter/4"

    def test_no_encounter_reference(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        assert obs.encounter is None

    def test_effective_datetime(self):
        obs = _build_single_observation(_sample_obs(), "Patient/2", None, AU_PROFILE)
        assert obs.effectiveDateTime.isoformat() == "2026-04-20T10:30:00+10:00"

    def test_no_effective_datetime(self):
        obs = _build_single_observation(
            _sample_obs(observationDatetime=""), "Patient/2", None, AU_PROFILE
        )
        assert obs.effectiveDateTime is None

    def test_interpretation_normal(self):
        obs = _build_single_observation(_sample_obs(abnormalFlag="N"), "Patient/2", None, AU_PROFILE)
        assert obs.interpretation[0].coding[0].code == "N"
        assert obs.interpretation[0].coding[0].display == "Normal"

    def test_interpretation_high(self):
        obs = _build_single_observation(_sample_obs(abnormalFlag="H"), "Patient/2", None, AU_PROFILE)
        assert obs.interpretation[0].coding[0].code == "H"

    def test_no_interpretation(self):
        obs = _build_single_observation(
            _sample_obs(abnormalFlag=""), "Patient/2", None, AU_PROFILE
        )
        assert obs.interpretation is None

    def test_reference_range(self):
        obs = _build_single_observation(
            _sample_obs(referenceRange="50-100"), "Patient/2", None, AU_PROFILE
        )
        obs_dict = _resource_json(obs)
        assert obs_dict["referenceRange"][0]["text"] == "50-100"

    def test_no_reference_range(self):
        obs = _build_single_observation(
            _sample_obs(referenceRange=""), "Patient/2", None, AU_PROFILE
        )
        assert obs.referenceRange is None

    def test_fetal_heart_rate(self):
        obs = _build_single_observation(
            _sample_obs(code="55283-6", display="Fetal heart rate", value=145, unitCode="/min", unitDisplay="per minute"),
            "Patient/2",
            None,
            AU_PROFILE,
        )
        assert obs.code.coding[0].code == "55283-6"
        assert obs.valueQuantity.value == 145
        assert obs.valueQuantity.code == "/min"


class TestBuildObservations:
    def test_single_observation(self):
        payload = _sample_payload([_sample_obs()])
        results = build_observations(payload, "Patient/2", "Encounter/4", AU_PROFILE)
        assert len(results) == 1

    def test_multiple_observations(self):
        payload = _sample_payload([
            _sample_obs(code="29463-7", display="Body weight"),
            _sample_obs(code="55283-6", display="Fetal heart rate"),
        ])
        results = build_observations(payload, "Patient/2", "Encounter/4", AU_PROFILE)
        assert len(results) == 2
        assert results[0].code.coding[0].code == "29463-7"
        assert results[1].code.coding[0].code == "55283-6"

    def test_empty_observations(self):
        payload = _sample_payload([])
        results = build_observations(payload, "Patient/2", None, AU_PROFILE)
        assert len(results) == 0

    def test_bp_codes_merged_into_panel(self):
        """Phase 5: BP OBX segments are merged into a single panel observation."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None, AU_PROFILE)
        assert len(results) == 1
        assert results[0].code.coding[0].code == "85354-9"


class TestBuildBpPanelObservation:
    def _sys(self, **overrides):
        return _sample_obs(
            code="8480-6",
            display="Systolic blood pressure",
            value=118,
            unitCode="mm[Hg]",
            unitDisplay="mmHg",
            **overrides,
        )

    def _dia(self, **overrides):
        return _sample_obs(
            code="8462-4",
            display="Diastolic blood pressure",
            value=76,
            unitCode="mm[Hg]",
            unitDisplay="mmHg",
            **overrides,
        )

    def test_resource_type(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert _resource_type(obs) == "Observation"

    def test_panel_code(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.code.coding[0].code == "85354-9"
        assert obs.code.coding[0].display == "Blood pressure panel"
        assert obs.code.coding[0].system == "http://loinc.org"

    def test_no_top_level_value_quantity(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.valueQuantity is None

    def test_two_components(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert len(obs.component) == 2

    def test_systolic_component(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        sys_comp = obs.component[0]
        assert sys_comp.code.coding[0].code == "8480-6"
        assert sys_comp.valueQuantity.value == 118
        assert sys_comp.valueQuantity.code == "mm[Hg]"

    def test_diastolic_component(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        dia_comp = obs.component[1]
        assert dia_comp.code.coding[0].code == "8462-4"
        assert dia_comp.valueQuantity.value == 76
        assert dia_comp.valueQuantity.code == "mm[Hg]"

    def test_component_interpretation(self):
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="H"), self._dia(abnormalFlag="N"), "Patient/2", None, AU_PROFILE
        )
        assert obs.component[0].interpretation[0].coding[0].code == "H"
        assert obs.component[1].interpretation[0].coding[0].code == "N"

    def test_au_bp_profile(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        obs_dict = _resource_json(obs)
        assert (
            "http://hl7.org.au/fhir/StructureDefinition/au-vitalsigns-bloodpressure"
            in obs_dict["meta"]["profile"]
        )

    def test_status_both_final(self):
        obs = _build_bp_panel_observation(
            self._sys(status="F"), self._dia(status="F"), "Patient/2", None, AU_PROFILE
        )
        assert obs.status == "final"

    def test_status_one_preliminary(self):
        obs = _build_bp_panel_observation(
            self._sys(status="P"), self._dia(status="F"), "Patient/2", None, AU_PROFILE
        )
        assert obs.status == "preliminary"

    def test_effective_datetime(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.effectiveDateTime.isoformat() == "2026-04-20T10:30:00+10:00"

    def test_subject_reference(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.subject.reference == "Patient/2"

    def test_encounter_reference(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", "Encounter/4", AU_PROFILE)
        assert obs.encounter.reference == "Encounter/4"

    def test_no_encounter(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.encounter is None

    def test_category_vital_signs(self):
        obs = _build_bp_panel_observation(self._sys(), self._dia(), "Patient/2", None, AU_PROFILE)
        assert obs.category[0].coding[0].code == "vital-signs"

    def test_panel_interpretation_abnormal(self):
        """Panel-level interpretation picks up non-normal flag from either component."""
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="N"), self._dia(abnormalFlag="H"), "Patient/2", None, AU_PROFILE
        )
        assert obs.interpretation[0].coding[0].code == "H"

    def test_panel_interpretation_both_normal(self):
        """No panel-level interpretation when both components are normal."""
        obs = _build_bp_panel_observation(
            self._sys(abnormalFlag="N"), self._dia(abnormalFlag="N"), "Patient/2", None, AU_PROFILE
        )
        assert obs.interpretation is None


class TestBpMergingInBuildObservations:
    def test_mixed_bp_and_simple(self):
        """BP pair merges; non-BP observations remain individual."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
            _sample_obs(code="29463-7", display="Body weight", value=68.5, unitCode="kg"),
            _sample_obs(code="55283-6", display="Fetal heart rate", value=145, unitCode="/min"),
        ])
        results = build_observations(payload, "Patient/2", "Encounter/4", AU_PROFILE)
        assert len(results) == 3
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
        results = build_observations(payload, "Patient/2", None, AU_PROFILE)
        assert results[0].code.coding[0].code == "85354-9"

    def test_orphan_systolic_built_individually(self):
        """Systolic without diastolic -> individual observation."""
        payload = _sample_payload([
            _sample_obs(code="8480-6", display="Systolic BP", value=120, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None, AU_PROFILE)
        assert len(results) == 1
        assert results[0].code.coding[0].code == "8480-6"

    def test_orphan_diastolic_built_individually(self):
        """Diastolic without systolic -> individual observation."""
        payload = _sample_payload([
            _sample_obs(code="8462-4", display="Diastolic BP", value=80, unitCode="mm[Hg]"),
        ])
        results = build_observations(payload, "Patient/2", None, AU_PROFILE)
        assert len(results) == 1
        assert results[0].code.coding[0].code == "8462-4"


class TestMapObservationStatus:
    def test_final(self):
        assert map_observation_status("F") == "final"

    def test_preliminary(self):
        assert map_observation_status("P") == "preliminary"

    def test_corrected(self):
        assert map_observation_status("C") == "corrected"

    def test_unknown(self):
        assert map_observation_status("Z") == "unknown"


class TestMapAbnormalFlag:
    def test_normal(self):
        result = map_abnormal_flag("N")
        assert result["code"] == "N"

    def test_high(self):
        result = map_abnormal_flag("H")
        assert result["code"] == "H"

    def test_low(self):
        result = map_abnormal_flag("L")
        assert result["code"] == "L"

    def test_empty(self):
        result = map_abnormal_flag("")
        assert result is None

    def test_unknown_flag(self):
        result = map_abnormal_flag("Z")
        assert result is None


class TestHl7DatetimeToIso:
    def test_full_datetime(self):
        assert _hl7_datetime_to_iso("20260420103000", AU_PROFILE.timezone_offset) == "2026-04-20T10:30:00+10:00"

    def test_date_only(self):
        assert _hl7_datetime_to_iso("20260420", AU_PROFILE.timezone_offset) == "2026-04-20"

    def test_short_string(self):
        assert _hl7_datetime_to_iso("2026", AU_PROFILE.timezone_offset) == "2026"
