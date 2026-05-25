"""
Build comprehensive description-action JSON for the Gunfighter.

Strategy:
  1. Walk every JG input, gather its vJoy targets + SC actions (from layout).
  2. For each input, decide the etched-name by signature: hat input → R-A1 or L-A1,
     a button → the cluster whose distinguishing SC actions match.
  3. Use full chart text (from the SVG, current as of May 22 09:00) as the body.
  4. Emit JSON keyed by input-key = "<device>|<input-type>|<input-id>|<mode>".

The output replaces tools/_gf-descriptions.json. Apply with _gf-apply-descriptions.py.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = Path(
    r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds"
)
JG_PATH = STICK_DIR / "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR / "layout_ENH_GF_480_LIVE_exported.xml"
SVG_PATH = STICK_DIR / "Binding Charts" / "Binding Chart [ENH][GF][4.8.0][LIVE].svg"
OUT_PATH = Path(
    r"E:\06. Dev Projects\Subs-Curated-Bindings\tools\_gf-descriptions.json"
)


# ---------- 1. SC action → chart cluster signature ----------
# Each SC action name (or partial prefix) maps to ONE chart cluster's etched-name.
# Built from the current chart text + JG/layout cross-reference (see _gf-recon-missing.py).
SC_ACTION_TO_CLUSTER = {
    # MAIN-TRIG-R stages
    "v_toggle_qdrive_engagement": "MAIN-TRIG-R.stage-1",
    "v_scanning_trigger_scan": "MAIN-TRIG-R.stage-1",
    "v_toggle_mining_laser_fire": "MAIN-TRIG-R.stage-1",
    "v_salvage_toggle_fire_focused": "MAIN-TRIG-R.stage-1",
    "v_weapon_preset_attack": "MAIN-TRIG-R.stage-1",
    "v_weapon_preset_fire_guns1": "MAIN-TRIG-R.stage-1",
    "v_weapon_toggle_launch_missile": "MAIN-TRIG-R.stage-1",
    "v_weapon_preset_fire_guns2": "MAIN-TRIG-R.stage-2",

    # R-A2 / L-A2 (Master Mode / Operator Mode cycle) — both sticks share these SC actions
    # Treated as side-dependent in DUAL_SIDE_ACTIONS below; default here is R-A2 for
    # the cluster-device check, then overridden during assignment for left-side inputs.
    "v_operator_mode_cycle_forward": "DUAL_SIDE",
    "v_master_mode_set_scm": "DUAL_SIDE",
    "v_master_mode_set_nav": "DUAL_SIDE",
    "v_horn": "DUAL_SIDE",
    "v_weapon_bombing_toggle_desired_impact_point": "DUAL_SIDE",
    "v_toggle_mining_mode": "DUAL_SIDE",
    "v_toggle_salvage_mode": "DUAL_SIDE",

    # R-A1B
    "v_ifcs_vector_decoupling_toggle": "R-A1B",

    # R-D1 (VOIP / Notifications / Chat)
    "foip_pushtotalk_proximity": "R-D1",
    "foip_pushtotalk": "R-D1",
    "v_target_hail": "R-D1",
    "notification_accept": "R-D1",
    "notification_decline": "R-D1",
    "toggle_chat": "R-D1",

    # R-A4 cluster (Capacitor management)
    "v_engineering_assignment_shields_increase": "R-A4.right",
    "v_engineering_assignment_shields_decrease": "R-A4.right",
    "v_engineering_assignment_shields_max": "R-A4.right",
    "v_engineering_assignment_shields_min": "R-A4.right",
    "v_engineering_assignment_engine_increase": "R-A4.down",
    "v_engineering_assignment_engine_decrease": "R-A4.down",
    "v_engineering_assignment_engine_max": "R-A4.down",
    "v_engineering_assignment_engine_min": "R-A4.down",
    "v_engineering_assignment_weapons_increase": "R-A4.left",
    "v_engineering_assignment_weapons_decrease": "R-A4.left",
    "v_engineering_assignment_weapons_max": "R-A4.left",
    "v_engineering_assignment_weapons_min": "R-A4.left",
    "v_engineering_assignment_reset": "R-A4.press-in",

    # R-A3 hat (Sub Target / Salvage / Mining Throttle / Missile)
    "v_increase_mining_throttle": "R-A3.up",
    "v_salvage_toggle_fire_fracture": "R-A3.up",
    "v_weapon_increase_max_missiles": "R-A3.up",
    "v_decrease_mining_throttle": "R-A3.down",
    "v_weapon_decrease_max_missiles": "R-A3.down",
    "v_salvage_toggle_fire_disintegrate": "R-A3.down",
    "v_salvage_cycle_modifiers_structural": "R-A3.down",
    "v_target_cycle_subitem_reset": "R-A3.down",
    "v_target_cycle_subitem_back": "R-A3.left",
    "v_salvage_cycle_modifiers_left": "R-A3.left",
    "v_salvage_toggle_fire_left": "R-A3.left",
    "v_weapon_cycle_missile_back": "R-A3.left",
    "v_target_cycle_subitem_fwd": "R-A3.right",
    "v_salvage_cycle_modifiers_right": "R-A3.right",
    "v_salvage_toggle_fire_right": "R-A3.right",
    "v_weapon_cycle_missile_fwd": "R-A3.right",
    "v_toggle_mining_laser_type": "R-A3.press-in",
    "v_salvage_toggle_beam_spacing_axis": "R-A3.press-in",
    "v_weapon_reset_max_missiles": "R-A3.press-in",

    # R-C1 (Shields / Mining Modules / Salvage Focus)
    "v_mining_use_consumable1": "R-C1.up",
    "v_salvage_focus_fracture": "R-C1.up",
    "v_shield_raise_level_forward": "R-C1.up",
    "v_mining_use_consumable2": "R-C1.right",
    "v_salvage_focus_right": "R-C1.right",
    "v_shield_raise_level_right": "R-C1.right",
    "v_salvage_focus_disintegrate": "R-C1.down",
    "v_shield_raise_level_back": "R-C1.down",
    "v_mining_use_consumable3": "R-C1.left",
    "v_salvage_focus_left": "R-C1.left",
    "v_shield_raise_level_left": "R-C1.left",
    "v_shield_reset_level": "R-C1.press-in",
    "v_salvage_focus_all": "R-C1.press-in",

    # RAPID-TRIG-R
    "v_weapon_countermeasure_decoy_launch": "RAPID-TRIG-R",
    "v_weapon_countermeasure_noise_launch": "RAPID-TRIG-R",
    "v_weapon_preset_next_overflow": "RAPID-TRIG-R",
    "v_weapon_preset_prev_overflow": "RAPID-TRIG-R",

    # LEFT STICK
    # MAIN-TRIG-L
    "v_afterburner": "MAIN-TRIG-L",
    "turret_toggle_mouse_mode": "MAIN-TRIG-L",

    # RAPID-TRIG-L
    "v_invoke_ping": "RAPID-TRIG-L",
    "v_space_brake": "RAPID-TRIG-L",
    "v_brake": "RAPID-TRIG-L",
    "eva_brake": "RAPID-TRIG-L",
    # v_light_amplification_toggle is dual: on RAPID-TRIG-L [H] AND L-A3.up [H] per chart.
    # Vote weighting: assign to L-A3.up (matches more other actions on the same button cluster).
    "v_light_amplification_toggle": "L-A3.up",

    # L-A2 / R-A2 share SC actions — disambiguated by device-side at vote time
    # (see DUAL_SIDE_ACTIONS below)

    # L-A3 hat
    "v_flightready": "L-A3.up",
    "v_lights": "L-A3.up",
    "v_power_toggle": "L-A3.up",

    "v_toggle_all_doors": "L-A3.left",
    "v_toggle_all_doorlocks": "L-A3.left",
    "v_power_toggle_weapons": "L-A3.left",

    "v_autoland": "L-A3.down",
    "v_invoke_docking": "L-A3.down",
    "v_toggle_docking_mode": "L-A3.down",
    "v_toggle_landing_system": "L-A3.down",
    "v_power_toggle_thrusters": "L-A3.down",

    "v_vtol_toggle": "L-A3.right",
    "turret_change_position": "L-A3.right",
    "v_power_toggle_shields": "L-A3.right",

    "v_atc_request": "L-A3.press-in",
    "v_toggle_jump_request": "L-A3.press-in",
    "v_atc_loading_area_request": "L-A3.press-in",

    # L-A4 hat (Camera / Scan / Tractor / Head Track / Freelook)
    "v_inc_scan_focus_level": "L-A4.up",
    "tractor_beam_vehicle_increase_distance": "L-A4.up",
    "v_salvage_increase_beam_spacing": "L-A4.up",
    "v_salvage_decrease_beam_spacing": "L-A4.up",
    "v_weapon_bombing_hud_range_increase": "L-A4.up",
    "v_weapon_countermeasure_decoy_burst_increase": "L-A4.up",

    "v_dec_scan_focus_level": "L-A4.down",
    "tractor_beam_vehicle_decrease_distance": "L-A4.down",
    "v_weapon_bombing_hud_range_decrease": "L-A4.down",
    "v_weapon_countermeasure_decoy_burst_decrease": "L-A4.down",
    "v_view_look_behind": "L-A4.down",

    "headtrack_enabled": "L-A4.left",
    "headtrack_camera_enabled": "L-A4.left",
    "headtrack_recenter_device": "L-A4.left",

    "v_view_dynamic_zoom_abs_toggle": "L-A4.right",
    "v_weapon_launch_missile_cinematic_hold": "L-A4.right",
    "v_dock_toggle_view": "L-A4.right",

    "v_view_cycle_fwd": "L-A4.up",  # Camera (3rd Person) SCM-mode cycle
    "v_view_freelook_mode": "L-A4.press-in",
    "eva_toggle_headlook_mode": "L-A4.press-in",
    "view_restore_defaults": "L-A4.press-in",
    "v_weapon_bombing_hud_range_reset": "L-A4.press-in",

    # L-C1
    "v_weapon_staggered_fire_toggle": "L-C1.up",
    "v_enter_remote_turret_1": "L-C1.up",
    "v_ifcs_toggle_gforce_safety": "L-C1.up",
    "turret_gyromode": "L-C1.down",
    "stopwatch_reset": "L-C1.down",
    "stopwatch_trigger": "L-C1.down",
    "v_seat_exit": "L-C1.down",
    "tractor_beam_increase_distance": "L-C1.down",
    "v_target_toggle_lead_pip": "L-C1.left",
    "v_enter_remote_turret_2": "L-C1.left",
    "v_ifcs_toggle_esp": "L-C1.right",
    "turret_esp_toggle": "L-C1.right",
    "v_enter_remote_turret_3": "L-C1.right",
    "v_flight_advanced_hud_toggle": "L-C1.right",
    "v_weapon_gimbals_state_toggle": "L-C1.press-in",
    "turret_recenter": "L-C1.press-in",
    "v_salvage_toggle_gimbal_mode": "L-C1.press-in",
    "v_salvage_reset_gimbal": "L-C1.press-in",

    # L-A1B
    "v_ads_hold": "L-A1B",
    "v_ads_toggle": "L-A1B",

    # L-A1 hat (covered by hat input — these for trim-related auxiliary buttons)
    "v_strafe_trim_set_short": "L-A1",
    "v_strafe_trim_set_100_long": "L-A1",
    "v_strafe_trim_reset_short": "L-A1",
    "v_strafe_trim_reset_long": "L-A1",
    "v_ifcs_speed_limiter_up": "L-A1",
    "v_ifcs_speed_limiter_down": "L-A1",
    "v_ifcs_throttle_swap_mode": "L-A1",
    "v_accel_range_up": "L-A1",
    "v_accel_range_down": "L-A1",
}

# Chart cluster → primary device-id (so we disambiguate v_master_mode_set_scm etc.
# between left and right A2 buttons).
CLUSTER_DEVICE = {
    "L-A1": "0dcdeb30",
    "L-A1B": "0dcdeb30",
    "L-A2": "0dcdeb30",
    "L-A3.up": "0dcdeb30",
    "L-A3.down": "0dcdeb30",
    "L-A3.left": "0dcdeb30",
    "L-A3.right": "0dcdeb30",
    "L-A3.press-in": "0dcdeb30",
    "L-A4.up": "0dcdeb30",
    "L-A4.down": "0dcdeb30",
    "L-A4.left": "0dcdeb30",
    "L-A4.right": "0dcdeb30",
    "L-A4.press-in": "0dcdeb30",
    "L-C1.up": "0dcdeb30",
    "L-C1.down": "0dcdeb30",
    "L-C1.left": "0dcdeb30",
    "L-C1.right": "0dcdeb30",
    "L-C1.press-in": "0dcdeb30",
    "L-D1": "0dcdeb30",
    "MAIN-TRIG-L": "0dcdeb30",
    "RAPID-TRIG-L": "0dcdeb30",
    "R-A1": "0dcd7600",
    "R-A1B": "0dcd7600",
    "R-A2": "0dcd7600",
    "R-A3.up": "0dcd7600",
    "R-A3.down": "0dcd7600",
    "R-A3.left": "0dcd7600",
    "R-A3.right": "0dcd7600",
    "R-A3.press-in": "0dcd7600",
    "R-A4.up": "0dcd7600",
    "R-A4.down": "0dcd7600",
    "R-A4.left": "0dcd7600",
    "R-A4.right": "0dcd7600",
    "R-A4.press-in": "0dcd7600",
    "R-C1.up": "0dcd7600",
    "R-C1.down": "0dcd7600",
    "R-C1.left": "0dcd7600",
    "R-C1.right": "0dcd7600",
    "R-C1.press-in": "0dcd7600",
    "R-D1": "0dcd7600",
    "MAIN-TRIG-R.stage-1": "0dcd7600",
    "MAIN-TRIG-R.stage-2": "0dcd7600",
    "RAPID-TRIG-R": "0dcd7600",
    "L-A2": "0dcdeb30",
}


def parse_chart():
    """Return {etched -> chart text}."""
    tree = ET.parse(SVG_PATH)
    root = tree.getroot()
    serif_ns = "{http://www.serif.com/}id"
    clusters = {}
    for elem in root.iter():
        eid = elem.attrib.get("id", "")
        serif_id = elem.attrib.get(serif_ns, "")
        canonical = serif_id or eid
        if not canonical.startswith("bind."):
            continue
        etched = canonical[len("bind."):]
        parts = []
        for t in elem.iter():
            tag = t.tag.split("}", 1)[-1]
            if tag in ("text", "tspan") and t.text:
                parts.append(t.text)
        text = " ".join(" ".join(parts).split())
        # Fix Affinity's ﬁ / ﬂ ligatures so SC's plaintext chart text reads naturally.
        text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
        if text:
            clusters[etched] = text
    return clusters


def parse_layout():
    tree = ET.parse(LAYOUT_PATH)
    root = tree.getroot()
    bm = defaultdict(list)
    hat_m = defaultdict(list)
    for am in root.findall("./actionmap"):
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    bm[(int(m.group(1)), int(m.group(2)))].append(aname)
                    continue
                m = re.match(r"js(\d+)_hat(\d+)_(up|down|left|right)$", inp)
                if m:
                    hat_m[(int(m.group(1)), int(m.group(2)), m.group(3))].append(aname)
    return bm, hat_m


def parse_jg():
    """Return list of (device_id, input_type, input_id, mode, vjoy_targets, sc_actions)."""
    bm, hat_m = parse_layout()
    tree = ET.parse(JG_PATH)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    def collect_vjoy(action, visited=None):
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
                    props.get("vjoy-input-type", ""),
                    int(props.get("vjoy-input-id", "0")),
                ))
            except ValueError:
                pass
        for el in action.iter():
            if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
                out.extend(collect_vjoy(by_id[el.text], visited))
        return out

    records = []
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action", "")
            if rid not in by_id:
                continue
            vjoy = collect_vjoy(by_id[rid])
            sc = []
            for dev, vt, vid in vjoy:
                if vt == "button":
                    sc.extend(bm.get((dev, vid), []))
                elif vt == "hat":
                    for d in ("up", "down", "left", "right"):
                        sc.extend(hat_m.get((dev, vid, d), []))
            records.append({
                "device_id": did,
                "input_type": itype,
                "input_id": iid,
                "mode": mode,
                "vjoy": vjoy,
                "sc_actions": sc,
            })
    return records


def assign_etched(rec, clusters):
    """Pick the etched-name for a JG input based on its SC action signature."""
    sc = rec["sc_actions"]
    dev_short = (rec["device_id"] or "")[:8]
    itype = rec["input_type"]

    # Hat inputs are always aggregate descriptions for L-A1 or R-A1.
    if itype == "hat":
        if dev_short == "0dcd7600":  # right
            return "R-A1"
        elif dev_short == "0dcdeb30":  # left
            return "L-A1"
        return None

    # VKB virtual/shifted button slots (high logical button numbers).
    # These appear in the JG profile as JG-listens-for-input records but they're
    # alternate-mode emits of the same physical button — describing them would
    # duplicate the physical button's chart cluster.
    try:
        if int(rec["input_id"]) >= 100:
            return None
    except (ValueError, TypeError):
        pass

    # Empty SC list → no layout binding → no description needed.
    if not sc:
        return None

    # Vote across SC actions; pick the most-voted cluster filtered by device side.
    votes = defaultdict(int)
    for action in sc:
        cluster = SC_ACTION_TO_CLUSTER.get(action)
        if not cluster:
            continue
        if cluster == "DUAL_SIDE":
            # L-A2 vs R-A2 based on physical device side.
            if dev_short == "0dcdeb30":
                cluster = "L-A2"
            elif dev_short == "0dcd7600":
                cluster = "R-A2"
            else:
                continue
        # Filter by device-side: cluster must match this input's device side.
        expected_dev = CLUSTER_DEVICE.get(cluster)
        if expected_dev and expected_dev != dev_short:
            continue
        votes[cluster] += 1

    if not votes:
        return None
    best = sorted(votes.items(), key=lambda x: (-x[1], x[0]))[0]
    return best[0]


def _split_trigger_text(text):
    """Partition a RAPID-TRIG chart text into (trigger-up half, trigger-down half).

    Chart text format: 'Trigger Up <stuff> Trigger Down <more stuff>'.
    Returns ('<stuff after Up, before Down>', '<stuff after Down>').
    If markers aren't found, returns (whole text, whole text).
    """
    import re as _re
    up_marker = _re.search(r"Trigger Up\s+", text, _re.IGNORECASE)
    down_marker = _re.search(r"Trigger Down\s+", text, _re.IGNORECASE)
    if up_marker and down_marker and down_marker.start() > up_marker.end():
        up_part = text[up_marker.end():down_marker.start()].strip()
        down_part = text[down_marker.end():].strip()
        return up_part, down_part
    return text, text


def aggregate_hat_body(side, clusters):
    """Return the aggregate description body for an L-A1 or R-A1 hat."""
    prefix = side  # "L-A1" or "R-A1"
    dirs = []
    for d in ("up", "down", "left", "right", "press-in"):
        key = f"{prefix}.{d}"
        if key in clusters:
            text = clusters[key]
            dirs.append(f"{d}={text}")
    return " | ".join(dirs)


def main():
    clusters = parse_chart()
    records = parse_jg()

    assignments = {}
    skipped_by_reason = defaultdict(list)

    for rec in records:
        # Aux/Nav modes for L-A2 / R-A2 only; otherwise restrict to SCM and Modifier.
        mode = rec["mode"]
        if mode not in ("SCM Mode", "Modifier", "Auxiliary Mode", "Nav Mode"):
            skipped_by_reason["unhandled_mode"].append(rec)
            continue

        etched = assign_etched(rec, clusters)
        if not etched:
            skipped_by_reason["no_cluster_match"].append(rec)
            continue

        parenthetical = ""
        # Build body
        if rec["input_type"] == "hat":
            side = "L-A1" if etched == "L-A1" else "R-A1"
            body = aggregate_hat_body(side, clusters)
        elif etched in ("RAPID-TRIG-L", "RAPID-TRIG-R"):
            # Split chart text by "Trigger Up" / "Trigger Down" markers; assign
            # button 26 to (Trigger Up) and button 27 to (Trigger Down).
            full = clusters.get(etched, "")
            up_part, down_part = _split_trigger_text(full)
            input_id = rec["input_id"]
            if input_id == "26":
                parenthetical = "Trigger Up"
                body = up_part
            elif input_id == "27":
                parenthetical = "Trigger Down"
                body = down_part
            else:
                body = full
        else:
            body = clusters.get(etched, "")
        if not body:
            skipped_by_reason["no_chart_body"].append(rec)
            continue

        mode_tag = "" if mode == "SCM Mode" else mode

        key = f"{rec['device_id']}|{rec['input_type']}|{rec['input_id']}|{mode}"
        if key in assignments:
            # Multiple action-configurations for the same input — keep the first.
            skipped_by_reason["duplicate_key"].append(rec)
            continue
        entry = {
            "etched": etched,
            "mode_tag": mode_tag,
            "body": body,
            "sc_actions": rec["sc_actions"],
        }
        if parenthetical:
            entry["parenthetical"] = parenthetical
        assignments[key] = entry

    # ---- Manual additions for clusters that auto-derivation can't reach ----
    # L-D1: the Modifier indicator button. Triggers JG mode-change, emits no vjoy.
    # Maps to vJ1 (device 0dcdeb30) button 5 — confirmed via JG profile change-mode action chain.
    LEFT_DEVICE = "0dcdeb30-d727-11ef-8013-444553540000"
    for mode in ("SCM Mode", "Modifier"):
        key = f"{LEFT_DEVICE}|button|5|{mode}"
        mode_tag = "" if mode == "SCM Mode" else mode
        assignments[key] = {
            "etched": "L-D1",
            "mode_tag": mode_tag,
            "body": clusters.get("L-D1", "[M] Modifier"),
            "sc_actions": [],
        }

    print(f"Built {len(assignments)} description assignments")
    print()
    print("Skipped:")
    for reason, recs in skipped_by_reason.items():
        print(f"  {reason}: {len(recs)}")
        for r in recs[:5]:
            sc_str = ", ".join(r["sc_actions"][:3]) + ("..." if len(r["sc_actions"]) > 3 else "")
            print(f"    {r['device_id'][:8]} {r['mode']:<16} {r['input_type']:<6} {r['input_id']:<4} sc=[{sc_str}]")
        if len(recs) > 5:
            print(f"    ... +{len(recs) - 5} more")

    OUT_PATH.write_text(json.dumps(assignments, indent=2), encoding="utf-8")
    print()
    print(f"Wrote {OUT_PATH.name} with {len(assignments)} entries.")


if __name__ == "__main__":
    main()
