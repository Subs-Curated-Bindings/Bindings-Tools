"""
Produce a draft labels.json that proposes an action-label for each JG <input>'s
root action, in the em-dash format Sub picked:

    <etched-name>[.<dir>] [<mode-tag>] — <player-speak description>

Approach:
  1. Build the SCM Mode + Modifier inputs per device.
  2. For each input, follow the root-action -> map-to-vjoy chain to get the
     vJoy slot, look up the layout XML for SC actions, and use those to
     identify the chart bind cluster whose text content overlaps the action set.
  3. Output JSON keyed by root-action-id with the proposed action-label.

Confidence is scored:
  - 'high': unambiguous match (single chart cluster wins by >= 3 points)
  - 'medium': clear winner but lower margin
  - 'low': tied or no clear winner — flag for manual review
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT"
JG_XML = os.path.join(STICK_DIR, "Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml")
LAYOUT_XML = os.path.join(STICK_DIR, "layout_ENH_NXT_480_LIVE_exported.xml")
SVG_PATH = r"C:\Users\subli\OneDrive\Desktop\nxt-chart-machine-readable.svg"
OUT_JSON = r"C:\Users\subli\OneDrive\Desktop\nxt-labels-draft.json"

DEFAULT_MODE = "SCM Mode"
MOD_MODE = "Modifier"


def parse_jg(jg_path):
    tree = ET.parse(jg_path)
    root = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root.findall("./library/action")}

    # input element -> (did, itype, iid, mode, root_action_id, behavior)
    inputs = []
    for inp in root.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            beh = ac.findtext("behavior", "")
            ra = ac.findtext("root-action", "")
            if ra:
                inputs.append((did, itype, iid, mode, ra, beh))
    return root, by_id, inputs


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
            dev = int(props.get("vjoy-device-id", "0"))
            inp = int(props.get("vjoy-input-id", "0"))
            ityp = props.get("vjoy-input-type", "")
            out.append((dev, inp, ityp))
        except ValueError:
            pass
    for el in action.iter():
        if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
            out.extend(collect_vjoy_targets(by_id[el.text], by_id, visited))
    return out


def parse_layout(layout_path):
    root = ET.parse(layout_path).getroot()
    vjoy_button = defaultdict(list)
    vjoy_axis = defaultdict(list)
    vjoy_hat = defaultdict(list)
    for am in root.findall("./actionmap"):
        amname = am.attrib.get("name", "")
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    vjoy_button[(int(m.group(1)), int(m.group(2)))].append((amname, aname))
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rx|ry|rz|slider1|slider2)$", inp)
                if m:
                    vjoy_axis[(int(m.group(1)), m.group(2))].append((amname, aname))
                    continue
                m = re.match(r"js(\d+)_hat(\d+)_(up|down|left|right)$", inp)
                if m:
                    vjoy_hat[(int(m.group(1)), int(m.group(2)), m.group(3))].append((amname, aname))
                    continue
    return vjoy_button, vjoy_axis, vjoy_hat


def parse_svg(svg_path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    clusters = {}
    for elem in root.iter():
        eid = elem.attrib.get("id", "")
        if not (eid.startswith("bind.") or eid.startswith("label.")):
            continue
        parts = []
        for t in elem.iter():
            tag = t.tag.split("}", 1)[-1]
            if tag in ("text", "tspan") and t.text:
                parts.append(t.text)
        clusters[eid] = " ".join(" ".join(parts).split())
    return clusters


def cluster_tokens(text):
    t = text.lower()
    t = re.sub(r"\[[a-z]+\]", " ", t, flags=re.IGNORECASE)
    tokens = re.findall(r"[a-z0-9]+", t)
    stop = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "off", "with", "for"}
    return set(tok for tok in tokens if tok not in stop and len(tok) >= 3)


def action_tokens(action_name, actionmap):
    n = re.sub(r"^[a-z]_", "", action_name).lower()
    parts = re.split(r"[_]+", n)
    tokens = set(parts)
    # Strip common SC stem variations
    tokens.update({t.rstrip("s") for t in parts if len(t) > 3})
    # Useful actionmap-derived hints
    am = actionmap.lower()
    if "salvage" in am: tokens.add("salvage")
    if "mining" in am: tokens.add("mining")
    if "missile" in am: tokens.add("missile")
    if "weapon" in am: tokens.add("weapon")
    if "shield" in am: tokens.add("shield")
    return tokens


# Player-speak token expansion: SC action stem -> chart-speak tokens
EXPAND = {
    "afterburner": {"burner", "afterburner"},
    "boost": {"boost"},
    "strafe_trim": {"trim"},
    "operator_mode": {"operator", "mode"},
    "master_mode": {"master", "mode", "scm", "nav"},
    "ads": {"precision", "aiming", "zoom"},
    "flightready": {"flight", "ready"},
    "power_toggle": {"power", "toggle"},
    "autoland": {"auto", "land", "landing"},
    "docking": {"docking", "dock"},
    "doors": {"door", "doors"},
    "atc_request": {"request", "landing"},
    "jump_request": {"jumpgate", "jump"},
    "view_cycle": {"view", "camera", "cycle"},
    "dynamic_zoom": {"dynamic", "zoom"},
    "missile_cinematic": {"cinematic", "missile"},
    "view_look_behind": {"look", "behind"},
    "headtrack": {"head", "tracking", "track"},
    "freelook": {"freelook"},
    "bombing_hud_range": {"bomb", "range"},
    "remote_turret": {"remote", "turret"},
    "staggered_fire": {"stagger"},
    "gforce_safety": {"gforce"},
    "esp": {"esp"},
    "advanced_hud": {"adv", "hud"},
    "tractor": {"tractor"},
    "gyromode": {"gyro"},
    "lead_lag": {"lead", "lag", "pip"},
    "gimbal": {"gimbal"},
    "recenter": {"recenter"},
    "ping": {"ping", "scan"},
    "brake": {"brake"},
    "limiter": {"limiter"},
    "scan_focus": {"scanning", "angle"},
    "mining_throttle": {"mining", "throttle"},
    "close_doors": {"close", "doors"},
    "open_doors": {"open", "doors"},
    "loading_area": {"cargo"},
    "transform": {"cycle", "config", "vtol"},
    "change_position": {"turret", "position"},
    "qdrive": {"light", "amplification"},
    "scanning_trigger": {"scan", "ping"},
    "mining_laser_fire": {"mining", "fire"},
    "salvage_fire_focused": {"salvage", "fire"},
    "weapon_preset_attack": {"fire", "weapon", "group"},
    "launch_missile": {"fire", "missile"},
    "fire_guns": {"fire", "guns"},
    "repair_all": {"repair", "self"},
    "impact_point": {"impact"},
    "decoupling": {"decoupled"},
    "chat": {"chat"},
    "pushtotalk": {"voip", "ptt"},
    "viewownplayer": {"voip", "ptt"},
    "hail": {"hail"},
    "fire_fracture": {"fracture"},
    "max_missiles": {"missile", "count"},
    "cycle_modifiers_right": {"right", "modifier"},
    "fire_right": {"right", "tool"},
    "cycle_missile_fwd": {"missile", "next"},
    "cycle_modifiers_structural": {"structural"},
    "fire_disintegrate": {"disintegrate"},
    "cycle_modifiers_left": {"left", "modifier"},
    "fire_left": {"left", "tool"},
    "cycle_missile_back": {"missile", "previous"},
    "mining_laser_type": {"fracture", "extraction"},
    "beam_spacing": {"beam", "spacing"},
    "reset_max_missiles": {"reset", "missile"},
    "target_cycle_attacker": {"attacker"},
    "target_cycle_all": {"target"},
    "target_cycle_hostile": {"hostile"},
    "target_cycle_subitem": {"sub", "target"},
    "target_lock": {"target", "lock"},
    "target_unlock": {"unlock"},
    "target_under_reticle": {"under", "reticle"},
    "target_pin": {"pin"},
    "target_unpin": {"unpin"},
    "consumable": {"module"},
    "focus_fracture": {"focus", "fracture"},
    "shield_raise_forward": {"shields"},
    "mfd_movement": {"mfd"},
    "focus_right": {"focus", "right"},
    "shield_raise_right": {"shields", "right"},
    "mfd_interact": {"mfd"},
    "soft_select_cast_right": {"cast", "right"},
    "focus_disintegrate": {"focus", "disintegration"},
    "shield_raise_back": {"shields", "aft"},
    "focus_left": {"focus", "left"},
    "shield_raise_left": {"shields", "left"},
    "soft_select_cast_left": {"cast", "left"},
    "focus_all": {"focus", "all"},
    "shield_reset": {"shields", "reset"},
    "decoy_launch": {"decoy"},
    "preset_emp": {"weapon"},
    "preset_next": {"weapon", "next"},
    "preset_prev": {"weapon", "previous"},
    "noise_launch": {"multi", "decoy"},
    "decoy_burst": {"decoy", "burst"},
    "lights": {"lights"},
    "light_amplification": {"light", "amplification"},
    "emergency_exit": {"exit", "seat", "quick"},
    "turret_remote_exit": {"exit", "turret"},
    "eject": {"eject"},
    "portlocks": {"port", "lock"},
    "doorlocks": {"doors", "lock"},
    "capacitor": {"capacitor", "weapon", "shield", "thruster", "cap"},
    "shield_cap": {"shield", "cap"},
    "weapon_cap": {"weapon", "cap"},
    "thruster_cap": {"thruster", "cap"},
}


def expand_action_tokens(action_name):
    n = re.sub(r"^[a-z]_", "", action_name).lower()
    tokens = set(re.split(r"[_]+", n))
    for key, extras in EXPAND.items():
        if key in n:
            tokens.update(extras)
    return tokens


def score_match(cluster_text, action_set):
    cl_toks = cluster_tokens(cluster_text)
    if not cl_toks: return 0
    act_toks = set()
    for an in action_set:
        act_toks.update(expand_action_tokens(an))
    return len(cl_toks & act_toks)


def main():
    jg_root, by_id, jg_inputs = parse_jg(JG_XML)
    vbtn, vax, vhat = parse_layout(LAYOUT_XML)
    clusters = parse_svg(SVG_PATH)
    binds = {k: v for k, v in clusters.items() if k.startswith("bind.")}

    devices = sorted({did for (did,_,_,_,_,_) in jg_inputs})
    side_for_device = {devices[0]: "L", devices[1]: "R"} if len(devices) >= 2 else {}

    draft = {}
    # Process by (device, input-type, input-id, mode)
    for did, itype, iid, mode, ra, beh in jg_inputs:
        if ra not in by_id:
            continue
        if mode not in (DEFAULT_MODE, MOD_MODE):
            continue
        action = by_id[ra]
        vjoys = collect_vjoy_targets(action, by_id)
        # Resolve SC actions reachable through this root
        sc_actions = []
        for (vdev, vinp, vtyp) in vjoys:
            if vtyp == "button":
                sc_actions.extend(vbtn.get((vdev, vinp), []))
            # axes / hats handled separately below
        # Hat behavior: behavior=hat means this root maps the device hat to vJoy hat
        if itype == "hat" and beh == "hat":
            # We don't have a direct vJoy hat target list — but the layout XML
            # uses js1_hat1_up/down/left/right for hats. Use the JG's vjoy
            # output device id assumption: vjoy device = JG device order.
            jg_dev_idx = devices.index(did) + 1
            for direction in ("up", "down", "left", "right"):
                sc_actions.extend(vhat.get((jg_dev_idx, 1, direction), []))

        # Score each chart cluster against this input's SC action set
        side = side_for_device.get(did, "?")
        candidates = []
        for cid, ctext in binds.items():
            # Side-filter the cluster against the device side
            stripped = cid[len("bind."):]
            cluster_side = "L" if stripped.startswith("L-") or "TRIG-L" in stripped else \
                           "R" if stripped.startswith("R-") or "TRIG-R" in stripped else "?"
            if side != "?" and cluster_side != "?" and cluster_side != side:
                continue
            score = score_match(ctext, [a for _, a in sc_actions])
            if score > 0:
                candidates.append((score, cid, ctext))
        candidates.sort(reverse=True)
        if not candidates:
            confidence = "low"
            chosen = None
        else:
            top = candidates[0]
            second = candidates[1] if len(candidates) > 1 else (0, "", "")
            if top[0] >= 3 and (top[0] - second[0]) >= 2:
                confidence = "high"
            elif top[0] >= 2 and (top[0] - second[0]) >= 1:
                confidence = "medium"
            else:
                confidence = "low"
            chosen = top[1]

        key = f"{ra}"
        # mode-tag suffix
        mode_tag = ""
        if mode == MOD_MODE:
            mode_tag = "[Modifier]"
        # description: the chart cluster's text content, simplified to one line
        if chosen:
            stripped = chosen[len("bind."):]
            chart_text = binds[chosen]
            # take the first phrase before [M] or | as the SCM-default description
            primary = re.split(r"\[M\]|\[H\]|\[DT\]", chart_text)[0].strip()
            primary = re.sub(r"\s+", " ", primary)[:65]
            if mode == DEFAULT_MODE:
                label = f"{stripped} — {primary}"
            else:
                # for modifier mode, take the [M]-prefixed segment if any
                mod_match = re.search(r"\[M\][^\[]*", chart_text)
                mod_desc = re.sub(r"\[M\]\s*", "", mod_match.group()).strip() if mod_match else primary
                mod_desc = re.sub(r"\s+", " ", mod_desc)[:60]
                label = f"{stripped} [Modifier] — {mod_desc}"
        else:
            label = f"(unmatched) — {itype}-{iid} {mode}"

        draft[key] = {
            "device-id": did,
            "side": side,
            "input-type": itype,
            "input-id": iid,
            "mode": mode,
            "behavior": beh,
            "vjoy_targets": [f"js{d}_btn{i}" if t == "button" else f"js{d}_{t}{i}" for d,i,t in vjoys],
            "sc_actions": [f"{a}({am})" for am, a in sc_actions[:8]],
            "chosen_cluster": chosen,
            "confidence": confidence,
            "candidates_top3": [(s, c) for s, c, _ in candidates[:3]],
            "proposed_label": label,
        }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    # Summary
    by_conf = defaultdict(int)
    for r in draft.values():
        by_conf[r["confidence"]] += 1
    print(f"Wrote {OUT_JSON}")
    print(f"Total inputs in draft: {len(draft)}")
    print(f"  high   : {by_conf['high']}")
    print(f"  medium : {by_conf['medium']}")
    print(f"  low    : {by_conf['low']}")

    # Show 10 low-confidence samples
    print("\n=== Low-confidence samples (need manual review) ===")
    for ra, r in draft.items():
        if r["confidence"] != "low": continue
        print(f"  {r['side']} {r['input-type']:6s} {r['input-id']:>4s} {r['mode']:20s}  ", end="")
        print(f"vjoy={r['vjoy_targets'][:2]} sc={r['sc_actions'][:2]}")
        print(f"     proposed: {r['proposed_label']}")


if __name__ == "__main__":
    main()
