/*
 * GenerateChannel — emits mirth/channels/Maternity_Inbound.xml from Mirth's own
 * model classes, so the connector/transformer/datatype XML is guaranteed to
 * match the exact serialization the running Mirth version expects.
 *
 * Why this exists: hand-authoring a Mirth 4.5 channel export is fragile — a
 * single wrong property class (e.g. MLLPModeProperties vs FrameModeProperties)
 * makes Mirth silently import the channel as "invalid" with its connectors
 * stripped. Building the object graph with the real classes and serializing via
 * ObjectXMLSerializer sidesteps all of that. The JavaScript transformer body is
 * read from mirth/code_templates/maternity_transformers.js (the source of truth).
 *
 * Usage (needs a running `mirth` container to source the jars from):
 *
 *   WORK=/tmp/mirthgen; mkdir -p $WORK/lib
 *   docker cp mirth:/opt/connect/server-lib/. $WORK/lib/
 *   docker cp mirth:/opt/connect/server-lib/donkey/. $WORK/lib/
 *   for e in tcp http mllpmode datatype-hl7v2 datatype-raw javascriptstep; do \
 *     docker cp mirth:/opt/connect/extensions/$e/. $WORK/lib/; done
 *   find $WORK/lib -maxdepth 1 -type f ! -name '*.jar' -delete
 *   CP=$(find $WORK/lib -name '*.jar' | tr '\n' ':')
 *   javac -proc:none --release 17 -cp "$CP" -d $WORK mirth/tools/GenerateChannel.java
 *   java -cp "$CP:$WORK" GenerateChannel mirth/code_templates/maternity_transformers.js \
 *     > mirth/channels/Maternity_Inbound.xml
 *
 * Then deploy with ./scripts/import_channels.sh.
 */
import com.mirth.connect.model.*;
import com.mirth.connect.model.converters.ObjectXMLSerializer;
import com.mirth.connect.connectors.tcp.TcpReceiverProperties;
import com.mirth.connect.connectors.http.HttpDispatcherProperties;
import com.mirth.connect.plugins.javascriptstep.JavaScriptStep;
import com.mirth.connect.plugins.datatypes.hl7v2.HL7v2DataTypeProperties;
import com.mirth.connect.plugins.datatypes.raw.RawDataTypeProperties;
import java.util.*;
import java.nio.file.*;

public class GenerateChannel {
    static final String CHANNEL_ID = "7f3a9c10-4d2b-4e6a-9b21-000000000001";
    static final String MIRTH_VERSION = "4.5.2";

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: GenerateChannel <path-to-transformer.js>");
            System.exit(2);
        }
        String js = new String(Files.readAllBytes(Paths.get(args[0])), "UTF-8");

        ObjectXMLSerializer s = ObjectXMLSerializer.getInstance();
        s.init(MIRTH_VERSION);
        s.processAnnotations(new Class[]{ Channel.class, Connector.class, Transformer.class, Filter.class,
            TcpReceiverProperties.class, HttpDispatcherProperties.class, JavaScriptStep.class,
            HL7v2DataTypeProperties.class, RawDataTypeProperties.class });

        Channel ch = new Channel();
        ch.setId(CHANNEL_ID);
        ch.setName("Maternity Inbound HL7");
        ch.setDescription("SYNTHETIC DATA ONLY - not for clinical use. Receives HL7 v2.5 over MLLP on port 6661, "
            + "routes by MSH-9.1 and POSTs the flat JSON contract to FastAPI "
            + "(ADT->/fhir/Patient, ORM->/fhir/Encounter, ORU->/fhir/Observation/bundle). "
            + "Transformer source-of-truth: mirth/code_templates/maternity_transformers.js");
        ch.setRevision(1);
        ch.setPreprocessingScript("// Generate one correlation ID per inbound message.\n"
            + "channelMap.put('correlationId', UUIDGenerator.getUUID());\nreturn message;");
        ch.setPostprocessingScript("return;");
        ch.setDeployScript("return;");
        ch.setUndeployScript("return;");

        // --- Source: MLLP TCP Listener on 6661, HL7 v2.x, auto ACK/NAK ---
        Connector src = new Connector("sourceConnector");
        src.setMetaDataId(0);
        src.setMode(Connector.Mode.SOURCE);
        src.setTransportName("TCP Listener");
        TcpReceiverProperties tcp = new TcpReceiverProperties();
        tcp.getListenerConnectorProperties().setHost("0.0.0.0");
        tcp.getListenerConnectorProperties().setPort("6661");
        src.setProperties(tcp);
        Transformer st = new Transformer();
        st.setInboundDataType("HL7V2");
        st.setOutboundDataType("HL7V2");
        st.setInboundProperties(new HL7v2DataTypeProperties());
        st.setOutboundProperties(new HL7v2DataTypeProperties());
        src.setTransformer(st);
        src.setFilter(new Filter());
        src.setEnabled(true);
        src.setWaitForPrevious(true);
        ch.setSourceConnector(src);

        // --- Destination: HTTP Sender -> FastAPI, JS transformer builds payload + route ---
        Connector dst = new Connector("FastAPI FHIR Transform");
        dst.setMetaDataId(1);
        dst.setMode(Connector.Mode.DESTINATION);
        dst.setTransportName("HTTP Sender");
        HttpDispatcherProperties http = new HttpDispatcherProperties();
        http.setHost("${httpUrl}");
        http.setMethod("post");
        http.setContent("${httpBody}");
        http.setContentType("application/json");
        http.setCharset("UTF-8");
        Map<String, List<String>> headers = new LinkedHashMap<>();
        headers.put("X-Correlation-ID", new ArrayList<>(Arrays.asList("${correlationId}")));
        http.setHeadersMap(headers);
        dst.setProperties(http);

        Transformer dt = new Transformer();
        dt.setInboundDataType("HL7V2");
        dt.setOutboundDataType("RAW");
        dt.setInboundProperties(new HL7v2DataTypeProperties());
        dt.setOutboundProperties(new RawDataTypeProperties());
        JavaScriptStep step = new JavaScriptStep();
        step.setName("Build FHIR payload and route");
        step.setScript(js);
        List<Step> els = new ArrayList<>();
        els.add(step);
        dt.setElements(els);
        dst.setTransformer(dt);

        Transformer rt = new Transformer();
        rt.setInboundDataType("RAW");
        rt.setOutboundDataType("RAW");
        rt.setInboundProperties(new RawDataTypeProperties());
        rt.setOutboundProperties(new RawDataTypeProperties());
        dst.setResponseTransformer(rt);

        dst.setFilter(new Filter());
        dst.setEnabled(true);
        dst.setWaitForPrevious(true);
        ch.addDestination(dst);

        System.out.println(s.serialize(ch));
    }
}
