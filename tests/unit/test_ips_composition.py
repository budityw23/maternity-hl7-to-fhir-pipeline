from app.transformers.ips_composition import (
    _is_pregnancy_condition,
    _is_vital_sign,
    build_ips_bundle,
)


def _sample_patient():
    return {
        "resourceType": "Patient",
        "id": "pat-1",
        "name": [{"family": "SMITH", "given": ["EMMA"]}],
    }


def _sample_condition(code="O80", system="http://hl7.org/fhir/sid/icd-10"):
    return {
        "resourceType": "Condition",
        "id": f"cond-{code}",
        "code": {"coding": [{"system": system, "code": code, "display": f"Condition {code}"}]},
    }


def _sample_observation(code="29463-7", is_vital=True):
    categories = []
    if is_vital:
        categories = [{"coding": [{"code": "vital-signs"}]}]
    return {
        "resourceType": "Observation",
        "id": f"obs-{code}",
        "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
        "category": categories,
    }


def _sample_encounter():
    return {
        "resourceType": "Encounter",
        "id": "enc-1",
        "status": "finished",
    }


class TestIsPregnancyCondition:
    def test_icd10_o_prefix(self):
        assert _is_pregnancy_condition(_sample_condition("O80")) is True

    def test_icd10_non_pregnancy(self):
        assert _is_pregnancy_condition(_sample_condition("J06.9")) is False

    def test_snomed_pregnancy(self):
        cond = _sample_condition("77386006", "http://snomed.info/sct")
        assert _is_pregnancy_condition(cond) is True

    def test_empty_coding(self):
        assert _is_pregnancy_condition({"code": {"coding": []}}) is False


class TestIsVitalSign:
    def test_vital_sign_category(self):
        assert _is_vital_sign(_sample_observation("8480-6", is_vital=True)) is True

    def test_non_vital_sign(self):
        assert _is_vital_sign(_sample_observation("29463-7", is_vital=False)) is False


class TestBuildIpsBundle:
    def test_bundle_type_document(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        assert bundle["type"] == "document"

    def test_bundle_profile(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        assert "http://hl7.org/fhir/uv/ips/StructureDefinition/Bundle-uv-ips" in bundle["meta"]["profile"]

    def test_composition_is_first_entry(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        first_entry = bundle["entry"][0]["resource"]
        assert first_entry["resourceType"] == "Composition"

    def test_composition_profile(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        composition = bundle["entry"][0]["resource"]
        assert "http://hl7.org/fhir/uv/ips/StructureDefinition/Composition-uv-ips" in composition["meta"]["profile"]

    def test_composition_type_loinc(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        composition = bundle["entry"][0]["resource"]
        assert composition["type"]["coding"][0]["code"] == "60591-5"

    def test_composition_has_required_sections(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        composition = bundle["entry"][0]["resource"]
        section_titles = [s["title"] for s in composition["section"]]
        assert "Allergies and Intolerances" in section_titles
        assert "Medications" in section_titles
        assert "Problems" in section_titles
        assert "Results" in section_titles
        assert "Vital Signs" in section_titles
        assert "Pregnancy History" in section_titles

    def test_empty_sections_have_reason(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        composition = bundle["entry"][0]["resource"]
        allergies_section = composition["section"][0]
        assert "emptyReason" in allergies_section

    def test_conditions_in_problems_section(self):
        conditions = [_sample_condition("O80"), _sample_condition("O48")]
        bundle = build_ips_bundle(_sample_patient(), conditions, [], [])
        composition = bundle["entry"][0]["resource"]
        problems = next(s for s in composition["section"] if s["title"] == "Problems")
        assert len(problems["entry"]) == 2

    def test_vital_signs_separated(self):
        observations = [
            _sample_observation("8480-6", is_vital=True),
            _sample_observation("1234-5", is_vital=False),
        ]
        bundle = build_ips_bundle(_sample_patient(), [], observations, [])
        composition = bundle["entry"][0]["resource"]
        vitals = next(s for s in composition["section"] if s["title"] == "Vital Signs")
        results = next(s for s in composition["section"] if s["title"] == "Results")
        assert len(vitals["entry"]) == 1
        assert len(results["entry"]) == 1

    def test_pregnancy_conditions_in_pregnancy_section(self):
        conditions = [_sample_condition("O80"), _sample_condition("J06.9")]
        bundle = build_ips_bundle(_sample_patient(), conditions, [], [])
        composition = bundle["entry"][0]["resource"]
        pregnancy = next(s for s in composition["section"] if s["title"] == "Pregnancy History")
        assert len(pregnancy["entry"]) == 1

    def test_patient_in_bundle_entries(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
        assert "Patient" in resource_types

    def test_all_resources_in_bundle(self):
        conditions = [_sample_condition("O80")]
        observations = [_sample_observation("8480-6")]
        encounters = [_sample_encounter()]
        bundle = build_ips_bundle(_sample_patient(), conditions, observations, encounters)
        assert len(bundle["entry"]) == 5

    def test_composition_subject_reference(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        composition = bundle["entry"][0]["resource"]
        assert composition["subject"]["reference"] == "Patient/pat-1"

    def test_bundle_has_timestamp(self):
        bundle = build_ips_bundle(_sample_patient(), [], [], [])
        assert "timestamp" in bundle
