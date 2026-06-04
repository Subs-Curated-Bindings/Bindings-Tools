#!/usr/bin/env python3
"""
parse_binds_v2.py — Star Citizen keybind extractor (SubliminalsTV).

A strict SUPERSET of splitradius's parse_binds.py: the original 12 columns are
preserved byte-for-byte in name/order/semantics, then behavioral columns are
appended. Two real defects in the v1 script are fixed (see CHANGES below).

Inputs:
  defaultProfile.xml  (unforged / de-CryXML'd)
  global.ini          (English localization; .gz accepted transparently)

Outputs (same folder as --out by default):
  <out>.csv              every action, full superset schema
  <out>_axes_only.csv    same schema, axis-type actions only

CHANGES vs v1 (all grounded in the actual defaultProfile.xml):
  1. Activation semantics RESOLVED, not just copied. The profile's
     <ActivationModes> table is parsed; each action's behavior is resolved from
     (a) its activationMode= reference, else (b) inline onPress/onHold/onRelease
     flags, else (c) CIG default (press). 72 actions in 4.8.1 use inline flags
     with NO activationMode — v1 left those blank and lost their hold-ness.
     New cols: OnPress, OnHold, OnRelease, MultiTap, IsHold, IsTap, IsDoubleTap,
     ActivationSource.
  2. Per-action Category= attribute captured (v1 only had actionmap UICategory).
     New col: Category.
  3. MULTI-BINDING FIX. Nested <gamepad><inputdata input=".."/></gamepad> bindings
     were silently dropped by v1 (it read .get("input") on the container, which is
     None). Now collected. Primary value still lands in the device column for
     12-col parity; overflow goes to new col ExtraBindings.
  4. The natural key is (ActionMap, XMLActionName) — names repeat across
     actionmaps (78 collisions in 4.8.1). Rows stay 1-per-(map,action); callers
     should key on the pair, not the name alone.
  5. Actions defined outside any <actionmap> are counted and reported (v1 silently
     dropped them: 1103 <action> elements vs 1100 rows).

Build version is intentionally NOT a per-row column — that would make every row
"change" every patch and drown the diff. It belongs in the sidecar manifest.json.
"""

from __future__ import annotations

import csv
import gzip
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------- #
# localization
# --------------------------------------------------------------------------- #

def load_localization(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    table = {}
    with opener(path, "rt", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith((";", "#")) or "=" not in line:
                continue
            key, _, value = line.partition("=")
            table[key.strip()] = value
    return table


def resolve_label(raw, table: dict) -> str:
    if not raw:
        return ""
    if raw.startswith("@"):
        key = raw[1:]
        if key in table:
            return table[key]
        base = key.split(",", 1)[0]
        return table.get(base, key)
    return raw

# --------------------------------------------------------------------------- #
# activation-mode table  (the semantic source v1 ignored)
# --------------------------------------------------------------------------- #

def load_activation_modes(root: ET.Element) -> dict:
    modes = {}
    for am in root.findall(".//ActivationModes/ActivationMode"):
        name = am.get("name", "")
        if not name:
            continue
        modes[name] = {
            "onPress": am.get("onPress", "0") == "1",
            "onHold": am.get("onHold", "0") == "1",
            "onRelease": am.get("onRelease", "0") == "1",
            "multiTap": int(am.get("multiTap", "1") or "1"),
        }
    return modes


def _as_bool_attr(v):
    """Inline onPress/onHold/onRelease attr -> bool or None if absent."""
    if v is None:
        return None
    return v == "1"


def resolve_activation(action: ET.Element, modes: dict) -> dict:
    am = action.get("activationMode")
    ip, ih, ir = (_as_bool_attr(action.get(k)) for k in ("onPress", "onHold", "onRelease"))
    imt = action.get("multiTap")

    if am and am in modes:
        m = modes[am]
        onP, onH, onR, mt = m["onPress"], m["onHold"], m["onRelease"], m["multiTap"]
        # inline flags, if present, override individual fields
        if ip is not None: onP = ip
        if ih is not None: onH = ih
        if ir is not None: onR = ir
        if imt is not None: mt = int(imt or "1")
        src = "mode"
    elif any(x is not None for x in (ip, ih, ir)) or imt is not None:
        onP = bool(ip); onH = bool(ih); onR = bool(ir); mt = int(imt or "1")
        src = "inline"
    else:
        onP, onH, onR, mt = True, False, False, 1  # CIG default: fire on press
        src = "default"

    is_hold = bool(onH) or (am is not None and "hold" in am.lower()) or (ih is True)
    is_tap = bool(am and am.lower().startswith("tap"))
    is_double = mt >= 2
    return {
        "ActivationMode": am or "",
        "OnPress": int(onP), "OnHold": int(onH), "OnRelease": int(onR),
        "MultiTap": mt,
        "IsHold": int(is_hold), "IsTap": int(is_tap), "IsDoubleTap": int(is_double),
        "ActivationSource": src,
    }

# --------------------------------------------------------------------------- #
# binding extraction  (multi-binding aware — fixes v1 inputdata drop)
# --------------------------------------------------------------------------- #

def collect_bindings(action: ET.Element, device: str) -> list:
    """All bindings for a device: the direct attr + any nested
    <device>[/<inputdata>] children. Space-only placeholders -> dropped.
    Order preserved, de-duped."""
    vals = []
    attr = action.get(device)
    if attr and attr.strip():
        vals.append(attr.strip())
    for child in action:
        if child.tag.lower() != device:
            continue
        if child.get("input") and child.get("input").strip():
            vals.append(child.get("input").strip())
        for gc in child:  # <inputdata input="..."/>
            iv = gc.get("input")
            if iv and iv.strip():
                vals.append(iv.strip())
    seen, out = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v); out.append(v)
    return out

# --------------------------------------------------------------------------- #
# axis detection  (unchanged heuristic from v1, applied to collected values)
# --------------------------------------------------------------------------- #

_GAMEPAD_AXIS = {"thumblx", "thumbly", "thumbrx", "thumbry", "triggerl", "triggerr"}
_JOY_AXIS = {"x", "y", "z", "rx", "ry", "rz", "rotx", "roty", "rotz",
             "throttle", "slider", "slider1", "slider2", "u", "v"}
_MOUSE_AXIS = re.compile(r"^(maxis_|mouse_(x|y)$)", re.I)
_JS_AXIS = re.compile(r"^js\d+_(x|y|z|rx|ry|rz|throttle|slider|rotx|roty|rotz)\b", re.I)


def _is_axis(value: str, device: str) -> bool:
    if not value or device == "keyboard":
        return False
    for p in (x for x in re.split(r"\+", value.lower()) if x):
        if device == "mouse" and _MOUSE_AXIS.match(p):
            return True
        if device == "gamepad" and p in _GAMEPAD_AXIS:
            return True
        if device == "joystick" and (p in _JOY_AXIS or _JS_AXIS.match(p)):
            return True
    return False


def classify(bindings_by_device: dict) -> str:
    for device, vals in bindings_by_device.items():
        for v in vals:
            if _is_axis(v, device):
                return "axis"
    return "button"

# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

FIELDS = [
    # --- original 12 (do not reorder/rename) ---
    "ActionMap", "ActionMapLabel", "ActionMapCategory",
    "XMLActionName", "DisplayName", "Description",
    "Type", "ActivationMode", "Keyboard", "Mouse", "Gamepad", "Joystick",
    # --- v2 behavioral superset ---
    "Category",
    "OnPress", "OnHold", "OnRelease", "MultiTap",
    "IsHold", "IsTap", "IsDoubleTap",
    "ExtraBindings", "ActivationSource",
]


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit("usage: parse_binds_v2.py <defaultProfile.xml> <global.ini[.gz]> <out.csv>")
    profile, gini, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_axes = out.with_name(out.stem + "_axes_only.csv")

    print(f"Loading {gini.name} ...")
    loc = load_localization(gini)
    print(f"  {len(loc):,} localization keys")

    print(f"Parsing {profile.name} ...")
    root = ET.parse(profile).getroot()
    modes = load_activation_modes(root)
    print(f"  {len(modes)} activation modes")

    total_actions = len(root.findall(".//action"))
    rows, in_map = [], 0
    for am_el in root.findall(".//actionmap"):
        am_name = am_el.get("name", "")
        am_label = resolve_label(am_el.get("UILabel"), loc)
        am_cat = resolve_label(am_el.get("UICategory"), loc)
        for action in am_el.findall("action"):
            in_map += 1
            binds = {d: collect_bindings(action, d) for d in ("keyboard", "mouse", "gamepad", "joystick")}
            act = resolve_activation(action, modes)
            primary = {d: (binds[d][0] if binds[d] else "") for d in binds}
            extra = [f"{d}={v}" for d in binds for v in binds[d][1:]]
            rows.append({
                "ActionMap": am_name,
                "ActionMapLabel": am_label,
                "ActionMapCategory": am_cat,
                "XMLActionName": action.get("name", ""),
                "DisplayName": resolve_label(action.get("UILabel"), loc),
                "Description": resolve_label(action.get("UIDescription"), loc),
                "Type": classify(binds),
                "ActivationMode": act["ActivationMode"],
                "Keyboard": primary["keyboard"], "Mouse": primary["mouse"],
                "Gamepad": primary["gamepad"], "Joystick": primary["joystick"],
                "Category": action.get("Category", ""),
                "OnPress": act["OnPress"], "OnHold": act["OnHold"], "OnRelease": act["OnRelease"],
                "MultiTap": act["MultiTap"],
                "IsHold": act["IsHold"], "IsTap": act["IsTap"], "IsDoubleTap": act["IsDoubleTap"],
                "ExtraBindings": ";".join(extra),
                "ActivationSource": act["ActivationSource"],
            })

    orphans = total_actions - in_map
    print(f"  {in_map:,} actions in actionmaps  ({orphans} action element(s) outside any actionmap — not exported)")

    def write(path: Path, data: list) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader(); w.writerows(data)

    write(out, rows)
    axes = [r for r in rows if r["Type"] == "axis"]
    write(out_axes, axes)
    print(f"Wrote {out.name} ({len(rows):,} rows) and {out_axes.name} ({len(axes):,} rows).")


if __name__ == "__main__":
    main()
