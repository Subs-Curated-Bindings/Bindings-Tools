"""
Extract per-cluster text bodies from the VMAX+AERO chart SVG.

Output: tools/_vmax-cluster-bodies.json keyed by cluster base name (e.g. T-B1,
T-H1, R-M1). For hat-style clusters (4-way hat, analog mini stick), aggregates
the 5 directional sub-clusters into a single body with format
  "up=... | right=... | down=... | left=... | press-in=..."

For singleton clusters (buttons, encoders, throttle, triggers, main trigger
stages), the body is the raw text content of that bind frame.

Reads from tools/_vmax-cluster-bodies.json's matching SVG path.
"""
import json
import re
import sys
from collections import defaultdict
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

SVG_PATH = (
    r"E:\06. Dev Projects\Subs-Curated-Bindings"
    r"\[Enhanced] Virpil VMAX Throttle + Aeromax-R"
    r"\Binding Charts\Binding Chart [ENH][VMAX+AERO][4.8.0][LIVE].svg"
)
OUT_PATH = r"E:\06. Dev Projects\Subs-Curated-Bindings\tools\_vmax-cluster-bodies.json"

NS = {"svg": "http://www.w3.org/2000/svg"}


def collect_text(el):
    """Recursively collect all visible text in this SVG element (preserve order)."""
    out = []
    for t in el.iter("{http://www.w3.org/2000/svg}text"):
        # join all tspan/text content with spaces, preserving multi-line
        parts = []
        for sub in t.iter():
            if sub.text:
                parts.append(sub.text)
        line = " ".join(p.strip() for p in parts if p and p.strip())
        if line:
            out.append(line)
    return out


def main():
    print(f"Reading {SVG_PATH}")
    tree = ET.parse(SVG_PATH)
    root = tree.getroot()

    # Find every <g> with id starting with "bind."
    bind_groups = {}
    for g in root.iter("{http://www.w3.org/2000/svg}g"):
        gid = g.attrib.get("id", "")
        if not gid.startswith("bind."):
            continue
        # serif:id preserves canonical (no auto-suffix). Prefer that if present.
        serif_id = g.attrib.get("{http://www.serif.com/}id", "")
        canonical = serif_id if serif_id else gid
        # canonical may have an Affinity numeric suffix (e.g. press-in1) on `id`;
        # serif:id is the un-suffixed form. Use that.
        # Also: if id ends with a digit and serif:id missing, treat as duplicate
        # and merge into the un-suffixed name.
        if not serif_id and re.search(r"\d+$", canonical) and re.sub(r"\d+$", "", canonical) in [g2.attrib.get("id", "") for g2 in root.iter("{http://www.w3.org/2000/svg}g")]:
            # Likely an auto-suffixed dup; strip trailing digit(s)
            canonical = re.sub(r"\d+$", "", canonical)
        # collect text
        texts = collect_text(g)
        body = " / ".join(texts).strip()
        if canonical in bind_groups:
            # merge — intentional duplicate (e.g. R-M1.press-in with modifier mode)
            bind_groups[canonical] = bind_groups[canonical] + " | " + body
        else:
            bind_groups[canonical] = body

    print(f"Found {len(bind_groups)} bind clusters in SVG")

    # Strip the "bind." prefix from keys
    raw = {k[len("bind."):]: v for k, v in bind_groups.items()}

    # Group by base name (strip .up/.down/.left/.right/.press-in suffix)
    by_base = defaultdict(dict)
    DIRECTIONS = ("up", "right", "down", "left", "press-in")
    for cid, body in raw.items():
        m = re.match(r"^(.+)\.(up|down|left|right|press-in)$", cid)
        if m:
            by_base[m.group(1)][m.group(2)] = body
        else:
            # singleton (button, encoder axis, throttle, trigger stage, etc.)
            by_base[cid][""] = body

    # Build final clusters map
    out = {}
    for base, parts in sorted(by_base.items()):
        if "" in parts and len(parts) == 1:
            # singleton
            out[base] = parts[""]
        else:
            # hat-style: aggregate directions in clockwise order
            pieces = []
            for d in DIRECTIONS:
                if d in parts:
                    pieces.append(f"{d}={parts[d]}")
            # if there's a non-directional part too (shouldn't happen for hats), append
            if "" in parts:
                pieces.append(parts[""])
            out[base] = " | ".join(pieces)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {OUT_PATH}")
    print(f"\nCluster summary ({len(out)} entries):")
    for base, body in sorted(out.items()):
        preview = body[:90] + "..." if len(body) > 90 else body
        print(f"  {base:24s} {preview}")


if __name__ == "__main__":
    main()
