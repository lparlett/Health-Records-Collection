"""Shared helpers for service tests to avoid duplication."""

from __future__ import annotations

import hashlib
import sqlite3
import unittest
from pathlib import Path
from typing import Tuple

from health_records_collection.db.schema import ensure_schema

SCHEMA_FILE = Path(__file__).parent.parent / "schema.sql"
DEFAULT_INGESTED_AT = "2025-10-12T00:00:00Z"


def create_schema_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the project schema loaded."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    ensure_schema(conn)
    return conn


def seed_archive_and_data_source(
    conn: sqlite3.Connection,
    *,
    archive_name: str = "archive.zip",
    data_source_name: str = "test.xml",
    ingested_at: str = DEFAULT_INGESTED_AT,
    file_hash: str | None = None,
) -> Tuple[int, int]:
    """Insert an ingested_archive and data_source row for foreign-key fixtures."""
    archive_hash = hashlib.sha256(archive_name.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO ingested_archive (
            archive_name,
            archive_sha256,
            first_ingested_at,
            last_ingested_at,
            ingest_count
        ) VALUES (?, ?, ?, ?, 1)
        """,
        (archive_name, archive_hash, ingested_at, ingested_at),
    )
    archive_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO data_source (
            original_filename,
            file_sha256,
            ingested_at,
            source_archive_id
        ) VALUES (?, ?, ?, ?)
        """,
        (
            data_source_name,
            file_hash or hashlib.sha256(data_source_name.encode("utf-8")).hexdigest(),
            ingested_at,
            archive_id,
        ),
    )
    data_source_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    return archive_id, data_source_id


SAMPLE_INSURANCE_XML = """
<ClinicalDocument xmlns="urn:hl7-org:v3"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  xmlns:sdtc="urn:hl7-org:sdtc">
  <recordTarget>
    <patientRole>
      <patient>
        <name>
          <given>Alex</given>
          <family>Smith</family>
        </name>
      </patient>
    </patientRole>
  </recordTarget>
  <component>
    <structuredBody>
      <component>
        <section>
          <code code="48765-2"/>
          <text>
            <paragraph ID="allergyNote">Patient reported penicillin reaction.</paragraph>
          </text>
          <entry>
            <act classCode="ACT" moodCode="EVN">
              <entryRelationship typeCode="SUBJ">
                <observation classCode="OBS" moodCode="EVN">
                  <templateId root="2.16.840.1.113883.10.20.22.4.8"/>
                  <statusCode code="active"/>
                  <effectiveTime value="20250105"/>
                  <value xsi:type="CD" code="70618" codeSystem="2.16.840.1.113883.6.88" displayName="Penicillin"/>
                  <text>
                    <reference value="#allergyNote"/>
                  </text>
                  <entryRelationship typeCode="SUBJ">
                    <observation classCode="OBS" moodCode="EVN">
                      <templateId root="2.16.840.1.113883.10.20.22.4.9"/>
                      <value xsi:type="CD" code="39579001" displayName="Anaphylaxis"/>
                    </observation>
                  </entryRelationship>
                  <author>
                    <assignedAuthor>
                      <assignedPerson>
                        <name>Dr Allergy Tester</name>
                      </assignedPerson>
                    </assignedAuthor>
                  </author>
                </observation>
              </entryRelationship>
            </act>
          </entry>
        </section>
      </component>
      <component>
        <section>
          <code code="48768-6"/>
          <text>
            <list>
              <item ID="coverage100">Plan: BCBS PPO</item>
              <item ID="coverage100PlanName">BCBS PPO</item>
              <item ID="coverage100relToSub">Self</item>
            </list>
          </text>
          <entry>
            <act classCode="ACT" moodCode="EVN">
              <id root="2.16.840.1.113883.19.5" extension="12345"/>
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


class SchemaTestCase(unittest.TestCase):
    """Base test case that provisions a schema connection and data source."""

    schema_conn: sqlite3.Connection
    data_source_id: int

    def setUp(self) -> None:
        """Initialise reusable schema connection and data source."""
        self.schema_conn = create_schema_conn()
        _, self.data_source_id = seed_archive_and_data_source(self.schema_conn)

    def tearDown(self) -> None:
        """Close schema connection."""
        self.schema_conn.close()
