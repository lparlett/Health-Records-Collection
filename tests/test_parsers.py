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

    name = result.get("name")
    
    assert isinstance(name, str)
    assert "Jane" in name or "Doe" in name