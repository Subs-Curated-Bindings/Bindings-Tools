"""
Build JG-input -> chart-cluster mapping for the TM SOL-R 2.

Strategy: for each JG <input>, follow JG -> map-to-vjoy -> layout-XML rebinds ->
SC XMLActionName + DisplayName. Build a token bag from those names. Score each
cluster by sum of token-overlap weighted by token rarity across all clusters
(TF-IDF-ish). Pick the highest-scoring cluster.

This works because cluster bodies contain distinctive words (Landing, Decoy,
Quantum, Burner, MFD, etc.) that match the SC action names well even when the
DisplayName phrasing diverges from the chart's player-speak.
"""
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual TM SOL-R"
TOOLS_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\tools"
JG_PATH = STICK_DIR + r"\Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR + r"\layout_ENH_SOL-R2_480_LIVE_exported.xml"
CLUSTERS_JSON = TOOLS_DIR + r"\_sol-r-cluster-bodies.json"
CSV_PATH = r"C:\Users\subli\Downloads\sc_keybinds_reference.csv"
OUT_PATH = TOOLS_DIR + r"\_sol-r-cluster-assignment.json"

STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "on", "in", "by", "with", "for",
    "is", "are", "v", "vehicle", "spaceship", "ship", "press", "hold",
    "btn", "btns", "l", "r", "ll", "lr", "rl", "rr", "switch",
    "encoder", "knob", "throttle", "cluster", "hat", "way", "trig", "trigger",
    "main", "rapid", "analog", "pinky", "stage",
    "m", "h", "dt", "n",
}


def tokenize(text):
    """Split on underscores, hyphens, spaces; lowercase; drop stop/short words."""
    if not text:
        return []
    # split camelCase into separate words
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    parts = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return [p for p in parts if p and len(p) > 1 and p not in STOP_WORDS]


def load_csv():
    out = {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("XMLActionName", "")
            disp = row.get("DisplayName", "")
            if name:
                out[name] = disp
    return out


def load_layout():
    root = ET.parse(LAYOUT_PATH).getroot()
    bmap = defaultdict(list)
    amap = defaultdict(list)
    hmap = defaultdict(list)
    for am in root.findall("./actionmap"):
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    bmap[(int(m.group(1)), int(m.group(2)))].append(aname)
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rx|ry|rz|throttle|slider1|slider2)$", inp)
                if m:
                    amap[(int(m.group(1)), m.group(2))].append(aname)
                    continue
                m = re.match(r"js(\d+)_hat(\d+)_(up|down|left|right)$", inp)
                if m:
                    hmap[(int(m.group(1)), int(m.group(2)), m.group(3))].append(aname)
    return bmap, amap, hmap


def collect_vjoy_targets(action, by_id, visited=None):
    if visited is None:
        visited = set()
    aid = action.attrib.get("id")
    if aid in visited:
        return []
    visited.add(aid)
    out = []
    if action.attrib.get("type") == "map-to-vjoy":
        props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
        try:
            out.append((
                int(props.get("vjoy-device-id", "0")),
                int(props.get("vjoy-input-id", "0")),
                props.get("vjoy-input-type", ""),
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
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action", "")
            if not rid or rid not in by_id:
                continue
            vt = collect_vjoy_targets(by_id[rid], by_id)
            records.append({
                "device": did, "itype": itype, "iid": iid, "mode": mode,
                "root_id": rid, "vjoy_targets": vt,
            })
    return records


def short_device(did):
    if did.startswith("141b1470"):
        return "L"
    if did.startswith("6686f980"):
        return "R"
    return did[:8]


def cluster_side(name):
    """L or R from cluster name. First letter of name=stick.
    Special: 4WAY-HAT-L-* / -R-*, MAIN-TRIG-L / -R, etc."""
    if "-L" in name and "-R" not in name.replace("-LIVE", ""):
        # patterns like MAIN-TRIG-L, 4WAY-HAT-L-30
        return "L"
    if "-R" in name and "-L" not in name:
        return "R"
    # by first letter
    if name.startswith("L") or name.startswith("LL") or name.startswith("LR"):
        return "L"
    if name.startswith("R") or name.startswith("RL") or name.startswith("RR"):
        return "R"
    return "?"


def main():
    print("Loading CSV ...")
    xml_to_disp = load_csv()

    print("Loading layout XML ...")
    button_map, axis_map, hat_map = load_layout()

    print("Loading JG profile ...")
    jg_records = load_jg()

    print("Loading chart cluster bodies ...")
    with open(CLUSTERS_JSON, encoding="utf-8") as f:
        clusters = json.load(f)

    # Tokenize each cluster body — unigrams and bigrams
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

    # Compute IDF for unigrams and bigrams across clusters
    df = Counter()
    for name, toks in cluster_tokens.items():
        for tk in toks:
            df[tk] += 1
    df_bg = Counter()
    for name, toks in cluster_bigrams.items():
        for tk in toks:
            df_bg[tk] += 1
    total_clusters = len(clusters)
    import math
    idf = {tk: math.log(1 + total_clusters / max(1, n)) for tk, n in df.items()}
    idf_bg = {tk: math.log(1 + total_clusters / max(1, n)) for tk, n in df_bg.items()}

    print(f"  {total_clusters} clusters, {len(df)} distinct tokens")
    print(f"  Most distinctive tokens (high IDF): {sorted(idf.items(), key=lambda x: -x[1])[:15]}")
    print(f"  Least distinctive (low IDF): {sorted(idf.items(), key=lambda x: x[1])[:15]}")

    # vjoy axis-id -> standard axis name (R14 default mapping)
    VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rx", 5: "ry", 6: "rz", 7: "slider1", 8: "slider2"}

    # For each JG record, build token bag from SC actions and score clusters
    assignments = []
    for rec in jg_records:
        side = short_device(rec["device"])
        actions = []
        for (dev, inp, vtype) in rec["vjoy_targets"]:
            if vtype == "button":
                acts = button_map.get((dev, inp), [])
            elif vtype == "axis":
                ax_name = VJOY_AXIS_NAMES.get(inp, "")
                acts = axis_map.get((dev, ax_name), []) if ax_name else []
            elif vtype == "hat":
                acts = []  # rare; skip
            else:
                acts = []
            for a in acts:
                actions.append((dev, inp, vtype, a))

        # Build token bag for this JG input's actions
        input_tokens = []
        for (dev, inp, vtype, aname) in actions:
            input_tokens.extend(tokenize(aname))
            input_tokens.extend(tokenize(xml_to_disp.get(aname, "")))
        # also build bigrams
        input_bigrams = [f"{input_tokens[i]}_{input_tokens[i+1]}" for i in range(len(input_tokens) - 1)]
        input_tokens_set = set(input_tokens)
        input_bigrams_set = set(input_bigrams)

        # Score each cluster: weighted sum of unigram + bigram overlaps
        scores = {}
        for cname, ctoks in cluster_tokens.items():
            cs = cluster_side(cname)
            if cs != "?" and cs != side:
                continue
            u_over = input_tokens_set & set(ctoks.keys())
            b_over = input_bigrams_set & set(cluster_bigrams[cname].keys())
            if not u_over and not b_over:
                continue
            s = sum(idf[tk] for tk in u_over) + 2.0 * sum(idf_bg[tk] for tk in b_over)
            scores[cname] = s

        # Pick winner
        if scores:
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            top_cname, top_score = ranked[0]
            second_score = ranked[1][1] if len(ranked) > 1 else 0
            # Confidence: top_score vs second_score
            gap = top_score - second_score
            cluster = top_cname
            status = "OK" if gap > 0.5 else ("WEAK" if gap > 0 else "TIE")
        else:
            cluster = None
            status = "UNMATCHED" if actions else "NO-VJOY"
            ranked = []

        assignments.append({
            "device": rec["device"],
            "side": side,
            "itype": rec["itype"],
            "iid": rec["iid"],
            "mode": rec["mode"],
            "root_id": rec["root_id"],
            "cluster": cluster,
            "status": status,
            "input_tokens": sorted(input_tokens),
            "scores": ranked[:5],
            "actions": [a[3] for a in actions],
            "vjoy_targets": rec["vjoy_targets"],
        })

    # Report
    print()
    status_counts = Counter(a["status"] for a in assignments)
    print(f"Status counts: {dict(status_counts)}")
    print()

    # Show samples
    for status in ("OK", "WEAK", "TIE", "UNMATCHED", "NO-VJOY"):
        recs = [a for a in assignments if a["status"] == status]
        if not recs:
            continue
        print(f"--- {status} ({len(recs)}) [first 30] ---")
        for a in sorted(recs, key=lambda r: (r["side"], r["itype"], int(r["iid"]) if r["iid"].isdigit() else 0, r["mode"]))[:30]:
            scores_brief = ", ".join(f"{c}({s:.1f})" for c, s in a["scores"][:3])
            acts_brief = ",".join(a["actions"][:3])
            print(f"  {a['side']} {a['itype']:6s} id={a['iid']:>3s} {a['mode']:14s} "
                  f"-> {a['cluster'] or '-':<14s} [{scores_brief}] acts=[{acts_brief}]")
        print()

    # Cross-mode coherence: per (side, itype, iid) prefer SCM Mode cluster.
    # Inputs with NO-VJOY in other modes inherit the SCM Mode cluster.
    by_phys = defaultdict(list)
    for a in assignments:
        by_phys[(a["side"], a["itype"], a["iid"])].append(a)

    for k, recs in by_phys.items():
        # Find the "anchor" cluster — SCM Mode if available, else any OK assignment
        scm_recs = [r for r in recs if r["mode"] == "SCM Mode" and r["cluster"]]
        anchor = scm_recs[0]["cluster"] if scm_recs else None
        if not anchor:
            ok_recs = [r for r in recs if r["status"] == "OK" and r["cluster"]]
            anchor = ok_recs[0]["cluster"] if ok_recs else None
        if not anchor:
            continue
        for r in recs:
            if not r["cluster"] or r["status"] in ("WEAK", "TIE", "UNMATCHED", "NO-VJOY"):
                if r["cluster"] != anchor:
                    r["inferred_from"] = r["cluster"]
                    r["cluster"] = anchor
                    r["status"] = "INHERITED"
            elif r["cluster"] != anchor and r["mode"] != "SCM Mode":
                # Force coherence: non-SCM mode mismatched -> override to SCM
                r["inferred_from"] = r["cluster"]
                r["cluster"] = anchor
                r["status"] = "COHERED"

    # Re-tally
    status_counts2 = Counter(a["status"] for a in assignments)
    print(f"\nAfter cross-mode coherence: {dict(status_counts2)}")

    incoherent = []
    for k, recs in by_phys.items():
        clusters_seen = {r["cluster"] for r in recs if r["cluster"]}
        if len(clusters_seen) > 1:
            incoherent.append((k, clusters_seen, recs))
    if incoherent:
        print(f"--- STILL INCOHERENT ({len(incoherent)}) ---")
        for k, cs, recs in incoherent[:20]:
            print(f"  {k}: {cs}")
            for r in recs:
                print(f"    mode={r['mode']:14s} cluster={(r['cluster'] or '-'):14s} status={r['status']}")
        print()

    # Show clusters that still have NO description-eligible assignment
    assigned_clusters = {a["cluster"] for a in assignments if a["cluster"]}
    missing = set(clusters.keys()) - assigned_clusters
    if missing:
        print(f"--- CLUSTERS WITHOUT ANY ASSIGNMENT ({len(missing)}) ---")
        for c in sorted(missing):
            print(f"  {c}")
        print()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(assignments, f, indent=2)
    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
