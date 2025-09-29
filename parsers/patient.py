"""Utilities for extracting patient demographics from CCD documents.

References
----------
- HL7 Continuity of Care Document (CCD) Standard
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=7
- HL7 CDA R2 Standard (Clinical Document Architecture)
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=7
- HL7 CDA R2 Implementation Guide: US Realm
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=280
- HL7 CDA R2 Implementation Guide: US Realm - Continuity of Care Document (CCD)
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=280
- HL7 Version 3 Standard: Data Types
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=185
- HL7 Version 3 Standard: Vocabulary Domains
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=186
- HL7 Version 3 Standard: Code Systems
  https://www.hl7.org/implement/standards/product_brief.cfm?product _id=187
- HL7 Version 3 Standard: Identifier Types
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=188
"""

from __future__ import annotations

from typing import Dict, Optional

from lxml import etree

PatientData = Dict[str, Optional[str]]


def parse_patient(tree: etree._ElementTree, ns: dict[str, str]) -> PatientData:
    """Return core demographics for the patient described in a CCD.

    Args:
        tree (etree._ElementTree): The XML tree of the CCD document.
        ns (dict[str, str]): The namespace dictionary for XML parsing.      
    Returns:
        PatientData: A dictionary containing patient demographics.  
    """
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