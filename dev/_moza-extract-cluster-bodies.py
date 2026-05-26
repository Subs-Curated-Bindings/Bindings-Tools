"""
Extract per-cluster text bodies from the MOZA MTQ + MHG chart SVG.

Output: tools/_moza-cluster-bodies.json keyed by cluster base name (e.g. T-COM,
R-POV, R-BB-1, MAIN-TRIG). For hat-style clusters (4-way / 5-way hats), aggregates
the directional sub-clusters into a single body with format
  "up=... | right=... | down=... | left=... | press-in=..."

For singleton clusters (buttons, encoders, sliders, etc.), the body is the raw
text content of that bind frame.

Same logic as _vmax-extract-cluster-bodies.py; only the SVG_PATH differs.
"""
import json
import re
import sys
from collections import defaultdict
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

SVG_PATH = (
    r"E:\06. Dev Projects\Subs-Curated-Bindings"
    r"\[Enhanced] MOZA MTQ + MHG"
    r"\Binding Charts\Binding Chart [ENH][MTQ+MHG][4.8.0][LIVE].svg"
)
OUT_PATH = r"E:\06. Dev Projects\Subs-Curated-Bindings\tools\_moza-cluster-bodies.json"


def collect_text(el):
    out = []
    for t in el.iter("{http://www.w3.org/2000/svg}text"):
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

    bind_groups = {}
    all_gids = [g.attrib.get("id", "") for g in root.iter("{http://www.w3.org/2000/svg}g")]
    for g in root.iter("{http://www.w3.org/2000/svg}g"):
        gid = g.attrib.get("id", "")
        if not gid.startswith("bind."):
            continue
        serif_id = g.attrib.get("{http://www.serif.com/}id", "")
        canonical = serif_id if serif_id else gid
        if not serif_id and re.search(r"\d+$", canonical) and re.sub(r"\d+$", "", canonical) in all_gids:
            canonical = re.sub(r"\d+$", "", canonical)
        texts = collect_text(g)
        body = " / ".join(texts).strip()
        if canonical in bind_groups:
            bind_groups[canonical] = bind_groups[canonical] + " | " + body
        else:
            bind_groups[canonical] = body

    print(f"Found {len(bind_groups)} bind clusters in SVG")

    raw = {k[len("bind."):]: v for k, v in bind_groups.items()}

    by_base = defaultdict(dict)
    DIRECTIONS = ("up", "right", "down", "left", "press-in")
    for cid, body in raw.items():
        # handle .stage-N / .device / .game suffixes by keeping them as singletons
        m = re.match(r"^(.+)\.(up|down|left|right|press-in)$", cid)
        if m:
            by_base[m.group(1)][m.group(2)] = body
        else:
            by_base[cid][""] = body

    out = {}
    for base, parts in sorted(by_base.items()):
        if "" in parts and len(parts) == 1:
            out[base] = parts[""]
        else:
            pieces = []
            for d in DIRECTIONS:
                if d in parts:
                    pieces.append(f"{d}={parts[d]}")
            if "" in parts:
                pieces.append(parts[""])
            out[base] = " | ".join(pieces)
    # Also keep raw entries whose suffix is NOT a direction (.stage-1/.stage-2,
    # .nav/.scm/.mining etc.) so they're addressable individually. Direction
    # sub-clusters (.up/.down/.left/.right/.press-in) are aggregated into base
    # and intentionally not surfaced separately — the audit's AGG mechanism
    # covers them via the base name.
    DIR_SUFFIX_PAT = re.compile(r"\.(up|down|left|right|press-in)(\.|$)")
    for cid, body in raw.items():
        if cid not in out and not DIR_SUFFIX_PAT.search(cid):
            out[cid] = body

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {OUT_PATH}")
    print(f"\nCluster summary ({len(out)} entries):")
    for base, body in sorted(out.items()):
        preview = body[:90] + "..." if len(body) > 90 else body
        print(f"  {base:24s} {preview}")


if __name__ == "__main__":
    main()
