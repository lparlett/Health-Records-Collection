import unittest

from lxml import etree  # nosec B410

from health_records_collection.parsers import (
    allergies,
    encounters,
    immunizations,
    insurance,
    patient,
    vitals,
)
from health_records_collection.tests import helpers


class TestParsers(unittest.TestCase):
    """Test suite for CCD parser functions."""

    def test_parse_patient_minimal(self):
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = patient.parse_patient(tree, ns)

        self.assertEqual(result.get("given"), "Jane")
        self.assertEqual(result.get("family"), "Doe")
        self.assertIsNone(result.get("dob"))
        self.assertIsNone(result.get("gender"))

    def test_parse_vitals_basic(self):
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        vitals_result = vitals.parse_vitals(tree, ns)

        self.assertEqual(len(vitals_result), 2)

        first = vitals_result[0]
        self.assertEqual(first["code"], "8302-2")
        self.assertEqual(first["vital_type"], "Body height")
        self.assertEqual(first["value"], "170")
        self.assertEqual(first["unit"], "cm")
        self.assertEqual(first["date"], "20240101120000")
        self.assertEqual(first["encounter_source_id"], "ORG-1")
        self.assertEqual(first["provider"], "Example Clinic")

        second = vitals_result[1]
        self.assertEqual(second["vital_type"], "Body weight")
        # Falls back to the organizer effective time when the observation lacks one.
        self.assertEqual(second["date"], "20240101120000")
        self.assertEqual(second["unit"], "kg")

    def test_parse_immunizations_basic(self):
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = immunizations.parse_immunizations(tree, ns)

        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertEqual(record["vaccine_name"], "Influenza vaccine")
        self.assertEqual(record["date"], "20240315")
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["cvx_codes"], ["140"])
        self.assertEqual(record["product_name"], "Influenza Quadrivalent")
        self.assertEqual(record["lot_number"], "LOT-ABC")

    def test_parse_encounters_reason_for_visit(self):
        sample_xml = """
        <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <componentOf>
            <encompassingEncounter>
              <encounterParticipant typeCode="ATND">
                <assignedEntity>
                  <assignedPerson>
                    <name>Dr. Test Provider</name>
                  </assignedPerson>
                </assignedEntity>
              </encounterParticipant>
            </encompassingEncounter>
          </componentOf>
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = encounters.parse_encounters(tree, ns)

        self.assertEqual(len(result), 1)
        encounter = result[0]
        self.assertEqual(encounter["reason_for_visit"], "Headache; Nausea")
        self.assertEqual(encounter["provider"], "Dr. Test Provider")

    def test_parse_encounter_description_spacing(self):
        sample_xml = """
        <ClinicalDocument xmlns="urn:hl7-org:v3">
          <componentOf>
            <encompassingEncounter>
              <encounterParticipant typeCode="ATND">
                <assignedEntity>
                  <assignedPerson>
                    <name>Dr. Aberdeen Specialist</name>
                  </assignedPerson>
                </assignedEntity>
              </encounterParticipant>
            </encompassingEncounter>
          </componentOf>
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = encounters.parse_encounters(tree, ns)
        self.assertEqual(len(result), 1)
        notes = result[0]["notes"]
        self.assertIsNotNone(notes)
        if notes:
            self.assertTrue(
                notes.startswith("05/05/2024 8:45 AM EDT Office Visit Aberdeen")
            )
        self.assertEqual(result[0]["provider"], "Dr. Aberdeen Specialist")

    def test_parse_encounter_prefers_encompassing_provider(self):
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = encounters.parse_encounters(tree, ns)
        self.assertEqual(len(result), 1)
        encounter = result[0]
        self.assertEqual(encounter["provider"], "Preferred Provider")

    def test_parse_allergies_basic(self):
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
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = allergies.parse_allergies(tree, ns)
        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertEqual(record["substance_code"], "70618")
        self.assertEqual(record["substance"], "Penicillin V")
        self.assertEqual(record["reaction"], "Anaphylaxis")
        self.assertEqual(record["severity"], "Mild")
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["noted_date"], "20250302")
        self.assertIsNotNone(record["notes"])
        if record["notes"]:
            self.assertTrue(record["notes"].startswith("Patient experienced hives"))
        self.assertEqual(record["provider"], "Dr Allergy Tester")

    def test_parse_insurance_basic(self):
        sample_xml = helpers.SAMPLE_INSURANCE_XML
        root = etree.fromstring(sample_xml.encode("utf-8"))  # nosec B320
        tree = etree.ElementTree(root)
        ns = {"hl7": "urn:hl7-org:v3"}

        result = insurance.parse_insurance(tree, ns)
        self.assertEqual(len(result), 1)
        policy = result[0]
        self.assertEqual(policy["payer_name"], "BCBS PPO")
        self.assertEqual(policy["payer_identifier"], "758")
        self.assertEqual(policy["plan_name"], "Plan: BCBS PPO")
        self.assertEqual(policy["coverage_type"], "612")
        self.assertEqual(policy["member_id"], "WLU768M83547")
        self.assertEqual(policy["group_number"], "1871VH")
        self.assertEqual(policy["subscriber_id"], "WLU768M83547")
        self.assertEqual(policy["relationship"], "Self")
        self.assertEqual(policy["effective_date"], "20200101000000")
        self.assertIsNone(policy["expiration_date"])
        self.assertEqual(policy["status"], "completed")
        self.assertIsNotNone(policy["notes"])
        if policy["notes"]:
            self.assertTrue(policy["notes"].startswith("Plan: BCBS PPO"))
