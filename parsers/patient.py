# Purpose: Extract patient-level demographics from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

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
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=187
- HL7 Version 3 Standard: Identifier Types
  https://www.hl7.org/implement/standards/product_brief.cfm?product_id=188
"""

from __future__ import annotations

from .common import safe_xpath_attr, safe_xpath_text
from .xml_types import ElementTreeType

PatientData = dict[str, str | None]


def parse_patient(tree: ElementTreeType, ns: dict[str, str]) -> PatientData:
    """Return core demographics for the patient described in a CCD.

    Args:
        tree: The XML tree of the CCD document.
        ns: Namespace dictionary for XML parsing.

    Returns:
        PatientData: A dictionary containing patient demographics.
    """
    root = tree.getroot()
    given = safe_xpath_text(root, ".//hl7:patient//hl7:given", ns)
    family = safe_xpath_text(root, ".//hl7:patient//hl7:family", ns)
    dob = safe_xpath_attr(root, ".//hl7:patient//hl7:birthTime", "value", ns)
    gender = safe_xpath_attr(
        root, ".//hl7:patient//hl7:administrativeGenderCode", "code", ns
    )

    return {
        "given": given,
        "family": family,
        "dob": dob,
        "gender": gender,
    }
