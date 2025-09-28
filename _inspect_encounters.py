from pathlib import Path
from lxml import etree

path = Path("data/parsed/HealthSummary_Sep_27_2025/IHE_XDM/Lauren1/DOC0025.XML")
ns = {"hl7": "urn:hl7-org:v3"}
tree = etree.parse(str(path))
for idx, encounter in enumerate(tree.xpath(".//hl7:encounter", namespaces=ns), start=1):
    print(f"Encounter {idx}")
    print(etree.tostring(encounter, pretty_print=True, encoding=str))
    print("---")
