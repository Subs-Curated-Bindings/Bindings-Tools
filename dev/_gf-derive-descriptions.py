"""
Gunfighter — auto-derive JG description-action mappings.

Strategy:
  1. Parse chart-text dump (we hand-built {etched -> text} from the Affinity walk).
  2. Parse JG profile: for each input, gather vJoy targets.
  3. Parse layout XML: for each vJoy slot, gather SC action names.
  4. Match each JG input to a chart cluster by overlap between SC action keywords
     (extracted from XMLActionName) and chart text keywords.
  5. Emit a JSON of {(device,type,id,mode) -> {etched, body}} for high-confidence matches.

Outputs:
  tools/_gf-descriptions.json — confident assignments
  tools/_gf-descriptions-low-conf.json — fuzzy/ambiguous, for review
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds")
JG_PATH = STICK_DIR / "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR / "layout_ENH_GF_480_LIVE_exported.xml"
OUT_DIR = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\tools")

# Chart bind cluster -> raw text (extracted from Affinity earlier in the session)
# These come straight from the .af inspection — text content per section per direction.
# Format: { etched_name: chart_text }
CHART_CLUSTERS = {
    # ----- LEFT SIDE -----
    "L-A1B":      "Precision Aiming | [H] Precision Max Zoom",
    "L-A2":       "[H] Master Mode Cycle Nav, & SCM | Operator Mode Cycle Guns, Flight, Missile, Mining, Salvage, Scanning, & Quantum",
    "L-D1":       "[M] Modifier",
    "L-A3.up":    "Flight Ready | [M] Toggle Power On/Off Lights Toggle [H] Light Amplification [DT] Port Lock Toggle",
    "L-A3.down":  "[M] Thruster Power Toggle Landing Gear | [H] Auto Land | Toggle Docking | Invoke Docking",
    "L-A3.left":  "[M] Weapon Power Toggle Open Doors Toggle | [DT] Lock Doors Toggle",
    "L-A3.right": "[M] Shields Power Toggle VTOL Toggle | Turret Position Toggle [DT] Cycle Config",
    "L-A3.press-in": "Request Landing Request Jumpgate [M]Request Cargo",
    "L-A4.up":    "Freelook1 [H] Reset Freelook [M] Reset Range",
    "L-A4.down":  "[M] Scanning Angle [M] Bomb Range [M] Tractor Distance Camera (3rd Person)",
    "L-A4.left":  "Head Tracking On/Off [M] Reset Head Tracking",
    "L-A4.right": "Dynamic Zoom | [H] Missile Cinematic Camera [M] Toggle Docking Camera",
    "L-A4.press-in": "[H] Look Behind [M] Tractor Distance [M] Bomb Range [M] Scanning Angle",
    "L-C1.up":    "E.S.P. Toggle | Turret E.S.P | Remote Turret 3 [M] Adv. HUD Toggle",
    "L-C1.down":  "Stagger Fire Toggle Stagger Fire Toggle Remote Turret 1 [M] GSafe Toggle | Turret Gyro Mode [M] Exit Seat Start/Pause Stop Watch [H] Reset Stop Watch",
    "L-C1.left":  "Lead/Lag Pip Toggle [M] Turret VJoy Remote Turret 2",
    "L-C1.right": "Gimbal Cycle Fixed/Auto [H] Recenter Turret Salvage Gimbal Toggle [DT] Salvage Gimbal Reset",
    "L-A1.up":    "Increase Limiter Increase Limiter [M] Acc. Limiter Increase",
    "L-A1.down":  "[M] Acc. Limiter Decrease Decrease Limiter Decrease Limiter",
    "L-A1.left":  "Cruise Control Toggle [M] Set Limiter to SCM",
    "L-A1.right": "Set Trim Toggle [H] Set Trim 100% [M] Release Trim",
    "L-A1.press-in": "Mode Switch To Analog UNBOUND",
    "MAIN-TRIG-L": "After Burner Toggle SCM Limiter [H] Release Trim Turret Mouse Mode Turret Zoom",
    "RAPID-TRIG-L": "Trigger Up | Scan Ping [H] Light Amplification | Trigger Down | Space Brake",
    # ----- RIGHT SIDE -----
    "R-A1B":      "Decouple Toggle",
    "R-A2":       "[H] Select Mining/Salvage Mode Toggle Bomb Impact",
    "R-D1":       "[H] VOIP PTT | [M][H] VOIP PTT Proximity [DT] Chat Window Toggle [M] Hail Target | [M] Accept Notification | Decline Notification",
    "R-A3.up":    "Inc. Mining Laser Power (Slow) Fire Fracture | Missile Count Up",
    "R-A3.down":  "Sub Target Reset | Missle Count Down | Fire Disintegrate | [M] Cycle Structural Modes Dec. Mining Laser Power (Slow)",
    "R-A3.left":  "Sub Target Back Missile Type Previous Fire Left Tool | [M] Left Modifier Cycle",
    "R-A3.right": "Sub Target Forward Missile Type Next | Fire Right Tool | [M] Right Modifier Cycle",
    "R-A3.press-in": "Reset Missile Count Cycle Fracture/Extraction Beam Axis Toggle",
    "R-A4.up":    "Capacitor Reset",
    "R-A4.down":  "UNBOUND",
    "R-A4.left":  "Weapon Cap Increase | [M] Weapon Cap Decrease [H] Weapon Set to Max [M][H] Weapon Set to Min",
    "R-A4.right": "Shield Cap Increase | [M] Shield Cap Decrease [H] Shield Set to Max [M][H] Shield Set to Min",
    "R-A4.press-in": "Thruster Cap Increase [M] Thruster Cap Decrease [H] Thruster Set to Max [M][H] Thruster Set to Min",
    "R-C1.up":    "Mining Module 1 Focus Fracture",
    "R-C1.down":  "Shileds Aft Focus Disintegration",
    "R-C1.left":  "Shields Left Mining Module 3 Focus Left Tool",
    "R-C1.right": "Shields Right Mining Module 2 Focus Right Tool",
    "R-C1.press-in": "Shields Reset | Focus All Salvage Heads",
    "R-A1.up":    "Increase Mining Laser Power | Decrease Mining Laser Power",
    "R-A1.down":  "Unlock Target | [M] Target Attacker Closest [M][H] Select MFD Down1",
    "R-A1.left":  "Tobii Gaze Target | Target Hostile Forward | [DT] Target Hostile Closest [M][H] Select MFD Left1 [M][DT] Select MFD Cast Left1",
    "R-A1.right": "Target All Forward | [DT] Target All Closest [M][H] Select MFD Right1 [M][DT] Select MFD Cast Right1 [M] Cycle MFD Page Forward",
    "R-A1.up.alt": "[M][H] Select MFD Up1 | [M] Target Attacker Forward Target Under Reticle",
    "R-A1.press-in.device": "Mode Switch To Analog",
    "R-A1.press-in.game":   "Freelook1",
    "MAIN-TRIG-R.stage-1": "Fire Selected Weapon Group Fire Weapon Group 2 | [H] Engage Quantum | Fire Salvage Beam | Fire Mining Laser",
    "MAIN-TRIG-R.stage-2": "Fire Selected & Group 3",
    "RAPID-TRIG-R": "Trigger Up | Decoy, [H] Multi Decoy | [M] Next Weapon Preset | Trigger Down | Noise, [M] Prev. Weapon Preset",
}


def keywords_from_text(text):
    """Lowercase tokenize, drop stopwords + tagging."""
    text = re.sub(r"\[(M|H|DT)\]", " ", text)  # drop tag prefixes
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    tokens = text.split()
    stop = {"the", "a", "an", "of", "to", "for", "on", "off", "in", "out", "up", "down",
            "left", "right", "and", "or", "is", "be", "by", "at", "with", "via", "vs",
            "toggle", "mode", "fire", "set", "cycle"}
    # Keep meaningful tokens of length >= 3
    return {t for t in tokens if len(t) >= 3 and t not in stop}


SC_DISPLAY_NAMES = {}
def load_sc_csv():
    global SC_DISPLAY_NAMES
    csv_path = Path(r"C:\Users\subli\Downloads\sc_keybinds_reference.csv")
    if not csv_path.exists():
        return
    with open(csv_path, encoding="utf-8-sig") as f:
        header = f.readline().strip().split(",")
        xan_idx = header.index("XMLActionName")
        disp_idx = header.index("DisplayName")
        for line in f:
            parts = line.rstrip("\n").split(",")
            if len(parts) > max(xan_idx, disp_idx):
                xan = parts[xan_idx]
                disp = parts[disp_idx]
                # Skip noisy CIG ui_* placeholders
                if disp.startswith("ui_"):
                    disp = ""
                SC_DISPLAY_NAMES[xan] = disp


def sc_keywords_from_action_name(action_name):
    """Combine tokens from the XML action name AND the SC DisplayName (if available)."""
    name = action_name
    for prefix in ("v_", "eva_", "ui_", "ifcs_", "vehicle_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    raw_tokens = name.split("_")
    out = set()
    for t in raw_tokens:
        if len(t) >= 3:
            out.add(t.lower())
    # Also tokenize the DisplayName — usually more aligned with chart's player-speak
    disp = SC_DISPLAY_NAMES.get(action_name, "")
    if disp:
        disp_lower = re.sub(r"[^a-z0-9 ]", " ", disp.lower())
        for t in disp_lower.split():
            if len(t) >= 3:
                out.add(t)
    # Boost shorter compound-word splits
    compound_splits = {
        "flightready": ["flight", "ready"],
        "freelook": ["free", "look"],
        "headtrack": ["head", "track"],
        "afterburner": ["after", "burner"],
        "portlocks": ["port", "locks"],
        "portlock": ["port", "lock"],
        "doorlocks": ["door", "locks"],
        "decouple": ["decouple"],
        "decoupling": ["decouple"],
    }
    for tok in list(out):
        if tok in compound_splits:
            out.update(compound_splits[tok])
    return out


# ---- Parse JG profile: input -> vjoy targets ----
def parse_jg():
    tree = ET.parse(JG_PATH)
    root = tree.getroot()
    by_id = {a.attrib['id']: a for a in root.findall('./library/action')}

    def collect_vjoy(action, visited=None):
        if visited is None: visited = set()
        aid = action.attrib.get('id')
        if aid in visited: return []
        visited.add(aid)
        out = []
        if action.attrib.get('type') == 'map-to-vjoy':
            props = {p.findtext('name', ''): p.findtext('value', '') for p in action.findall('property')}
            try:
                out.append((int(props.get('vjoy-device-id', '0')),
                            props.get('vjoy-input-type', ''),
                            int(props.get('vjoy-input-id', '0'))))
            except ValueError:
                pass
        for el in action.iter():
            if el.tag == 'action-id' and el.text and el.text in by_id and el.text != aid:
                out.extend(collect_vjoy(by_id[el.text], visited))
        return out

    records = []
    for inp in root.findall('./inputs/input'):
        did = inp.findtext('device-id')
        itype = inp.findtext('input-type')
        iid = inp.findtext('input-id')
        mode = inp.findtext('mode')
        for ac in inp.findall('action-configuration'):
            rid = ac.findtext('root-action')
            if rid in by_id:
                vjoy = collect_vjoy(by_id[rid])
                records.append({
                    'device_id': did,
                    'input_type': itype,
                    'input_id': iid,
                    'mode': mode,
                    'vjoy_targets': vjoy,
                })
    return records


# ---- Parse layout: vjoy slot -> SC action names ----
def parse_layout():
    tree = ET.parse(LAYOUT_PATH)
    root = tree.getroot()
    bm = defaultdict(list)  # (dev, btn) -> [action_name, ...]
    axis_m = defaultdict(list)
    hat_m = defaultdict(list)
    for am in root.findall('./actionmap'):
        for act in am.findall('action'):
            aname = act.attrib.get('name', '')
            for r in act.findall('rebind'):
                inp = r.attrib.get('input', '')
                m = re.match(r'js(\d+)_button(\d+)$', inp)
                if m:
                    bm[(int(m.group(1)), int(m.group(2)))].append(aname)
                    continue
                m = re.match(r'js(\d+)_(x|y|z|rx|ry|rz|throttle|slider1|slider2)$', inp)
                if m:
                    axis_m[(int(m.group(1)), m.group(2))].append(aname)
                    continue
                m = re.match(r'js(\d+)_hat(\d+)_(up|down|left|right)$', inp)
                if m:
                    hat_m[(int(m.group(1)), int(m.group(2)), m.group(3))].append(aname)
    return bm, axis_m, hat_m


def main():
    load_sc_csv()
    records = parse_jg()
    bm, axis_m, hat_m = parse_layout()

    # Precompute chart cluster keyword sets
    chart_kws = {etched: keywords_from_text(text) for etched, text in CHART_CLUSTERS.items()}

    # For each JG input (SCM Mode + Modifier), find best matching chart cluster
    confident = {}  # key -> {etched, body, scm_actions, chart_kws}
    low_conf = {}

    for r in records:
        if r['input_type'] == 'axis':
            continue  # skip axes for now; handle them separately
        # Gather SC action keywords this input emits
        sc_action_names = []
        sc_kws = set()
        for v in r['vjoy_targets']:
            dev, vtype, vid = v
            if vtype == 'button':
                actions = bm.get((dev, vid), [])
                sc_action_names.extend(actions)
                for an in actions:
                    sc_kws |= sc_keywords_from_action_name(an)
            elif vtype == 'hat':
                # Hat targets fire as hat directions in layout, gather all 4 dirs
                for d in ('up', 'down', 'left', 'right'):
                    actions = hat_m.get((dev, vid, d), [])
                    sc_action_names.extend(actions)
                    for an in actions:
                        sc_kws |= sc_keywords_from_action_name(an)
        if not sc_kws:
            continue
        # Score each chart cluster by keyword overlap (weighted: match count / union size)
        scores = []
        for etched, ckws in chart_kws.items():
            if not ckws:
                continue
            overlap = len(sc_kws & ckws)
            if overlap == 0:
                continue
            score = overlap / max(1, min(len(sc_kws), len(ckws)))
            scores.append((score, overlap, etched))
        scores.sort(reverse=True)
        key = f"{r['device_id']}|{r['input_type']}|{r['input_id']}|{r['mode']}"
        if scores and (scores[0][0] >= 0.4 and scores[0][1] >= 2 and (len(scores) == 1 or scores[0][0] > scores[1][0] * 1.5)):
            best = scores[0]
            confident[key] = {
                'etched': best[2],
                'mode_tag': '' if r['mode'] == 'SCM Mode' else r['mode'],
                'body': CHART_CLUSTERS[best[2]],
                'sc_actions': sc_action_names,
                'score': best[0],
                'overlap': best[1],
            }
        elif scores:
            top3 = scores[:3]
            low_conf[key] = {
                'top_candidates': [(s, o, e) for s, o, e in top3],
                'sc_actions': sc_action_names,
                'mode': r['mode'],
            }

    print(f"Confident matches: {len(confident)}")
    print(f"Low-confidence:    {len(low_conf)}")
    print()
    print("=" * 90)
    print("CONFIDENT (will be written to JSON):")
    print("=" * 90)
    for k, v in sorted(confident.items()):
        print(f"  {k}")
        print(f"    -> {v['etched']:25s} mode={v['mode_tag']:14s} score={v['score']:.2f} overlap={v['overlap']}")
        print(f"       sc_actions={v['sc_actions'][:3]}")
        print(f"       body={v['body'][:80]}")
    print()
    print("=" * 90)
    print("LOW-CONFIDENCE (for Sub to triage):")
    print("=" * 90)
    for k, v in sorted(low_conf.items()):
        print(f"  {k}")
        print(f"    mode={v['mode']} sc_actions={v['sc_actions'][:3]}")
        for s, o, e in v['top_candidates']:
            print(f"      candidate {e:25s} score={s:.2f} overlap={o}")

    (OUT_DIR / "_gf-descriptions.json").write_text(json.dumps(confident, indent=2), encoding="utf-8")
    (OUT_DIR / "_gf-descriptions-low-conf.json").write_text(json.dumps(low_conf, indent=2), encoding="utf-8")
    print()
    print(f"Wrote {OUT_DIR / '_gf-descriptions.json'} ({len(confident)} entries)")
    print(f"Wrote {OUT_DIR / '_gf-descriptions-low-conf.json'} ({len(low_conf)} entries)")


if __name__ == "__main__":
    main()
