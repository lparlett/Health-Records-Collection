from __future__ import annotations

from typing import Dict, Optional

from lxml import etree

PatientData = Dict[str, Optional[str]]


def parse_patient(tree: etree._ElementTree, ns: dict[str, str]) -> PatientData:
    given = tree.findtext(".//hl7:patient//hl7:given", namespaces=ns)
    family = tree.findtext(".//hl7:patient//hl7:family", namespaces=ns)
    dob = tree.findtext(".//hl7:patient//hl7:birthTime", namespaces=ns)
    gender = tree.findtext(".//hl7:patient//hl7:administrativeGenderCode", namespaces=ns)

    return {
        "given": given,
        "family": family,
        "dob": dob,
        "gender": gender,
    }