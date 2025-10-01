from lxml import etree
import parsers.patient as patient

def test_parse_patient_minimal():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3">
      <recordTarget>
        <patientRole>
          <patient>
            <name>
              <given>Jane</given>
              <family>Doe</family>
            </name>
          </patient>
        </patientRole>
      </recordTarget>
    </ClinicalDocument>
    """
    root = etree.fromstring(sample_xml.encode("utf-8"))
    tree = etree.ElementTree(root)
    ns = {"hl7": "urn:hl7-org:v3"}

    result = patient.parse_patient(tree, ns)

    assert result.get("given") == "Jane"
    assert result.get("family") == "Doe"
    assert result.get("dob") is None
    assert result.get("gender") is None
