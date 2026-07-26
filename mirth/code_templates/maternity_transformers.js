/*
 * Maternity HL7-to-FHIR Pipeline — Mirth Connect transformer logic
 * ================================================================
 *
 * SYNTHETIC DATA ONLY — Not for clinical use.
 *
 * This is the source-of-truth for the JavaScript that runs inside the
 * "FastAPI FHIR Transform" destination transformer of
 * `mirth/channels/Maternity_Inbound.xml`. The channel export embeds a copy of
 * this code; keep the two in sync.
 *
 * The functions parse an inbound HL7 v2.5 message (Mirth exposes it as the E4X
 * object `msg`) by CANONICAL HL7 field position and build the flat JSON payload
 * that the FastAPI service expects on:
 *
 *     ADT^A01  -> POST /fhir/Patient            (AdtPayload)
 *     ORM^O01  -> POST /fhir/Encounter          (OrmPayload)
 *     ORU^R01  -> POST /fhir/Observation/bundle (OruPayload)
 *
 * The exact field positions and output shape are locked by the executable
 * contract test `tests/unit/test_mirth_channel_contract.py`. If you change a
 * mapping here, update that test (and vice versa).
 */

/**
 * Safe text value for an E4X HL7 node — returns '' when absent/empty.
 *
 * Mirth parses every HL7 field into components, so a field node like PID-8 is
 * <PID.8><PID.8.1>F</PID.8.1></PID.8>. Calling toString() on that field returns
 * the XML MARKUP, not "F". This helper drills into the first child element until
 * it reaches the text leaf, so passing either a field (PID.8) or an explicit
 * component (PID.8.1) both yield the plain value.
 */
function mgText(node) {
    if (node === undefined || node === null || node.length() === 0) {
        return '';
    }
    var current = node;
    // Drill through element children (field -> component -> subcomponent) to the leaf.
    var kids = current.children();
    while (kids.length() > 0 && kids[0].nodeKind() === 'element') {
        current = kids[0];
        kids = current.children();
    }
    return current.toString();
}

/** Country normalisation: HL7 "AUS" -> ISO "AU"; empty passes through for FastAPI profile default. */
function mgCountry(code) {
    if (code === 'AUS') return 'AU';
    return code;
}

/** Pull MRN (identifier type MR) and national ID (NI/NH/PN/SS) from the repeating PID-3 field. */
function mgMrnAndIhi(pid) {
    var out = { mrn: '', ihi: '' };
    var nationalTypes = ['NI', 'NH', 'PN', 'SS'];
    for each (var rep in pid['PID.3']) {
        var idType = mgText(rep['PID.3.5']);
        var idVal = mgText(rep['PID.3.1']);
        if (idType === 'MR' && out.mrn === '') {
            out.mrn = idVal;
        } else if (nationalTypes.indexOf(idType) !== -1 && out.ihi === '') {
            out.ihi = idVal;
        }
    }
    return out;
}

/** ADT^A01 -> AdtPayload (Patient + Condition[]). Uses PID (name/ids/address) and DG1 (diagnoses). */
function mgBuildPatient(msg, correlationId) {
    var pid = msg['PID'];
    var ids = mgMrnAndIhi(pid);

    var payload = {
        correlationId: correlationId,
        messageType: 'ADT^A01',
        mrn: ids.mrn,
        ihi: ids.ihi,
        name: {
            family: mgText(pid['PID.5']['PID.5.1']),
            given: mgText(pid['PID.5']['PID.5.2']),
            middle: mgText(pid['PID.5']['PID.5.3']),
            prefix: mgText(pid['PID.5']['PID.5.5'])
        },
        birthDate: mgText(pid['PID.7']),
        gender: mgText(pid['PID.8']),
        address: {
            line: mgText(pid['PID.11']['PID.11.1']),
            city: mgText(pid['PID.11']['PID.11.3']),
            state: mgText(pid['PID.11']['PID.11.4']),
            postalCode: mgText(pid['PID.11']['PID.11.5']),
            country: mgCountry(mgText(pid['PID.11']['PID.11.6']))
        },
        phone: '',
        diagnoses: []
    };

    // First PID-13 repetition, component 1 (phone number).
    for each (var ph in pid['PID.13']) {
        payload.phone = mgText(ph['PID.13.1']);
        break;
    }

    // One diagnosis per DG1 segment.
    for each (var dg1 in msg['DG1']) {
        payload.diagnoses.push({
            code: mgText(dg1['DG1.3']['DG1.3.1']),
            display: mgText(dg1['DG1.3']['DG1.3.2']),
            codeSystem: mgText(dg1['DG1.3']['DG1.3.3']),
            recordedDate: mgText(dg1['DG1.5'])
        });
    }

    return payload;
}

/** ORM^O01 -> OrmPayload (Encounter). Uses PV1 (visit/location/doctor), ORC-1, OBR-4. */
function mgBuildEncounter(msg, correlationId) {
    var pid = msg['PID'];
    var pv1 = msg['PV1'];
    var orc = msg['ORC'];
    var obr = msg['OBR'];
    var ids = mgMrnAndIhi(pid);

    var payload = {
        correlationId: correlationId,
        messageType: 'ORM^O01',
        mrn: ids.mrn,
        visitNumber: mgText(pv1['PV1.19']['PV1.19.1']),
        patientClass: mgText(pv1['PV1.2']),
        admitDatetime: mgText(pv1['PV1.44']),
        location: {
            ward: mgText(pv1['PV1.3']['PV1.3.1']),
            room: mgText(pv1['PV1.3']['PV1.3.2']),
            facility: mgText(pv1['PV1.3']['PV1.3.4'])
        },
        attendingDoctor: {
            id: mgText(pv1['PV1.7']['PV1.7.1']),
            familyName: mgText(pv1['PV1.7']['PV1.7.2']),
            givenName: mgText(pv1['PV1.7']['PV1.7.3'])
        },
        orderControl: mgText(orc['ORC.1']) || 'NW',
        serviceCode: mgText(obr['OBR.4']['OBR.4.1']),
        serviceDisplay: mgText(obr['OBR.4']['OBR.4.2'])
    };

    var discharge = mgText(pv1['PV1.45']);
    if (discharge !== '') {
        payload.dischargeDatetime = discharge;
    }

    return payload;
}

/** ORU^R01 -> OruPayload (Observation[]). One entry per OBX; FastAPI merges the BP pair. */
function mgBuildObservation(msg, correlationId) {
    var pid = msg['PID'];
    var pv1 = msg['PV1'];
    var obr = msg['OBR'];
    var ids = mgMrnAndIhi(pid);

    var payload = {
        correlationId: correlationId,
        messageType: 'ORU^R01',
        mrn: ids.mrn,
        visitNumber: mgText(pv1['PV1.19']['PV1.19.1']),
        orderCode: mgText(obr['OBR.4']['OBR.4.1']),
        orderDisplay: mgText(obr['OBR.4']['OBR.4.2']),
        observations: []
    };

    for each (var obx in msg['OBX']) {
        var raw = mgText(obx['OBX.5']);
        payload.observations.push({
            setId: parseInt(mgText(obx['OBX.1']), 10),
            valueType: mgText(obx['OBX.2']),
            code: mgText(obx['OBX.3']['OBX.3.1']),
            display: mgText(obx['OBX.3']['OBX.3.2']),
            codeSystem: mgText(obx['OBX.3']['OBX.3.3']),
            value: raw === '' ? '' : parseFloat(raw),
            unitCode: mgText(obx['OBX.6']['OBX.6.1']),
            unitDisplay: mgText(obx['OBX.6']['OBX.6.2']),
            referenceRange: mgText(obx['OBX.7']),
            abnormalFlag: mgText(obx['OBX.8']),
            status: mgText(obx['OBX.11']),
            observationDatetime: mgText(obx['OBX.14'])
        });
    }

    return payload;
}

/*
 * Destination transformer entry point
 * -----------------------------------
 * Routes by MSH-9.1 and stashes the request (URL + body) in the channelMap for
 * the HTTP Sender to send. The correlation ID is generated once in the channel
 * preprocessor and reused here (and set as the X-Correlation-ID header).
 */
function mgRoute(msg, channelMap) {
    var correlationId = channelMap.get('correlationId');
    if (correlationId === null || correlationId === '' || correlationId === undefined) {
        correlationId = UUIDGenerator.getUUID();
        channelMap.put('correlationId', correlationId);
    }

    var messageType = mgText(msg['MSH']['MSH.9']['MSH.9.1']);
    var payload;
    var path;

    if (messageType === 'ADT') {
        payload = mgBuildPatient(msg, correlationId);
        path = '/fhir/Patient';
    } else if (messageType === 'ORM') {
        payload = mgBuildEncounter(msg, correlationId);
        path = '/fhir/Encounter';
    } else if (messageType === 'ORU') {
        payload = mgBuildObservation(msg, correlationId);
        path = '/fhir/Observation/bundle';
    } else {
        throw 'Unsupported HL7 message type: ' + messageType;
    }

    channelMap.put('httpBody', JSON.stringify(payload));
    channelMap.put('httpUrl', 'http://fastapi:8000' + path);
}

// Invoked by the channel's destination transformer step:
mgRoute(msg, channelMap);
