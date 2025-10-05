from lxml import etree

import parsers.patient as patient
import parsers.vitals as vitals
import parsers.immunizations as immunizations


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


def test_parse_immunizations_basic():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <component>
        <structuredBody>
          <component>
            <section>
              <code code="11369-6" />
              <entry>
                <substanceAdministration classCode="SBADM" moodCode="EVN">
                  <statusCode code="completed" />
                  <effectiveTime value="20240315" />
                  <code code="IMM123" displayName="Influenza vaccine" />
                  <consumable>
                    <manufacturedProduct>
                      <manufacturedMaterial>
                        <code code="140" codeSystem="2.16.840.1.113883.12.292" displayName="Influenza, seasonal" />
                        <name>Influenza Quadrivalent</name>
                        <lotNumberText>LOT-ABC</lotNumberText>
                      </manufacturedMaterial>
                    </manufacturedProduct>
                  </consumable>
                </substanceAdministration>
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

    result = immunizations.parse_immunizations(tree, ns)

    assert len(result) == 1
    record = result[0]
    assert record["vaccine_name"] == "Influenza vaccine"
    assert record["date"] == "20240315"
    assert record["status"] == "completed"
    assert record["cvx_codes"] == ["140"]
    assert record["product_name"] == "Influenza Quadrivalent"
    assert record["lot_number"] == "LOT-ABC"
