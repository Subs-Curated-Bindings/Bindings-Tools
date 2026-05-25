"""
Merge approved HumanLabel values from _humanlabel-review.csv back into the
canonical sc_keybinds_reference.csv.

Rules:
  - If `Approved HumanLabel` is non-empty, use that.
  - Else if `Proposal` is non-empty, use that.
  - Else skip (no change).

For each row in the canonical CSV that matches an XMLActionName in the review:
  - Write the merged value into the HumanLabel column.
  - All other columns preserved.

After running, the canonical CSV at:
  E:/06. Dev Projects/Subs-Curated-Bindings/tools/_sc-keybinds-reference.csv
is updated in place. Sub then scp's it back to Monitarr:

  wsl -- scp /mnt/e/.../tools/_sc-keybinds-reference.csv monitarr:/home/subliminal/projects/subliminal-gg/lib/sc-actions/data/sc_keybinds_reference.csv
"""
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings")
REVIEW = REPO / "tools" / "_humanlabel-review.csv"
CSV_REF = REPO / "tools" / "_sc-keybinds-reference.csv"


def main(dry_run=False):
    # Load review labels
    labels = {}
    with open(REVIEW, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            xml_name = r["XMLActionName"]
            approved = (r.get("Approved HumanLabel") or "").strip()
            proposal = (r.get("Proposal") or "").strip()
            label = approved or proposal
            if label:
                labels[xml_name] = label
    print(f"Loaded {len(labels)} labels from review CSV")

    # Read + rewrite canonical CSV
    with open(CSV_REF, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        rows = list(reader)

    if "HumanLabel" not in cols:
        print(f"ERROR: HumanLabel column not in canonical CSV (cols: {cols})")
        return 1

    changed = 0
    for r in rows:
        new = labels.get(r["XMLActionName"])
        if new and new != (r.get("HumanLabel") or ""):
            r["HumanLabel"] = new
            changed += 1
    print(f"Would update {changed} of {len(rows)} rows")

    if dry_run:
        print("(dry-run; not writing)")
        return 0

    with open(CSV_REF, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {CSV_REF}")
    print()
    print("To push back to Monitarr:")
    print("  wsl -- bash -c 'cp \"/mnt/e/06. Dev Projects/Subs-Curated-Bindings/tools/_sc-keybinds-reference.csv\" /tmp/sc.csv && scp /tmp/sc.csv monitarr:/home/subliminal/projects/subliminal-gg/lib/sc-actions/data/sc_keybinds_reference.csv'")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(main(args.dry_run) or 0)
