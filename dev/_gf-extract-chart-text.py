"""
Dump full {etched -> chart text} from the Gunfighter SVG.
Used to author description bodies without truncation.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SVG = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds\Binding Charts\Binding Chart [ENH][GF][4.8.0][LIVE].svg")

tree = ET.parse(SVG)
root = tree.getroot()
serif_ns = "{http://www.serif.com/}id"

for elem in root.iter():
    eid = elem.attrib.get("id", "")
    serif_id = elem.attrib.get(serif_ns, "")
    canonical = serif_id or eid
    if not canonical.startswith("bind."):
        continue
    etched = canonical[len("bind."):]
    parts = []
    for t in elem.iter():
        tag = t.tag.split("}", 1)[-1]
        if tag in ("text", "tspan") and t.text:
            parts.append(t.text)
    text = " ".join(" ".join(parts).split())
    if text:
        print(f"{etched}\t{text}")
