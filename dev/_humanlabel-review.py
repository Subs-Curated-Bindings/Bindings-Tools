"""
Generate a review-friendly CSV from _humanlabel-proposals.json for Sub to edit.

Output columns:
  - XMLActionName
  - ActionMap
  - DisplayName (CIG-speak from CSV)
  - Proposal (matcher's best guess)
  - Confidence (high/medium/low)
  - Source (chart:STICK:CLUSTER | csv_displayname | xml_name_fallback)
  - Alt 1 / Alt 2 / Alt 3 (next-best chart phrases — quick-pick alternatives)
  - Approved HumanLabel (Sub fills in — blank means "use Proposal as-is")
  - Notes (Sub's notes — optional)

Sub workflow:
  1. Open in Excel / Sheets / wherever
  2. Scan high-confidence rows quickly; tweak as needed
  3. For low/medium rows, fill in "Approved HumanLabel" with the player-speak you want
  4. Save as CSV
  5. Run `_humanlabel-apply.py` to merge approved labels back into sc_keybinds_reference.csv

If "Approved HumanLabel" is blank for a row, the Proposal is used (so high-confidence
rows can be left untouched). If both are blank, the row is skipped.
"""
import csv
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings")
PROPOSALS = REPO / "tools" / "_humanlabel-proposals.json"
CSV_REF = REPO / "tools" / "_sc-keybinds-reference.csv"
OUT_CSV = REPO / "tools" / "_humanlabel-review.csv"


def main():
    with open(PROPOSALS, encoding="utf-8") as f:
        data = json.load(f)
    proposals = data["proposals"]

    # Index canonical CSV by XMLActionName for ActionMap lookup
    by_xml = {}
    with open(CSV_REF, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            by_xml[r["XMLActionName"]] = r

    # Sort: high first, then medium, then low; within each by ActionMap then XMLActionName
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    rows = []
    for xml_name, p in proposals.items():
        r = by_xml.get(xml_name, {})
        rows.append({
            "XMLActionName": xml_name,
            "ActionMap": r.get("ActionMap", ""),
            "DisplayName": p.get("display_name", ""),
            "Proposal": p["proposal"],
            "Confidence": p["confidence"],
            "Source": p["source"],
            "Alt 1": p["candidates"][1]["text"] if len(p.get("candidates", [])) > 1 else "",
            "Alt 2": p["candidates"][2]["text"] if len(p.get("candidates", [])) > 2 else "",
            "Alt 3": p["candidates"][3]["text"] if len(p.get("candidates", [])) > 3 else "",
            "Approved HumanLabel": "",
            "Notes": "",
        })
    rows.sort(key=lambda r: (conf_rank.get(r["Confidence"], 99), r["ActionMap"], r["XMLActionName"]))

    fieldnames = ["XMLActionName", "ActionMap", "DisplayName", "Proposal",
                  "Confidence", "Source", "Alt 1", "Alt 2", "Alt 3",
                  "Approved HumanLabel", "Notes"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    by_conf = Counter(r["Confidence"] for r in rows)
    by_src = Counter(
        ("chart" if r["Source"].startswith("chart") else
         "csv_displayname" if r["Source"] == "csv_displayname" else
         "xml_fallback")
        for r in rows
    )
    print(f"Wrote {OUT_CSV}")
    print(f"  {len(rows)} actions")
    print(f"  By confidence: {dict(by_conf)}")
    print(f"  By source: {dict(by_src)}")
    print()
    print("Workflow:")
    print("  1. Open _humanlabel-review.csv in Excel/Sheets")
    print("  2. Scan high-confidence rows (top of file) — tweak Proposal if needed")
    print("  3. For low/medium rows, fill in 'Approved HumanLabel'")
    print("  4. Save the CSV, then run tools/_humanlabel-apply.py to merge into the canonical CSV")


if __name__ == "__main__":
    main()
