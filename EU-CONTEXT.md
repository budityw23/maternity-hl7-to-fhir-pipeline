# European Healthcare Standards Context

## 1. Regulatory Background

### European Health Data Space (EHDS)

The EHDS regulation (EU 2025/327) entered into force on 26 March 2025 and mandates FHIR-based interoperability across all 27 EU member states. Key milestones:

- **March 2025**: Regulation published in Official Journal
- **January 2026**: EHR system certification requirements
- **2027–2031**: Phased implementation of data access services

FHIR R4 is explicitly positioned as a central standard for cross-border health data exchange.

### GDPR and Health Data

The General Data Protection Regulation (EU 2016/679) classifies health data as a "special category" under Article 9. Processing requires explicit legal basis — typically Article 9(2)(h) for healthcare provision or Article 6(1)(a) for explicit consent.

This pipeline implements a lightweight GDPR Consent resource to demonstrate awareness of these requirements.

## 2. HL7 Europe Profiling Layer

HL7 Europe published its Base and Core FHIR Implementation Guides (STU 2.0) based on FHIR R4:

- **HL7 Europe Base Profiles** — loosely constrained baseline definitions
- **HL7 Europe Core Profiles** — essential constraints aligned with IPS
- **HL7 Europe Extensions** — common European extensions

Package: `hl7.fhir.eu.base#2.0.0`
Canonical URL: `http://hl7.eu/fhir/base`

### Layered Architecture

```text
HL7 EU Extensions
       |
HL7 EU Base Profiles (flexible foundation)
       |
HL7 EU Core Profiles (essential constraints)
       |
Scoped HL7 EU IGs (domain-specific)
       |
National IGs (country-specific)
```

This differs from Australia's flatter AU Base → AU Core approach.

## 3. Profile URLs Used in This Pipeline

| Resource | EU Profile URL | Notes |
|---|---|---|
| Patient | `http://hl7.eu/fhir/base/StructureDefinition/patient-eu` | EU Base Patient |
| Condition | `http://hl7.eu/fhir/base/StructureDefinition/condition-eu-core` | EU Core Condition |
| Encounter | `http://hl7.org/fhir/StructureDefinition/Encounter` | No EU-specific profile |
| Observation (BP) | `http://hl7.org/fhir/StructureDefinition/bp` | FHIR core BP profile |

## 4. National Identifier Systems

| Country | Identifier | FHIR System URI |
|---|---|---|
| UK | NHS Number | `https://fhir.nhs.uk/Id/nhs-number` |
| Netherlands | BSN | `http://fhir.nl/fhir/NamingSystem/bsn` |
| Germany | KVNR | `http://fhir.de/sid/gkv/kvid-10` |
| Ireland | PPS Number | `https://fhir.ie/sid/ppsn` |
| Generic EU | National ID | `http://hl7.eu/fhir/base/NamingSystem/national-id` |

## 5. Terminology Differences from AU

| Terminology | AU | EU |
|---|---|---|
| Diagnosis | ICD-10-AM (`http://hl7.org.au/fhir/CodeSystem/icd-10-am`) | ICD-10 WHO (`http://hl7.org/fhir/sid/icd-10`) |
| Clinical terms | SNOMED CT AU Edition | SNOMED CT International Edition |
| Observation codes | LOINC (same) | LOINC (same) |
| Units | UCUM (same) | UCUM (same) |

## 6. International Patient Summary (IPS)

The IPS (ISO 27269) is the cross-border health document standard that EHDS is built around.

- **Bundle profile**: `http://hl7.org/fhir/uv/ips/StructureDefinition/Bundle-uv-ips`
- **Composition profile**: `http://hl7.org/fhir/uv/ips/StructureDefinition/Composition-uv-ips`
- **Composition type**: LOINC `60591-5` (Patient summary Document)

Required sections: Allergies, Medications, Problems, Results, Vital Signs, Pregnancy History.

The IPS endpoint in this pipeline works in both AU and EU modes.

## 7. References

- [EHDS Regulation (EU 2025/327)](https://www.european-health-data-space.com/)
- [HL7 Europe Base/Core FHIR IG](https://hl7.eu/fhir/base)
- [HL7 Europe Extensions FHIR IG](https://hl7.eu/fhir/extensions)
- [International Patient Summary IG](https://hl7.org/fhir/uv/ips/)
- [GDPR Regulation](https://gdpr-info.eu/)
