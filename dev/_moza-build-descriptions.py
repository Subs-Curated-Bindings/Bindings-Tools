"""
Build JG-input -> chart-cluster mapping for the MOZA MTQ + MHG.

Strategy (mirrors VMAX matcher, plus a side filter):

  For each JG <input>:
    1. Follow root-action -> map-to-vjoy primitives (incl. nested in tempos/macros)
       to get the (vjoy-device, vjoy-input, vjoy-type) tuples this input emits.
    2. Look up each vjoy slot in the layout XML to find the SC XMLActionName
       it binds.
    3. Build a token bag from action names + DisplayName/HumanLabel (SC CSV).
    4. Score each chart cluster by TF-IDF token+bigram overlap.
    5. Filter to clusters on this physical device's chart side.
    6. Pick the best-scoring cluster (OK / WEAK / TIE / UNMATCHED).

Side filter (Moza):
  - Physical device 00ed3200 (vjoy 2) is the FLIGHT STICK (MHG) — pitch/yaw/roll
    live here. Maps to chart clusters with prefix `R-` and `MAIN-TRIG`.
  - Physical device b3167000 (vjoy 1) is the THROTTLE QUADRANT (MTQ). Maps to
    chart clusters with prefix `T-`.

After scoring, apply cross-mode coherence: per (device, itype, iid), prefer
the SCM-Mode cluster and inherit it to Nav/Modifier mode siblings.

Output: tools/_moza-cluster-assignment.json — one entry per JG input.
"""
import csv
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

REPO = r"E:\06. Dev Projects\Subs-Curated-Bindings"
STICK_DIR = REPO + r"\[Enhanced] MOZA MTQ + MHG"
TOOLS_DIR = REPO + r"\tools"
JG_PATH = STICK_DIR + r"\Joystick Gremlin Profile [ENH][MTQ+MHG][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR + r"\layout_ENH_MTQ_MHG_480_LIVE_exported.xml"
CLUSTERS_JSON = TOOLS_DIR + r"\_moza-cluster-bodies.json"
CSV_PATH = TOOLS_DIR + r"\_sc-keybinds-reference.csv"
OUT_PATH = TOOLS_DIR + r"\_moza-cluster-assignment.json"

# Side filter: chart-side prefix(es) per physical device-short.
# Established by inspecting the layout XML for known flight actions:
#   js2 (00ed3200) has v_pitch/v_yaw/v_roll -> FLIGHT STICK (MHG) -> chart R-*
#   js1 (b3167000) has accel_range/mining_throttle/strafe -> THROTTLE (MTQ) -> chart T-*
DEVICE_SIDE = {
    "00ed3200": ("R-", "MAIN-TRIG"),  # MHG (flight stick / right grip)
    "b3167000": ("T-",),               # MTQ (throttle quadrant)
}

# Main flight-axis actions — stick axes users customize per preference.
# Inputs whose ONLY mapped actions match this pattern get no description.
FLIGHT_AXIS_PAT = re.compile(
    r"^(v|eva|turret|gp)_"
    r"(view_|rotate)?"
    r"(pitch|yaw|roll|movex|movey)$"
)
def is_flight_axis_action(name):
    return bool(FLIGHT_AXIS_PAT.match(name))

STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "on", "in", "by", "with", "for",
    "is", "are", "v", "vehicle", "spaceship", "ship", "press", "hold",
    "btn", "btns", "l", "r", "t",
    "encoder", "knob", "throttle", "cluster", "hat", "way", "trig", "trigger",
    "main", "rapid", "flip", "analog", "mini", "stick", "stage",
    "m", "h", "dt", "pm", "n",
    "bind", "label", "up", "down", "left", "right", "press",
}


LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})

def tokenize(text):
    if not text:
        return []
    text = text.translate(LIGATURES)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    parts = re.split(r"[^a-zA-Z0-9]+", text.lower())
    # Keep digit-only tokens (e.g. MFD slot numbers 1-8) and alpha tokens > 1 char
    return [p for p in parts if p and (p.isdigit() or len(p) > 1) and p not in STOP_WORDS]


def load_csv():
    out = {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("XMLActionName", "")
            disp = row.get("DisplayName", "")
            human = row.get("HumanLabel", "")
            if name:
                out[name] = (disp, human)
    return out


def load_layout():
    root = ET.parse(LAYOUT_PATH).getroot()
    bmap = defaultdict(list)
    amap = defaultdict(list)
    for am in root.findall("./actionmap"):
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    bmap[(int(m.group(1)), int(m.group(2)))].append(aname)
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rotx|roty|rotz|throttle|slider1|slider2)$", inp)
                if m:
                    amap[(int(m.group(1)), m.group(2))].append(aname)
    return bmap, amap


def collect_vjoy_targets(action, by_id, visited=None):
    if visited is None:
        visited = set()
    aid = action.attrib.get("id", "")
    if aid in visited:
        return []
    visited.add(aid)
    out = []
    atype = action.attrib.get("type", "")
    if atype == "map-to-vjoy":
        props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
        try:
            out.append((
                int(props.get("vjoy-device-id", "0")),
                int(props.get("vjoy-input-id", "0")),
                props.get("vjoy-input-type", ""),
            ))
        except ValueError:
            pass
    for ma in action.findall("macro-action"):
        if ma.attrib.get("type") == "vjoy":
            props = {p.findtext("name", ""): p.findtext("value", "") for p in ma.findall("property")}
            try:
                out.append((
                    int(props.get("vjoy-id", "0")),
                    int(props.get("input-id", "0")),
                    props.get("input-type", ""),
                ))
            except ValueError:
                pass
    for el in action.iter():
        if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
            out.extend(collect_vjoy_targets(by_id[el.text], by_id, visited))
    return out


def load_jg():
    tree = ET.parse(JG_PATH)
    root = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root.findall("./library/action")}
    records = []
    for inp in root.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        vt_all = []
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action", "")
            if not rid or rid not in by_id:
                continue
            vt_all.extend(collect_vjoy_targets(by_id[rid], by_id))
        records.append({
            "device": did, "itype": itype, "iid": iid, "mode": mode,
            "vjoy_targets": vt_all,
        })
    return records


def cluster_side_match(cname, side_prefixes):
    """True if cluster name belongs to one of the allowed side prefixes."""
    for sp in side_prefixes:
        if sp.endswith("-") and cname.startswith(sp):
            return True
        if cname == sp:
            return True
    return False


def main():
    print("Loading CSV ...")
    sc_actions = load_csv()
    print(f"  {len(sc_actions)} SC actions in CSV")

    print("Loading layout XML ...")
    button_map, axis_map = load_layout()
    print(f"  {len(button_map)} button slots, {len(axis_map)} axis slots in layout")

    print("Loading JG profile ...")
    jg_records = load_jg()
    print(f"  {len(jg_records)} JG input records (device x mode combinations)")

    print("Loading chart cluster bodies ...")
    with open(CLUSTERS_JSON, encoding="utf-8") as f:
        clusters = json.load(f)
    print(f"  {len(clusters)} chart clusters")

    def tokens_and_bigrams(text):
        toks = tokenize(text)
        bigrams = [f"{toks[i]}_{toks[i+1]}" for i in range(len(toks) - 1)]
        return Counter(toks), Counter(bigrams)

    cluster_tokens = {}
    cluster_bigrams = {}
    for name, body in clusters.items():
        ut, bt = tokens_and_bigrams(body)
        cluster_tokens[name] = ut
        cluster_bigrams[name] = bt

    df = Counter()
    for name, toks in cluster_tokens.items():
        for tk in toks:
            df[tk] += 1
    df_bg = Counter()
    for name, toks in cluster_bigrams.items():
        for tk in toks:
            df_bg[tk] += 1
    total_clusters = len(clusters)
    idf = {tk: math.log(1 + total_clusters / max(1, n)) for tk, n in df.items()}
    idf_bg = {tk: math.log(1 + total_clusters / max(1, n)) for tk, n in df_bg.items()}

    print(f"  {len(df)} distinct unigrams, {len(df_bg)} distinct bigrams")

    # vjoy axis-id 4/5/6 maps to SC layout names rotx/roty/rotz (NOT rx/ry/rz)
    VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz", 7: "slider1", 8: "slider2"}

    assignments = []
    for rec in jg_records:
        device_short = rec["device"][:8]
        side = DEVICE_SIDE.get(device_short, ())
        actions = []
        for (dev, inp, vtype) in rec["vjoy_targets"]:
            if vtype == "button":
                acts = button_map.get((dev, inp), [])
            elif vtype == "axis":
                ax_name = VJOY_AXIS_NAMES.get(inp, "")
                acts = axis_map.get((dev, ax_name), []) if ax_name else []
            else:
                acts = []
            for a in acts:
                actions.append((dev, inp, vtype, a))

        input_tokens = []
        for (dev, inp, vtype, aname) in actions:
            input_tokens.extend(tokenize(aname))
            disp, human = sc_actions.get(aname, ("", ""))
            input_tokens.extend(tokenize(disp))
            input_tokens.extend(tokenize(human))
        input_bigrams = [f"{input_tokens[i]}_{input_tokens[i+1]}" for i in range(len(input_tokens) - 1)]
        input_tokens_set = set(input_tokens)
        input_bigrams_set = set(input_bigrams)

        scores = {}
        for cname, ctoks in cluster_tokens.items():
            if side and not cluster_side_match(cname, side):
                continue
            u_over = input_tokens_set & set(ctoks.keys())
            b_over = input_bigrams_set & set(cluster_bigrams[cname].keys())
            if not u_over and not b_over:
                continue
            raw = sum(idf[tk] for tk in u_over) + 2.0 * sum(idf_bg[tk] for tk in b_over)
            cluster_size = len(ctoks) + len(cluster_bigrams[cname])
            norm = max(1.0, cluster_size ** 0.5)
            scores[cname] = raw / norm

        action_names = {a[3] for a in actions}
        flight_only = (
            action_names
            and all(is_flight_axis_action(n) for n in action_names)
            and all(a[2] == "axis" for a in actions)
        )

        if flight_only:
            cluster = None
            status = "FLIGHT-AXIS"
            ranked = []
        elif scores:
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            top_score = ranked[0][1]
            second_score = ranked[1][1] if len(ranked) > 1 else 0
            gap = top_score - second_score
            cluster = ranked[0][0]
            status = "OK" if gap > 0.5 else ("WEAK" if gap > 0 else "TIE")
        else:
            cluster = None
            status = "UNMATCHED" if actions else "NO-VJOY"
            ranked = []

        assignments.append({
            "device": rec["device"],
            "device_short": device_short,
            "itype": rec["itype"],
            "iid": rec["iid"],
            "mode": rec["mode"],
            "cluster": cluster,
            "status": status,
            "scores": ranked[:5],
            "actions": [a[3] for a in actions],
            "vjoy_targets": rec["vjoy_targets"],
        })

    # Status report
    status_counts = Counter(a["status"] for a in assignments)
    print(f"\nStatus counts: {dict(status_counts)}")

    # Cross-mode coherence
    by_phys = defaultdict(list)
    for a in assignments:
        by_phys[(a["device_short"], a["itype"], a["iid"])].append(a)
    # Moza coherence: only INHERIT from SCM anchor when this mode's match is
    # weak/tie/unmatched. Do NOT cohere (override) OK matches that legitimately
    # differ — the MHG's modifier-mode physical buttons 1-8 functionally do
    # R-BB-N actions instead of the SCM-mode grip actions, and the matcher
    # correctly picks R-BB-N for them.
    inherited = 0
    for k, recs in by_phys.items():
        scm = [r for r in recs if r["mode"] == "SCM Mode" and r["cluster"]]
        anchor = scm[0]["cluster"] if scm else None
        if not anchor:
            ok = [r for r in recs if r["status"] == "OK" and r["cluster"]]
            anchor = ok[0]["cluster"] if ok else None
        if not anchor:
            continue
        for r in recs:
            # Skip FLIGHT-AXIS entirely — pitch/yaw/roll are intentionally not on
            # the chart and should not be back-filled with an anchor cluster.
            if r["status"] == "FLIGHT-AXIS":
                continue
            if not r["cluster"] or r["status"] in ("WEAK", "TIE", "UNMATCHED", "NO-VJOY"):
                if r["cluster"] != anchor:
                    r["inferred_from"] = r["cluster"]
                    r["cluster"] = anchor
                    r["status"] = "INHERITED"
                    inherited += 1
    print(f"Inherited from SCM anchor: {inherited}")

    status_counts2 = Counter(a["status"] for a in assignments)
    print(f"After coherence: {dict(status_counts2)}")

    for status in ("OK", "INHERITED", "COHERED", "WEAK", "TIE", "UNMATCHED", "NO-VJOY", "FLIGHT-AXIS"):
        recs = [a for a in assignments if a["status"] == status]
        if not recs:
            continue
        print(f"\n--- {status} ({len(recs)}) [first 20] ---")
        for a in sorted(recs, key=lambda r: (r["device_short"], r["itype"], int(r["iid"]) if r["iid"].isdigit() else 0, r["mode"]))[:20]:
            sc = ", ".join(f"{c}({s:.1f})" for c, s in a["scores"][:2]) if a["scores"] else "-"
            acts = ",".join(a["actions"][:2])
            print(f"  {a['device_short']} {a['itype']:6s} {a['iid']:>3s} {a['mode']:14s} -> {a['cluster'] or '-':<14s} [{sc}] acts=[{acts}]")

    assigned = {a["cluster"] for a in assignments if a["cluster"]}
    missing = set(clusters.keys()) - assigned
    if missing:
        print(f"\n!! CLUSTERS NOT ASSIGNED TO ANY JG INPUT ({len(missing)}):")
        for c in sorted(missing):
            print(f"  {c}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(assignments, f, indent=2)
    print(f"\nSaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
