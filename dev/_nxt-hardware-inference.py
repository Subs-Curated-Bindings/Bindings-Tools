"""
Match each chart bind cluster (id="bind.X[.dir]" in the SVG) to the
hardware button that fires it, by cross-referencing the JG profile
(button -> vJoy slot, per mode) and the layout XML (vJoy slot -> SC action).

Strategy: for each chart cluster, tokenize its text content and score every
hardware button's set of SC actions against it. Highest-scoring button wins.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT"
JG_XML = os.path.join(STICK_DIR, "Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml")
LAYOUT_XML = os.path.join(STICK_DIR, "layout_ENH_NXT_480_LIVE_exported.xml")
SVG_PATH = r"C:\Users\subli\OneDrive\Desktop\nxt-chart-machine-readable.svg"

# Friendly token map: SC action name fragment -> player-speak tokens we expect on the chart.
# Used to expand SC action names so they match chart text more liberally.
ACTION_TOKEN_HINTS = {
    "afterburner": ["afterburner", "burner"],
    "boost": ["boost"],
    "strafe_trim": ["trim", "strafe"],
    "operator_mode_cycle": ["operator", "mode"],
    "master_mode": ["master", "mode", "scm", "nav"],
    "ads_stable_max_zoom": ["precision", "max", "zoom"],
    "ads_toggle": ["precision", "aiming"],
    "flightready": ["flight", "ready"],
    "power_toggle": ["power", "toggle"],
    "power_toggle_shields": ["shields", "power"],
    "autoland": ["auto", "land"],
    "toggle_landing_system": ["landing"],
    "invoke_docking": ["docking"],
    "toggle_docking_mode": ["docking"],
    "power_toggle_thrusters": ["thruster", "power"],
    "toggle_all_doors": ["doors"],
    "power_toggle_weapons": ["weapon", "power"],
    "atc_request": ["request", "landing"],
    "toggle_jump_request": ["jumpgate", "request"],
    "view_cycle_fwd": ["camera", "view"],
    "view_dynamic_zoom": ["dynamic", "zoom"],
    "missile_cinematic": ["missile", "cinematic"],
    "dock_toggle_view": ["dock", "view"],
    "view_look_behind": ["look", "behind"],
    "headtrack": ["head", "tracking", "track"],
    "view_freelook": ["freelook"],
    "weapon_bombing_hud_range": ["bomb", "range"],
    "remote_turret": ["remote", "turret"],
    "weapon_staggered_fire": ["stagger"],
    "ifcs_toggle_gforce_safety": ["gforce", "safety"],
    "ifcs_toggle_esp": ["esp"],
    "turret_esp": ["turret", "esp"],
    "flight_advanced_hud": ["advanced", "hud", "adv.hud"],
    "tractor_beam": ["tractor"],
    "turret_gyromode": ["turret", "gyro"],
    "pl_exit": ["stop", "watch"],
    "weapon_pip_toggle_lead_lag": ["lead", "lag", "pip"],
    "salvage_reset_gimbal": ["recenter", "turret"],
    "salvage_toggle_gimbal_mode": ["gimbal"],
    "turret_recenter": ["recenter"],
    "weapon_gimbals_state_toggle": ["gimbal"],
    "invoke_ping": ["scan", "ping"],
    "space_brake": ["brake", "scan", "ping"],
    "eva_brake": ["brake"],
    "vehicle_driver_brake": ["brake"],
    "scan_focus_level": ["scanning", "angle"],
    "mining_throttle": ["mining", "throttle"],
    "close_all_doors": ["close", "doors"],
    "open_all_doors": ["open", "doors"],
    "atc_loading_area_request": ["cargo", "request"],
    "transform_cycle": ["cycle", "config", "vtol"],
    "turret_change_position": ["turret", "position"],
    "toggle_mining_mode": ["mining"],
    "toggle_salvage_mode": ["salvage"],
    "toggle_qdrive_engagement": ["light", "amplification", "scan", "ping"],
    "scanning_trigger_scan": ["scan", "ping"],
    "toggle_mining_laser_fire": ["mining", "laser", "fire"],
    "salvage_toggle_fire_focused": ["salvage", "fire"],
    "weapon_preset_attack": ["fire", "weapon", "group"],
    "weapon_toggle_launch_missile": ["fire", "missile"],
    "weapon_preset_fire_guns0": ["fire", "guns"],
    "mfd_quick_action_repair_all": ["self", "repair"],
    "weapon_bombing_toggle_desired_impact_point": ["impact"],
    "ifcs_vector_decoupling": ["decoupled"],
    "chat": ["chat"],
    "foip_pushtotalk": ["voip", "ptt"],
    "foip_viewownplayer": ["voip", "ptt"],
    "target_hail": ["hail"],
    "notification_accept": ["chat"],
    "salvage_toggle_fire_fracture": ["fracture"],
    "weapon_increase_max_missiles": ["missile", "count"],
    "salvage_cycle_modifiers_right": ["right", "modifier"],
    "salvage_toggle_fire_right": ["right", "tool"],
    "weapon_cycle_missile_fwd": ["missile", "next"],
    "salvage_cycle_modifiers_structural": ["structural"],
    "salvage_toggle_fire_disintegrate": ["disintegrate"],
    "weapon_decrease_max_missiles": ["missile", "count"],
    "salvage_cycle_modifiers_left": ["left", "modifier"],
    "salvage_toggle_fire_left": ["left", "tool"],
    "weapon_cycle_missile_back": ["missile", "previous"],
    "toggle_mining_laser_type": ["fracture", "extraction"],
    "salvage_toggle_beam_spacing_axis": ["beam", "spacing", "axis"],
    "weapon_reset_max_missiles": ["reset", "missile"],
    "target_cycle_attacker": ["attacker"],
    "target_cycle_all_fwd": ["all", "target", "forward"],
    "target_cycle_hostile_fwd": ["hostile", "forward"],
    "target_cycle_subitem_fwd": ["sub", "target", "forward"],
    "target_cycle_all_reset": ["target", "reset", "closest"],
    "target_cycle_hostile_reset": ["hostile", "closest", "reset"],
    "target_cycle_subitem_reset": ["sub", "target", "reset"],
    "target_cycle_all_back": ["target", "backward", "previous"],
    "target_cycle_hostile_back": ["hostile", "backward"],
    "target_cycle_subitem_back": ["sub", "target", "backward"],
    "target_lock_selected": ["target", "lock"],
    "target_unlock": ["unlock"],
    "target_under_reticle": ["under", "reticle"],
    "target_pin_selected": ["pin", "target"],
    "target_unpin_selected_hold": ["unpin"],
    "mining_use_consumable1": ["mining", "module"],
    "salvage_focus_fracture": ["focus", "fracture"],
    "shield_raise_level_forward": ["shields"],
    "mfd_movement_up": ["mfd", "up"],
    "mining_use_consumable2": ["mining", "module"],
    "salvage_focus_right": ["focus", "right"],
    "shield_raise_level_right": ["shields", "right"],
    "mfd_interact_cycle_forwards": ["mfd"],
    "mfd_movement_right": ["mfd", "right"],
    "mfd_soft_select_cast_right": ["right", "cast"],
    "salvage_focus_disintegrate": ["focus", "disintegration"],
    "shield_raise_level_back": ["shields", "aft"],
    "mfd_movement_down": ["mfd", "down"],
    "mining_use_consumable3": ["mining", "module"],
    "salvage_focus_left": ["focus", "left"],
    "shield_raise_level_left": ["shields", "left"],
    "mfd_interact_cycle_backwards": ["mfd"],
    "mfd_movement_left": ["mfd", "left"],
    "mfd_soft_select_cast_left": ["left", "cast"],
    "salvage_focus_all_heads": ["focus", "all"],
    "shield_reset_level": ["shields", "reset"],
    "weapon_countermeasure_decoy_launch": ["decoy"],
    "weapon_preset_emp": ["next", "weapon"],
    "weapon_preset_next": ["next", "weapon"],
    "weapon_preset_qid": ["next", "weapon"],
    "weapon_countermeasure_noise_launch": ["multi", "decoy"],
    "weapon_preset_prev": ["weapon", "previous"],
    "salvage_increase_beam_spacing": ["salvage", "beam", "inc"],
    "salvage_decrease_beam_spacing": ["salvage", "beam", "dec"],
    "decoy_burst_increase": ["decoy", "burst", "inc"],
    "decoy_burst_decrease": ["decoy", "burst", "dec"],
    "lights": ["lights"],
    "light_amplification": ["light", "amplification"],
    "emergency_exit": ["exit", "seat", "quick"],
    "turret_remote_exit": ["exit", "turret"],
    "eject": ["eject"],
    "toggle_all_portlocks": ["port", "lock"],
    "toggle_all_doorlocks": ["doors", "lock"],
}


def jg_walk_actions(jg_root):
    return {a.attrib["id"]: a for a in jg_root.findall("./library/action")}


def jg_collect_vjoy_targets(action, by_id, visited=None):
    if visited is None:
        visited = set()
    aid = action.attrib.get("id")
    if aid in visited:
        return []
    visited.add(aid)
    out = []
    atype = action.attrib.get("type", "")
    if atype == "map-to-vjoy":
        props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
        if props.get("vjoy-input-type") == "button":
            try:
                out.append((int(props.get("vjoy-device-id", "0")), int(props.get("vjoy-input-id", "0"))))
            except ValueError:
                pass
    for el in action.iter():
        if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
            out.extend(jg_collect_vjoy_targets(by_id[el.text], by_id, visited))
    return out


def parse_jg(jg_path):
    tree = ET.parse(jg_path)
    root = tree.getroot()
    by_id = jg_walk_actions(root)

    # (device-id, button-index) -> {mode -> set((vjoy_dev, vjoy_btn))}
    hw_per_mode = defaultdict(lambda: defaultdict(set))
    for inp in root.findall("./inputs/input"):
        if inp.findtext("input-type", "") != "button":
            continue
        did = inp.findtext("device-id", "")
        try:
            iid = int(inp.findtext("input-id", "0"))
        except ValueError:
            continue
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            root_id = ac.findtext("root-action", "")
            if root_id in by_id:
                vjoys = jg_collect_vjoy_targets(by_id[root_id], by_id)
                for v in vjoys:
                    hw_per_mode[(did, iid)][mode].add(v)
    return hw_per_mode


def parse_layout(layout_path):
    root = ET.parse(layout_path).getroot()
    vjoy_to_actions = defaultdict(list)
    for am in root.findall("./actionmap"):
        amname = am.attrib.get("name", "")
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    vjoy_to_actions[(int(m.group(1)), int(m.group(2)))].append((amname, aname))
    return vjoy_to_actions


def parse_svg_clusters(svg_path):
    """Walk SVG with ET; extract text content scoped to each id="bind.X"/"label.X" element."""
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


def action_tokens(action_name):
    """Return tokens for an SC action name, using ACTION_TOKEN_HINTS for player-speak expansion."""
    # Strip v_/p_/eva_ prefix
    n = re.sub(r"^[a-z]_", "", action_name).lower()
    # Direct token hint match
    hints = []
    for key, toks in ACTION_TOKEN_HINTS.items():
        if key in n:
            hints.extend(toks)
    # Plus the action's own word fragments
    parts = re.split(r"[_]+", n)
    return set(hints + parts)


def chart_tokens(text):
    """Tokenize chart text."""
    t = text.lower()
    # Strip mode prefixes for scoring (so [M][H][DT] don't dilute)
    t = re.sub(r"\[[A-Z]+\]", " ", t)
    tokens = re.findall(r"[a-z0-9]+", t)
    stop = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "off", "with"}
    return set(tok for tok in tokens if tok not in stop and len(tok) >= 2)


def main():
    hw_per_mode = parse_jg(JG_XML)
    vjoy_to_actions = parse_layout(LAYOUT_XML)
    clusters = parse_svg_clusters(SVG_PATH)

    binds = {k: v for k, v in clusters.items() if k.startswith("bind.")}

    # Build hw_summary: (did, iid) -> {sc_action_names across all modes}
    hw_actions = defaultdict(set)
    hw_vjoys = defaultdict(set)
    for (did, iid), mode_map in hw_per_mode.items():
        for mode, vjoys in mode_map.items():
            for v in vjoys:
                hw_vjoys[(did, iid)].add(v)
                for am, an in vjoy_to_actions.get(v, []):
                    hw_actions[(did, iid)].add(an)

    # Side identification: device with more buttons in low range is one side.
    # The chart says device 7d12d5c0... = LEFT, ec8bbeb0... = RIGHT — we'll verify
    devices_used = sorted({did for (did, iid) in hw_actions.keys()})
    print("Devices found:", devices_used)

    # Score each chart cluster against each hardware button
    results = []
    for cluster_id, text in sorted(binds.items()):
        cl_tokens = chart_tokens(text)
        if not cl_tokens:
            results.append((cluster_id, text, None, 0, []))
            continue
        # Determine expected side from cluster_id (L-* / R-* / MAIN-TRIG-L / etc.)
        side = None
        if ".L-" in "."+cluster_id or cluster_id.startswith("bind.L-") or "TRIG-L" in cluster_id:
            side = "L"
        elif ".R-" in "."+cluster_id or cluster_id.startswith("bind.R-") or "TRIG-R" in cluster_id:
            side = "R"

        scores = []
        for (did, iid), action_set in hw_actions.items():
            # Bias by side (left device vs right device)
            device_idx = devices_used.index(did)
            this_side = "L" if device_idx == 0 else "R"
            if side and side != this_side:
                continue
            tok_union = set()
            for an in action_set:
                tok_union.update(action_tokens(an))
            score = len(cl_tokens & tok_union)
            scores.append((score, did, iid, sorted(action_set)))
        scores.sort(reverse=True)
        best = scores[0] if scores else None
        results.append((cluster_id, text, best, best[0] if best else 0, scores[:3]))

    # Output
    print("\n=== Cluster → best-guess hardware button ===\n")
    for cluster_id, text, best, score, top3 in results:
        if not best:
            print(f"  {cluster_id:30s} NO MATCH   text={text[:60]!r}")
            continue
        _, did, iid, _ = best
        did_short = did[:8]
        runners = ", ".join(f"btn{t[2]}({t[0]})" for t in top3[1:3])
        print(f"  {cluster_id:30s} → {did_short}.. btn {iid:3d} (score {score:2d})  text={text[:55]!r}")
        if runners:
            print(f"  {'':32s}   alternates: {runners}")


if __name__ == "__main__":
    main()
