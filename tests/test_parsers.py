from lxml import etree

import parsers.allergies as allergies
import parsers.encounters as encounters
import parsers.immunizations as immunizations
import parsers.insurance as insurance
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


def test_parse_encounters_reason_for_visit():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <component>
        <structuredBody>
          <component>
            <section>
              <code code="29299-5" />
              <title>Reason for Visit</title>
              <text>
                <list>
                  <item>Headache</item>
                  <item>Nausea</item>
                </list>
              </text>
            </section>
          </component>
          <component>
            <section>
              <entry>
                <encounter classCode="ENC" moodCode="EVN">
                  <code code="AMB" displayName="Ambulatory" />
                  <effectiveTime value="20240101" />
                </encounter>
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

    result = encounters.parse_encounters(tree, ns)

    assert len(result) == 1
    encounter = result[0]
    assert encounter["reason_for_visit"] == "Headache; Nausea"


def test_parse_encounter_description_spacing():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3">
      <component>
        <structuredBody>
          <component>
            <section>
              <text>
                <paragraph ID="encounter4">
                  05/05/2024 8:45 AM EDT
                  <paragraph>Office Visit</paragraph>
                  <paragraph>Aberdeen</paragraph>
                  <paragraph>1800 N SANDHILLS BLVD</paragraph>
                </paragraph>
              </text>
              <entry>
                <encounter classCode="ENC" moodCode="EVN">
                  <text>
                    <reference value="#encounter4" />
                  </text>
                </encounter>
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

    result = encounters.parse_encounters(tree, ns)
    assert len(result) == 1
    notes = result[0]["notes"]
    assert notes.startswith("05/05/2024 8:45 AM EDT Office Visit Aberdeen")


def test_parse_encounter_prefers_encompassing_provider():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3">
      <componentOf>
        <encompassingEncounter>
          <encounterParticipant typeCode="ATND">
            <assignedEntity>
              <assignedPerson>
                <name>Preferred Provider</name>
              </assignedPerson>
            </assignedEntity>
          </encounterParticipant>
        </encompassingEncounter>
      </componentOf>
      <component>
        <structuredBody>
          <component>
            <section>
              <entry>
                <encounter classCode="ENC" moodCode="EVN">
                  <code code="AMB" displayName="Ambulatory" />
                  <effectiveTime value="20240101" />
                </encounter>
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

    result = encounters.parse_encounters(tree, ns)
    assert len(result) == 1
    encounter = result[0]
    assert encounter["provider"] == "Preferred Provider"


def test_parse_allergies_basic():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <component>
        <structuredBody>
          <component>
            <section>
              <code code="48765-2" />
              <text>
                <paragraph ID="note1">Patient experienced hives following penicillin.</paragraph>
              </text>
              <entry>
                <act classCode="ACT" moodCode="EVN">
                  <entryRelationship typeCode="SUBJ">
                    <observation classCode="OBS" moodCode="EVN">
                      <templateId root="2.16.840.1.113883.10.20.22.4.8"/>
                      <id root="urn:uuid:allergy-1"/>
                      <code code="ASSERTION"/>
                      <statusCode code="active"/>
                      <effectiveTime value="20250301"/>
                      <value xsi:type="CD" code="70618" codeSystem="2.16.840.1.113883.6.88" displayName="Penicillin"/>
                      <text>
                        <reference value="#note1"/>
                      </text>
                      <participant typeCode="CSM">
                        <participantRole>
                          <playingEntity>
                            <code code="70618" codeSystem="2.16.840.1.113883.6.88" displayName="Penicillin V"/>
                          </playingEntity>
                        </participantRole>
                      </participant>
                      <entryRelationship typeCode="SUBJ">
                        <observation classCode="OBS" moodCode="EVN">
                          <templateId root="2.16.840.1.113883.10.20.22.4.9"/>
                          <value xsi:type="CD" code="39579001" displayName="Anaphylaxis"/>
                        </observation>
                      </entryRelationship>
                      <entryRelationship typeCode="SUBJ">
                        <observation classCode="OBS" moodCode="EVN">
                          <code code="SEV" displayName="Severity"/>
                          <value xsi:type="CD" code="255604002" displayName="Mild"/>
                        </observation>
                      </entryRelationship>
                      <author>
                        <assignedAuthor>
                          <assignedPerson>
                            <name>Dr Allergy Tester</name>
                          </assignedPerson>
                        </assignedAuthor>
                        <time value="20250302"/>
                      </author>
                    </observation>
                  </entryRelationship>
                </act>
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

    result = allergies.parse_allergies(tree, ns)
    assert len(result) == 1
    record = result[0]
    assert record["substance_code"] == "70618"
    assert record["substance"] == "Penicillin V"
    assert record["reaction"] == "Anaphylaxis"
    assert record["severity"] == "Mild"
    assert record["status"] == "active"
    assert record["noted_date"] == "20250302"
    assert record["notes"].startswith("Patient experienced hives")
    assert record["provider"] == "Dr Allergy Tester"


def test_parse_insurance_basic():
    sample_xml = """
    <ClinicalDocument xmlns="urn:hl7-org:v3"
                      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                      xmlns:sdtc="urn:hl7-org:sdtc">
      <component>
        <structuredBody>
          <component>
            <section>
              <code code="48768-6" />
              <text>
                <list>
                  <item ID="coverage100">Plan: BCBS PPO</item>
                  <item ID="coverage100PlanName">BCBS PPO</item>
                  <item ID="coverage100relToSub">Self</item>
                </list>
              </text>
              <entry>
                <act classCode="ACT" moodCode="EVN">
                  <templateId root="2.16.840.1.113883.10.20.22.4.60"/>
                  <templateId root="2.16.840.1.113883.10.20.22.4.60" extension="2023-05-01"/>
                  <id root="1.2.840.114350.1.13.470.2.7.2.678671" extension="816442"/>
                  <code code="48768-6" codeSystem="2.16.840.1.113883.6.1" displayName="Payment sources"/>
                  <statusCode code="completed"/>
                  <effectiveTime value="20240303"/>
                  <entryRelationship typeCode="COMP">
                    <act classCode="ACT" moodCode="EVN">
                      <templateId root="2.16.840.1.113883.10.20.22.4.61"/>
                      <id root="1.2.840.114350.1.13.470.2.7.3.678671.210" extension="1871VH"/>
                      <code code="612" codeSystem="2.16.840.1.113883.3.221.5"/>
                      <text>
                        <reference value="#coverage100"/>
                      </text>
                      <statusCode code="completed"/>
                      <performer typeCode="PRF">
                        <assignedEntity>
                          <id root="2.16.840.1.113883.6.300" extension="758"/>
                          <representedOrganization>
                            <name>BCBS PPO</name>
                          </representedOrganization>
                        </assignedEntity>
                      </performer>
                      <participant typeCode="COV">
                        <participantRole>
                          <id extension="WLU768M83547"/>
                          <code codeSystem="2.16.840.1.113883.5.111">
                            <originalText>Self<reference value="#coverage100relToSub"/></originalText>
                          </code>
                          <time>
                            <low value="20200101000000"/>
                            <high nullFlavor="NA"/>
                          </time>
                          <playingEntity>
                            <name nullFlavor="NI"/>
                            <sdtc:birthTime nullFlavor="UNK"/>
                          </playingEntity>
                        </participantRole>
                      </participant>
                      <entryRelationship typeCode="REFR">
                        <act classCode="ACT" moodCode="DEF">
                          <text>
                            <reference value="#coverage100PlanName"/>
                          </text>
                        </act>
                      </entryRelationship>
                    </act>
                  </entryRelationship>
                </act>
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

    result = insurance.parse_insurance(tree, ns)
    assert len(result) == 1
    policy = result[0]
    assert policy["payer_name"] == "BCBS PPO"
    assert policy["payer_identifier"] == "758"
    assert policy["plan_name"] == "Plan: BCBS PPO"
    assert policy["coverage_type"] == "612"
    assert policy["member_id"] == "WLU768M83547"
    assert policy["group_number"] == "1871VH"
    assert policy["subscriber_id"] == "WLU768M83547"
    assert policy["relationship"] == "Self"
    assert policy["effective_date"] == "20200101000000"
    assert policy["expiration_date"] is None
    assert policy["status"] == "completed"
    assert policy["notes"].startswith("Plan: BCBS PPO")
