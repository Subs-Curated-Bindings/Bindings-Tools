"""
Build HumanLabel proposals for joystick-bound SC actions by mining chart
text against XMLActionName / DisplayName fragments.

Strategy:
  1. Find all joystick-bound XMLActionNames (union of <rebind> entries
     across every stick folder's layout XML).
  2. Parse every chart SVG, extracting per-cluster text bodies and breaking
     each body into "candidate phrases" (one per text frame, trimmed).
  3. For each action, score candidate phrases by token overlap with the
     action's XMLActionName tokens + DisplayName tokens. The best phrase
     becomes the proposal.
  4. Write a JSON of proposals for review before merging into CSV.

Input:
  - tools/_sc-keybinds-reference.csv  (canonical, pulled from Monitarr)
  - all stick folders under repo root

Output:
  - tools/_humanlabel-proposals.json   (action -> proposal + confidence + sources)

Heuristics tuned for the chart vocabulary: [M]/[H]/[DT] prefixes are
stripped from candidates so they don't influence matching, but kept in
the proposal text when present so the player can see modifier annotations.
"""
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings")
CSV_IN = REPO / "tools" / "_sc-keybinds-reference.csv"
PROPOSALS_OUT = REPO / "tools" / "_humanlabel-proposals.json"

STOP = {
    "a","an","the","and","or","to","of","on","in","by","with","for",
    "is","are","v","press","hold","mode","modes","set","unbound",
}


TOKEN_NORM = {
    "backward": "back", "backwards": "back",
    "forward": "fwd", "forwards": "fwd",
    "previous": "prev", "prv": "prev",
    "increase": "inc", "incr": "inc",
    "decrease": "dec", "decr": "dec",
    "subtarget": "sub",  # collapse to common stem
}


def tokenize(text):
    if not text: return []
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    parts = re.split(r"[^a-zA-Z0-9]+", text.lower())
    out = []
    for p in parts:
        if not p or len(p) <= 1 or p in STOP: continue
        out.append(TOKEN_NORM.get(p, p))
    return out


def strip_mod_tags(text):
    return re.sub(r"\[(M|H|DT)\]", "", text).strip()


def load_csv():
    rows = []
    with open(CSV_IN, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        for row in reader:
            rows.append(row)
    return cols, rows


def collect_joystick_actions():
    """Return dict[xml_action_name] = list of stick names binding it."""
    out = defaultdict(set)
    for stick in REPO.iterdir():
        if not (stick.is_dir() and stick.name.startswith("[Enhanced]")): continue
        for layout in stick.glob("layout_*_exported.xml"):
            if "Clear_Bindings" in layout.name: continue
            root = ET.parse(layout).getroot()
            for am in root.findall("./actionmap"):
                for act in am.findall("action"):
                    aname = act.attrib.get("name", "")
                    if not aname or not act.findall("rebind"): continue
                    out[aname].add(stick.name)
    return out


def extract_chart_phrases():
    """Return list of (stick, cluster_etched, phrase_text, phrase_tokens) tuples.
    Each chart text frame becomes one candidate phrase. The phrase is the raw
    text; tokens are normalized for matching."""
    serif_ns = "{http://www.serif.com/}id"
    out = []
    for stick in REPO.iterdir():
        if not (stick.is_dir() and stick.name.startswith("[Enhanced]")): continue
        svgs = list((stick / "Binding Charts").glob("*.svg")) if (stick / "Binding Charts").exists() else []
        for svg in svgs:
            try:
                tree = ET.parse(svg)
            except Exception as e:
                print(f"WARN parse {svg}: {e}")
                continue
            root = tree.getroot()
            # Find every <g> with id="bind.X" or serif:id="bind.X"
            for g in root.iter():
                eid = g.attrib.get("id", "")
                sid = g.attrib.get(serif_ns, "")
                canonical = sid or eid
                if not canonical.startswith("bind."): continue
                etched = canonical[5:]
                # Each text descendant becomes one candidate phrase
                for t in g.iter():
                    tag = t.tag.split("}", 1)[-1]
                    if tag != "text": continue
                    # Concatenate tspan text children
                    parts = []
                    if t.text: parts.append(t.text)
                    for sub in t.iter():
                        sub_tag = sub.tag.split("}", 1)[-1]
                        if sub_tag == "tspan" and sub.text:
                            parts.append(sub.text)
                    raw = " ".join(parts)
                    # The chart's text frames often contain multiple bind
                    # alternates separated by linebreaks (or operator-mode `/`
                    # alternates). Split into individual candidate phrases so a
                    # 4-direction hat frame doesn't collapse into one mega-phrase.
                    # The actual text concatenation drops newlines, so we use
                    # the raw text parts (line-by-line) as separators.
                    for part in re.split(r"\n+", raw):
                        # Each part may still contain `/`-separated operator-mode
                        # alternates; but those typically refer to the same physical
                        # bind in different modes, so keep them together.
                        # Strip leading [M]/[H]/[DT] tags but remember them.
                        s = strip_mod_tags(part)
                        s = re.sub(r"\s+", " ", s).strip()
                        if not s or len(s) < 3: continue
                        tokens = tokenize(s)
                        if tokens:
                            out.append({
                                "stick": stick.name,
                                "cluster": etched,
                                "raw": part,
                                "clean": s,
                                "tokens": tokens,
                            })
    return out


def make_label_from_xml_action(xml_name):
    """Fallback: build a human-readable label from the XMLActionName itself.
    e.g. v_view_freelook_mode -> View Freelook Mode"""
    name = xml_name
    for prefix in ("v_", "ui_", "vehicle_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in ("_long", "_short", "_hold", "_press"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    parts = name.replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts)


def display_name_is_clean(disp):
    """A DisplayName is usable as-is if it's not a UI-key remnant or empty."""
    if not disp: return False
    d = disp.strip()
    if not d: return False
    if d.startswith("ui_") or d.startswith("@"): return False
    if "_" in d and not d.replace("_", " ").replace(".", "").isascii(): return False
    return True


def clean_chart_phrase(raw):
    """Trim chart-text artifacts: stripped-tspan duplicate first letters,
    weird leading/trailing chars, normalize whitespace."""
    s = re.sub(r"\s+", " ", raw).strip()
    # Common artifact: doubled first letter from broken tspan concat ("SSpace", "FFire")
    s = re.sub(r"^([A-Z])\1([a-z])", r"\1\2", s)
    return s


def main():
    print("Loading CSV ...")
    cols, rows = load_csv()
    by_xml = {r["XMLActionName"]: r for r in rows}
    print(f"  {len(rows)} rows, columns: {cols}")

    print("Collecting joystick-bound actions ...")
    js_actions = collect_joystick_actions()
    print(f"  {len(js_actions)} distinct joystick-bound XMLActionNames")

    # Filter CSV down to joystick-relevant rows
    js_rows = {name: by_xml[name] for name in js_actions if name in by_xml}
    print(f"  {len(js_rows)} of those exist in CSV ({len(js_actions) - len(js_rows)} missing — possibly new actions not in CSV)")

    print("Extracting chart phrase corpus ...")
    phrases = extract_chart_phrases()
    print(f"  {len(phrases)} candidate phrases from all charts")

    # Token document frequency for IDF
    df = Counter()
    for p in phrases:
        for tk in set(p["tokens"]):
            df[tk] += 1
    total = len(phrases)
    import math
    idf = {tk: math.log(1 + total / max(1, n)) for tk, n in df.items()}

    print("Scoring proposals ...")
    proposals = {}
    for xml_name, row in js_rows.items():
        if (row.get("HumanLabel") or "").strip():
            continue  # already labeled

        disp = row.get("DisplayName", "")
        action_tokens_only = set(tokenize(xml_name))
        disp_tokens_only = set(tokenize(disp))
        action_tokens = action_tokens_only | disp_tokens_only
        if not action_tokens:
            continue

        # Score each chart phrase. Require at least 2 token overlap OR a very rare
        # (high-IDF) token to consider it a real match. Single common-token matches
        # produce false positives ("brake" matches anything braking-adjacent).
        scored = []
        for p in phrases:
            overlap = action_tokens & set(p["tokens"])
            if not overlap: continue
            n_overlap = len(overlap)
            score = sum(idf.get(tk, 0) for tk in overlap)
            # Penalize single-common-token matches (no distinctive overlap)
            max_idf = max((idf.get(tk, 0) for tk in overlap), default=0)
            if n_overlap == 1 and max_idf < 3.5:
                continue  # too weak; skip
            # Bonus when overlap is multi-token
            if n_overlap >= 2:
                score *= 1.5
            # Bonus for short, focused phrases
            phrase_len = len(p["clean"])
            if 8 <= phrase_len <= 50:
                score *= 1.2
            scored.append((score, n_overlap, p))
        scored.sort(key=lambda x: (-x[0], -x[1]))

        # Source priority:
        #   chart_high  = multi-token + clear gap (player-speak ready)
        #   chart_low   = chart match but weak; needs review
        #   displayname = chart doesn't match, but CSV DisplayName is usable
        #   xml_fallback = nothing usable, fall back to XML-name humanized
        chart_top = scored[0] if scored else None
        chart_gap = (chart_top[0] - scored[1][0]) if len(scored) > 1 else (chart_top[0] if chart_top else 0)

        if chart_top and chart_top[1] >= 2 and chart_top[0] > 4 and chart_gap > 1.0:
            confidence = "high"
            proposal = clean_chart_phrase(chart_top[2]["clean"])
            source = f"chart:{chart_top[2]['stick'][:25]}:{chart_top[2]['cluster']}"
        elif chart_top and chart_top[0] > 3:
            confidence = "medium"
            proposal = clean_chart_phrase(chart_top[2]["clean"])
            source = f"chart:{chart_top[2]['stick'][:25]}:{chart_top[2]['cluster']}"
        elif display_name_is_clean(disp):
            confidence = "medium"
            proposal = disp
            source = "csv_displayname"
        else:
            confidence = "low"
            proposal = make_label_from_xml_action(xml_name)
            source = "xml_name_fallback"

        proposals[xml_name] = {
            "proposal": proposal,
            "source": source,
            "confidence": confidence,
            "score": round(chart_top[0], 2) if chart_top else 0,
            "display_name": disp,
            "candidates": [
                {"text": clean_chart_phrase(p["clean"]), "score": round(s, 2),
                 "n_overlap": n, "cluster": f"{p['stick'][:25]}:{p['cluster']}"}
                for s, n, p in scored[:4]
            ],
        }

    # Uniqueness pass — chart phrases are limited supply. Without this, the
    # matcher cheerfully assigns "Cycle MFD Page Backward" to 9 different
    # XMLActionNames (gp_rotatepitch, gp_rotateyaw, ...) and downstream slot
    # matching fragments into ambiguous_exact piles. Greedy by score: strongest
    # proposal claims its top chart phrase first; collision losers walk down
    # their candidate list, then fall back to DisplayName, then XML-name.
    print("Uniqueness pass — resolving chart-phrase collisions ...")
    claimed = {}  # clean_text -> winner XMLActionName
    losers = []
    proposal_order = sorted(proposals.items(), key=lambda kv: -kv[1]["score"])
    for xml_name, p in proposal_order:
        if not p["source"].startswith("chart"):
            continue
        text = p["proposal"]
        if text not in claimed:
            claimed[text] = xml_name
            continue
        # Collision — try next-best chart candidate
        found = False
        for cand in p["candidates"][1:]:
            ct = cand["text"]
            if ct not in claimed:
                claimed[ct] = xml_name
                p["proposal"] = ct
                p["source"] = f"chart:{cand['cluster']}"
                p["score"] = cand["score"]
                p["confidence"] = "medium"  # downgrade — wasn't top pick
                found = True
                break
        if not found:
            losers.append(xml_name)

    fb_disp = 0
    fb_xml = 0
    for xml_name in losers:
        p = proposals[xml_name]
        disp = p.get("display_name", "")
        if display_name_is_clean(disp):
            p["proposal"] = disp
            p["source"] = "csv_displayname"
            p["confidence"] = "medium"
            fb_disp += 1
        else:
            p["proposal"] = make_label_from_xml_action(xml_name)
            p["source"] = "xml_name_fallback"
            p["confidence"] = "low"
            fb_xml += 1
    print(f"  {len(claimed)} unique chart-phrase assignments")
    print(f"  {len(losers)} losers re-routed ({fb_disp} → displayname, {fb_xml} → xml fallback)")

    # Stats
    conf_counts = Counter(p["confidence"] for p in proposals.values())
    src_counts = Counter(
        "chart" if p["source"].startswith("chart") else
        "csv_displayname" if p["source"] == "csv_displayname" else
        "xml_fallback"
        for p in proposals.values()
    )
    print()
    print(f"Proposals generated: {len(proposals)}")
    print(f"  By confidence: {dict(conf_counts)}")
    print(f"  By source: {dict(src_counts)}")
    print(f"  Sources: chart={src_counts.get('chart',0)} csv_displayname={src_counts.get('csv_displayname',0)} xml_fallback={src_counts.get('xml_fallback',0)}")

    # Write proposals
    out = {
        "_meta": {
            "csv_total_rows": len(rows),
            "joystick_actions_total": len(js_actions),
            "joystick_actions_in_csv": len(js_rows),
            "proposals_generated": len(proposals),
            "by_confidence": dict(conf_counts),
            "by_source": dict(src_counts),
        },
        "proposals": dict(sorted(proposals.items())),
    }
    with open(PROPOSALS_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {PROPOSALS_OUT}")


if __name__ == "__main__":
    main()
