from lxml import etree

import parsers.patient as patient
import parsers.vitals as vitals


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


def test_parse_vitals_basic():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <component>
        <structuredBody>
          <component>
            <section>
              <code code="8716-3" />
              <entry>
                <organizer>
                  <id root="1.2.3" extension="ORG-1" />
                  <effectiveTime value="20240101120000" />
                  <author>
                    <assignedAuthor>
                      <representedOrganization>
                        <name>Example Clinic</name>
                      </representedOrganization>
                    </assignedAuthor>
                  </author>
                  <component>
                    <observation>
                      <code code="8302-2">
                        <originalText>Body height</originalText>
                      </code>
                      <statusCode code="completed" />
                      <effectiveTime value="20240101120000" />
                      <value xsi:type="PQ" value="170" unit="cm" />
                    </observation>
                  </component>
                  <component>
                    <observation>
                      <code code="29463-7" displayName="Body weight" />
                      <value xsi:type="PQ" value="65" unit="kg" />
                    </observation>
                  </component>
                </organizer>
              </entry>
            </section>
          </component>
        </structuredBody>
      </component>
    </ClinicalDocument>
    """
    root = etree.fromstring(sample_xml.encode("utf-8"))
    tree = etree.ElementTree(root)
    ns = {"hl7": "urn:hl7-org:v3"}

    vitals_result = vitals.parse_vitals(tree, ns)

    assert len(vitals_result) == 2

    first = vitals_result[0]
    assert first["code"] == "8302-2"
    assert first["vital_type"] == "Body height"
    assert first["value"] == "170"
    assert first["unit"] == "cm"
    assert first["date"] == "20240101120000"
    assert first["encounter_source_id"] == "ORG-1"
    assert first["provider"] == "Example Clinic"

    second = vitals_result[1]
    assert second["vital_type"] == "Body weight"
    # Falls back to the organizer effective time when the observation lacks one.
    assert second["date"] == "20240101120000"
    assert second["unit"] == "kg"
