#!/usr/bin/env python3
"""Convert a Joystick Gremlin R13 (profile version 9) XML profile to R14 (profile version 14).

Schema verified against the JG R14 source (WhiteMagic/JoystickGremlin):
  - action_plugins/change_mode/__init__.py — change-type values & target-mode rules
  - gremlin/macro.py VJoyAction.to_xml — macro vjoy sub-action property order
  - action_plugins/response_curve — see Sub's vault wiki page 04-actions for the
    "must come before Map to vJoy" rule that the converter enforces

Critical invariants:
  - In <library>, primitive actions must be defined before any root/tempo that
    references them by id. JG R14 silently renders the whole profile blank on
    forward-reference. Roots are emitted last per input.
  - In each root's <actions> child list, response-curve action-ids must precede
    map-to-vjoy / map-to-mouse action-ids. R14 evaluates children top-down; a
    curve placed after the mapping shapes already-mapped output (no-op).

Dropped without an R14 equivalent (warned, recorded in the report):
  - text-to-speech (no equivalent action in R14)

Translated where the closest R14 action conveys the original intent:
  - noop -> R14 `description` action (carries a visible text label, no runtime
    effect). Preserves the "intentional placeholder" semantics that some R13
    profiles rely on. The description text incorporates the parent input's
    description attribute when present.

Usage:
    python r13_to_r14.py <input.xml> <output.xml> [--verbose] [--report <path>]

By default the sidecar report is written to `<output_dir>/.Assets/<output_stem>.report.txt`
(the `.Assets/` folder is created if missing). Pass `--report <path>` to override.
Re-running overwrites any existing report at that path.
"""
import argparse
import sys
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import Counter
from pathlib import Path


# ---------- helpers ----------

def gen_uuid() -> str:
    return str(uuid.uuid4())


def normalize_device_id(guid: str) -> str:
    """`{7D12D5C0-...}` -> `7d12d5c0-...`."""
    return guid.strip("{}").lower()


def add_property(parent: ET.Element, ptype: str, name: str, value) -> ET.Element:
    p = ET.SubElement(parent, "property", type=ptype)
    ET.SubElement(p, "name").text = name
    ET.SubElement(p, "value").text = str(value)
    return p


def append_label_and_mode(el: ET.Element, label: str, mode: str = "both") -> None:
    add_property(el, "string", "action-label", label)
    add_property(el, "activation-mode", "activation-mode", mode)


def make_action(atype: str) -> tuple[str, ET.Element]:
    """Build a library action element in memory. Caller appends it to <library>
    in the right order."""
    aid = gen_uuid()
    el = ET.Element("action", id=aid, type=atype)
    return aid, el


# ---------- R13 action -> R14 library action ----------

def convert_remap(remap_el: ET.Element) -> tuple[str, ET.Element]:
    aid, el = make_action("map-to-vjoy")
    add_property(el, "int", "vjoy-device-id", remap_el.attrib.get("vjoy", "1"))

    if "button" in remap_el.attrib:
        add_property(el, "int", "vjoy-input-id", remap_el.attrib["button"])
        add_property(el, "input_type", "vjoy-input-type", "button")
        add_property(el, "bool", "button-inverted", "False")
    elif "axis" in remap_el.attrib:
        add_property(el, "int", "vjoy-input-id", remap_el.attrib["axis"])
        add_property(el, "input_type", "vjoy-input-type", "axis")
        add_property(el, "axis_mode", "axis-mode", remap_el.attrib.get("axis-type", "absolute"))
        add_property(el, "float", "axis-scaling", remap_el.attrib.get("axis-scaling", "1.0"))
    elif "hat" in remap_el.attrib:
        add_property(el, "int", "vjoy-input-id", remap_el.attrib["hat"])
        add_property(el, "input_type", "vjoy-input-type", "hat")

    append_label_and_mode(el, "Map to vJoy")
    return aid, el


def convert_cycle_modes(cm_el: ET.Element) -> tuple[str, ET.Element]:
    aid, el = make_action("change-mode")
    add_property(el, "string", "change-type", "Cycle")
    for mode_el in cm_el.findall("mode"):
        target = ET.SubElement(el, "target-mode")
        add_property(target, "string", "name", mode_el.attrib.get("name", ""))
    append_label_and_mode(el, "Change Mode")
    return aid, el


def convert_temp_mode_switch(tms_el: ET.Element) -> tuple[str, ET.Element]:
    aid, el = make_action("change-mode")
    add_property(el, "string", "change-type", "Temporary")
    target = ET.SubElement(el, "target-mode")
    add_property(target, "string", "name", tms_el.attrib.get("name", ""))
    append_label_and_mode(el, "Change Mode")
    return aid, el


def convert_switch_mode(sm_el: ET.Element) -> tuple[str, ET.Element]:
    """R13 <switch-mode name="X"/> -> R14 change-mode with change-type=Switch
    and one <target-mode> child. Per JG R14 source action_plugins/change_mode/
    __init__.py: ChangeType.Switch requires exactly one target-mode, identical
    XML shape to Temporary (just a different change-type value)."""
    aid, el = make_action("change-mode")
    add_property(el, "string", "change-type", "Switch")
    target = ET.SubElement(el, "target-mode")
    add_property(target, "string", "name", sm_el.attrib.get("name", ""))
    append_label_and_mode(el, "Change Mode")
    return aid, el


def convert_previous_mode(_pm_el: ET.Element) -> tuple[str, ET.Element]:
    """R13 <previous-mode/> -> R14 change-mode action with change-type=Previous.
    Per JG R14 source (action_plugins/change_mode/__init__.py): Previous swaps
    the top two entries on the mode stack and takes NO target-mode children —
    the underlying target_modes list is intentionally empty for Previous,
    Unwind, and freshly-set Cycle. Emit zero <target-mode> elements."""
    aid, el = make_action("change-mode")
    add_property(el, "string", "change-type", "Previous")
    append_label_and_mode(el, "Change Mode")
    return aid, el


def convert_response_curve(rc_el: ET.Element) -> tuple[str, ET.Element]:
    aid, el = make_action("response-curve")

    dz_in = rc_el.find("deadzone")
    dz_out = ET.SubElement(el, "deadzone")
    defaults = {"low": "-1.0", "center-low": "0.0", "center-high": "0.0", "high": "1.0"}
    for k, default in defaults.items():
        val = dz_in.attrib.get(k, default) if dz_in is not None else default
        add_property(dz_out, "float", k, val)

    cps_out = ET.SubElement(el, "control-points")
    mapping = rc_el.find("mapping")
    if mapping is not None:
        for cp in mapping.findall("control-point"):
            add_property(cps_out, "point2d", "point", f"{cp.attrib['x']},{cp.attrib['y']}")

    curve_type_map = {
        "cubic-bezier-spline": "CubicBezierSpline",
        "cubic-spline": "CubicSpline",
        "piecewise-linear": "PiecewiseLinear",
    }
    raw_type = mapping.attrib.get("type", "cubic-bezier-spline") if mapping is not None else "cubic-bezier-spline"
    add_property(el, "string", "curve-type", curve_type_map.get(raw_type, "CubicBezierSpline"))

    append_label_and_mode(el, "Response Curve", "disallowed")
    return aid, el


def convert_map_to_mouse(mm_el: ET.Element) -> tuple[str, ET.Element]:
    aid, el = make_action("map-to-mouse")
    add_property(el, "string", "mode", "Motion")
    add_property(el, "int", "direction", mm_el.attrib.get("direction", "0"))
    add_property(el, "int", "min-speed", mm_el.attrib.get("min-speed", "0"))
    add_property(el, "int", "max-speed", mm_el.attrib.get("max-speed", "0"))
    add_property(el, "float", "time-to-max-speed", mm_el.attrib.get("time-to-max-speed", "1.0"))
    append_label_and_mode(el, "Map to Mouse")
    return aid, el


def convert_map_to_keyboard(mtk_el: ET.Element) -> tuple[str, ET.Element]:
    """R13 <map-to-keyboard><key extended scan-code/>...</map-to-keyboard>
    -> R14 <action type=map-to-keyboard> with one <input> child per key, each
    holding scan-code (int) and is-extended (bool) properties.

    Schema verified against JG R14 source action_plugins/map_to_keyboard/__init__.py:
      - element type="map-to-keyboard"
      - per-key wrapper element name is "input"
      - R13 attribute "extended" maps to R14 property "is-extended"
    """
    aid, el = make_action("map-to-keyboard")
    for key_el in mtk_el.findall("key"):
        inp = ET.SubElement(el, "input")
        add_property(inp, "int", "scan-code", key_el.attrib.get("scan-code", "0"))
        add_property(inp, "bool", "is-extended", key_el.attrib.get("extended", "False"))
    append_label_and_mode(el, "Map to Keyboard")
    return aid, el


def convert_play_sound(ps_el: ET.Element) -> tuple[str, ET.Element]:
    """R13 <play-sound file="X" volume="N"/> -> R14 <action type=play-sound>
    with filename (string) and volume (int) properties.

    Schema verified against JG R14 source action_plugins/play_sound/__init__.py:
      - element type="play-sound"
      - properties: filename (string), volume (int)
      - R13 uses attribute name `file`; R14 renames to `filename`

    JG R14 raises a load-time error if the filename path does not exist or is
    inaccessible. Old R13 profiles often carry stale paths from earlier folder
    layouts — those paths get preserved here unchanged. Audit the report.txt
    sound-file references after conversion if loading fails."""
    aid, el = make_action("play-sound")
    add_property(el, "string", "filename", ps_el.attrib.get("file", ""))
    add_property(el, "int", "volume", ps_el.attrib.get("volume", "100"))
    append_label_and_mode(el, "Play Sound")
    return aid, el


def convert_noop(_noop_el: ET.Element, input_description: str) -> tuple[str, ET.Element]:
    """R13 noop has no direct R14 equivalent (R14 removed the plugin), but R14's
    `description` action is the closest semantic match — both are no-runtime-
    effect placeholders that exist to be visible in the UI. Convert noop to a
    description action whose text records the conversion, optionally prefixed
    with the parent input's R13 description attribute (which often carries the
    creator's note explaining *why* the slot is a deliberate no-op).

    Schema verified against JG R14 source action_plugins/description/__init__.py:
      - element type="description"
      - single string property named "description" carrying the label text"""
    aid, el = make_action("description")
    note = "Incompatible action 'noop' converted to description"
    if input_description:
        text = f"{input_description} - {note}"
    else:
        text = note
    add_property(el, "string", "description", text)
    append_label_and_mode(el, "Description", "disallowed")
    return aid, el


def convert_macro(macro_el: ET.Element, log) -> tuple[str, ET.Element]:
    aid, el = make_action("macro")
    add_property(el, "bool", "is-exclusive", "False")
    add_property(el, "string", "repeat-mode", "Single")
    add_property(el, "int", "repeat-count", "1")
    add_property(el, "float", "repeat-delay", "0.1")

    actions = macro_el.find("actions")
    if actions is not None:
        for child in actions:
            tag = child.tag
            if tag == "key":
                ma = ET.SubElement(el, "macro-action", type="key")
                add_property(ma, "int", "scan-code", child.attrib["scan-code"])
                add_property(ma, "bool", "is-extended", child.attrib.get("extended", "False"))
                add_property(ma, "bool", "is-pressed", child.attrib.get("press", "True"))
            elif tag == "pause":
                ma = ET.SubElement(el, "macro-action", type="pause")
                add_property(ma, "float", "duration", child.attrib["duration"])
            elif tag == "vjoy":
                # Schema verified against gremlin/macro.py VJoyAction.to_xml.
                # Property order: vjoy-id, input-type, input-id, value, [axis-mode].
                ma = ET.SubElement(el, "macro-action", type="vjoy")
                vit = child.attrib.get("input-type", "button")
                add_property(ma, "int", "vjoy-id", child.attrib.get("vjoy-id", "1"))
                add_property(ma, "input_type", "input-type", vit)
                add_property(ma, "int", "input-id", child.attrib["input-id"])
                if vit == "axis":
                    add_property(ma, "float", "value", child.attrib.get("value", "0.0"))
                    add_property(ma, "axis_mode", "axis-mode", child.attrib.get("axis-mode", "Absolute"))
                elif vit == "hat":
                    add_property(ma, "hat_direction", "value", child.attrib.get("value", "(0,0)"))
                else:
                    add_property(ma, "bool", "value", child.attrib.get("value", "False"))
            else:
                log.dropped(f"macro sub-action <{tag}>")

    append_label_and_mode(el, "Macro")
    return aid, el


def convert_action_set(action_set: ET.Element, library: list[ET.Element], log,
                       input_description: str = "") -> list[str]:
    """Convert all primitive actions in one R13 <action-set> to R14 library entries.
    Appends each new action to `library` in the order it should be serialized
    (children appear before any root that references them).

    `input_description` is the R13 `<button|axis|hat description="...">` value
    for the input this action-set belongs to. Forwarded to converters that
    benefit from the surrounding context (currently `convert_noop`).

    Returns the list of action ids to populate parent <actions> /
    <short-actions> / <long-actions>. Response-curves are sorted to the front:
    R14 evaluates a root's children in order, so the curve must shape the input
    *before* map-to-vjoy reads it. R13 commonly placed response-curve after
    remap in source order; preserving that order silently breaks the curve."""
    rc_ids: list[str] = []
    other_ids: list[str] = []
    for a in action_set:
        tag = a.tag
        if tag == "remap":
            aid, el = convert_remap(a)
        elif tag == "cycle-modes":
            aid, el = convert_cycle_modes(a)
        elif tag == "temporary-mode-switch":
            aid, el = convert_temp_mode_switch(a)
        elif tag == "switch-mode":
            aid, el = convert_switch_mode(a)
        elif tag == "response-curve":
            aid, el = convert_response_curve(a)
        elif tag == "map-to-mouse":
            aid, el = convert_map_to_mouse(a)
        elif tag == "map-to-keyboard":
            aid, el = convert_map_to_keyboard(a)
        elif tag == "macro":
            aid, el = convert_macro(a, log)
        elif tag == "play-sound":
            aid, el = convert_play_sound(a)
        elif tag == "previous-mode":
            aid, el = convert_previous_mode(a)
        elif tag == "text-to-speech":
            log.dropped_tts(a.attrib.get("text", ""))
            continue
        elif tag == "noop":
            aid, el = convert_noop(a, input_description)
            log.dropped("noop converted to description action")
        else:
            log.warn(f"Unknown action tag '{tag}'; skipped")
            continue
        library.append(el)
        if tag == "response-curve":
            rc_ids.append(aid)
        else:
            other_ids.append(aid)
    return rc_ids + other_ids


def convert_input(input_el: ET.Element, mode_name: str, device_guid: str,
                  library: list[ET.Element], log) -> ET.Element | None:
    """Build the R14 <input> + library entries for one R13 button/axis/hat.

    Library order produced (tempo case):  children → tempo → root
    Library order produced (basic case):  children → root
    """
    container = input_el.find("container")
    if container is None:
        return None

    ctype = container.attrib.get("type", "basic")
    sets = container.findall("action-set")
    input_desc = input_el.attrib.get("description", "")

    root_child_ids: list[str] = []

    if ctype == "tempo":
        if not sets:
            log.warn(f"Empty tempo container on {input_el.tag} {input_el.attrib.get('id','?')} — skipped")
            return None
        short_ids = convert_action_set(sets[0], library, log, input_desc) if len(sets) >= 1 else []
        long_ids = convert_action_set(sets[1], library, log, input_desc) if len(sets) >= 2 else []
        if not short_ids and not long_ids:
            return None

        tempo_id, tempo_el = make_action("tempo")
        sa = ET.SubElement(tempo_el, "short-actions")
        for sid in short_ids:
            ET.SubElement(sa, "action-id").text = sid
        la = ET.SubElement(tempo_el, "long-actions")
        for lid in long_ids:
            ET.SubElement(la, "action-id").text = lid
        add_property(tempo_el, "float", "threshold", container.attrib.get("delay", "0.5"))
        add_property(tempo_el, "string", "activate-on", container.attrib.get("activate-on", "press"))
        label = input_el.attrib.get("description", "Tempo") or "Tempo"
        append_label_and_mode(tempo_el, label, "disallowed")
        library.append(tempo_el)
        root_child_ids.append(tempo_id)
    elif ctype == "double_tap":
        # Schema verified against JG R14 source action_plugins/double_tap/
        # __init__.py: tag="double-tap"; children are <single-actions> and
        # <double-actions> wrapping <action-id> entries (not <short-actions>/
        # <long-actions> like tempo). Properties are `threshold` (float) and
        # `activate-on` (string). R13 used `delay` for the threshold; R14
        # renamed it. R13's activate-on values like "exclusive" pass through
        # to R14 unchanged.
        if not sets:
            log.warn(f"Empty double_tap container on {input_el.tag} {input_el.attrib.get('id','?')} — skipped")
            return None
        single_ids = convert_action_set(sets[0], library, log, input_desc) if len(sets) >= 1 else []
        double_ids = convert_action_set(sets[1], library, log, input_desc) if len(sets) >= 2 else []
        if not single_ids and not double_ids:
            return None

        dt_id, dt_el = make_action("double-tap")
        sa = ET.SubElement(dt_el, "single-actions")
        for sid in single_ids:
            ET.SubElement(sa, "action-id").text = sid
        da = ET.SubElement(dt_el, "double-actions")
        for did in double_ids:
            ET.SubElement(da, "action-id").text = did
        add_property(dt_el, "float", "threshold", container.attrib.get("delay", "0.5"))
        add_property(dt_el, "string", "activate-on", container.attrib.get("activate-on", "exclusive"))
        label = input_el.attrib.get("description", "Double Tap") or "Double Tap"
        append_label_and_mode(dt_el, label, "disallowed")
        library.append(dt_el)
        root_child_ids.append(dt_id)
    else:
        if ctype != "basic":
            log.warn(f"Unknown container type '{ctype}' on {input_el.tag} {input_el.attrib.get('id','?')}; treated as basic")
        for s in sets:
            root_child_ids.extend(convert_action_set(s, library, log, input_desc))
        if not root_child_ids:
            return None

    root_id, root_el = make_action("root")
    root_actions = ET.SubElement(root_el, "actions")
    for cid in root_child_ids:
        ET.SubElement(root_actions, "action-id").text = cid
    append_label_and_mode(root_el, "Root", "disallowed")
    library.append(root_el)

    inp = ET.Element("input")
    ET.SubElement(inp, "device-id").text = normalize_device_id(device_guid)
    ET.SubElement(inp, "input-type").text = input_el.tag
    ET.SubElement(inp, "mode").text = mode_name
    ET.SubElement(inp, "input-id").text = input_el.attrib["id"]
    cfg = ET.SubElement(inp, "action-configuration")
    ET.SubElement(cfg, "root-action").text = root_id
    # R13 supports an axis-as-button trigger via a <virtual-button> sibling of
    # <action-set> inside an axis container. The action only fires when the
    # axis crosses configured thresholds (e.g. lower-limit=0.95 / upper-limit=
    # -0.95 means "fire near either extreme"). R14 expresses this by setting
    # the input's <behavior> to "button" while leaving <input-type> as "axis".
    # If we don't translate, R14 evaluates the action chain continuously across
    # the entire axis range and runaway-fires (verified on Sub's STECS Y-rot
    # mode-switch axis: caused JG R14 to stall until the profile was disabled).
    #
    # Setting <behavior>button</behavior> alone is not enough. JG R14's
    # _parse_virtual_button (gremlin/profile.py) raises AttributeError when an
    # axis input has behavior=button but no <virtual-button> sub-element under
    # <action-configuration> -- the entire profile fails to load. So we also
    # emit a <virtual-button> block translating R13's attributes (direction,
    # lower-limit, upper-limit) to R14's sub-elements
    # (<axis-button-direction>, <lower-limit>, <upper-limit>). Format
    # validated against SOL-R 2's working R14 (4 axis-as-button inputs).
    behavior = input_el.tag
    vb = None if input_el.tag != "axis" else container.find("virtual-button")
    if vb is not None:
        behavior = "button"
    ET.SubElement(cfg, "behavior").text = behavior
    if vb is not None:
        vb_el = ET.SubElement(cfg, "virtual-button")
        ET.SubElement(vb_el, "lower-limit").text = vb.attrib.get("lower-limit", "-1.0")
        ET.SubElement(vb_el, "upper-limit").text = vb.attrib.get("upper-limit", "1.0")
        ET.SubElement(vb_el, "axis-button-direction").text = vb.attrib.get("direction", "anywhere")
    return inp


# ---------- top-level ----------

class Logger:
    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.warn_count = 0
        self.tts_count = 0
        self.tts_examples: list[str] = []
        self.dropped_count = 0
        self.dropped_examples: list[str] = []

    def warn(self, msg: str) -> None:
        print(f"[warn] {msg}", file=sys.stderr)
        self.warn_count += 1

    def dropped(self, what: str) -> None:
        if self.verbose:
            print(f"[drop] {what}", file=sys.stderr)
        self.dropped_count += 1
        if len(self.dropped_examples) < 10:
            self.dropped_examples.append(what)

    def dropped_tts(self, text: str) -> None:
        if self.verbose:
            print(f"[drop] TTS: {text!r}", file=sys.stderr)
        self.tts_count += 1
        if len(self.tts_examples) < 10:
            self.tts_examples.append(text)


def collect_modes(r13_root: ET.Element) -> dict[str, str | None]:
    """Find the unique mode set across all devices, with parent (`inherit`) relationships.

    R13 declares modes per-device. The same mode name can appear on multiple
    devices with different (or absent) `inherit` attributes — typically because
    only the actively-bound devices set inheritance and inactive/legacy device
    entries leave it blank. First-wins drops the real inheritance when an
    inherit-less device is iterated first (silent regression: throttle/stick
    renders blank in JG R14 because modes that should inherit from SCM no
    longer do). Prefer any non-None inherit value over None for the same mode.
    """
    modes: dict[str, str | None] = {}
    for device in r13_root.findall("./devices/device") + r13_root.findall("./devices/vjoy-device"):
        for m in device.findall("mode"):
            name = m.attrib.get("name")
            if not name:
                continue
            inherit = m.attrib.get("inherit")
            if name not in modes or (modes[name] is None and inherit is not None):
                modes[name] = inherit
    return modes


def write_pretty(root: ET.Element, output_path: str) -> None:
    rough = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="    ")
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def parse_default_delay(r13_root: ET.Element) -> str:
    delay_el = r13_root.find("./settings/default-delay")
    if delay_el is not None and delay_el.text:
        return delay_el.text.strip()
    return "0.05"


def write_report(report_path: str, action_counts: Counter, log: Logger,
                 input_count: int, library_count: int) -> None:
    lines = []
    lines.append(f"R13 → R14 conversion report")
    lines.append(f"")
    lines.append(f"Inputs emitted:        {input_count}")
    lines.append(f"Library actions:       {library_count}")
    lines.append(f"")
    lines.append(f"Action types in library:")
    for atype, count in sorted(action_counts.items()):
        lines.append(f"  {atype:20s}  {count}")
    lines.append(f"")
    lines.append(f"Dropped — text-to-speech:  {log.tts_count}")
    if log.tts_examples:
        for ex in log.tts_examples:
            lines.append(f"    {ex!r}")
        if log.tts_count > len(log.tts_examples):
            lines.append(f"    ... and {log.tts_count - len(log.tts_examples)} more")
    lines.append(f"Dropped — other:           {log.dropped_count}")
    if log.dropped_examples:
        for ex in log.dropped_examples:
            lines.append(f"    {ex}")
        if log.dropped_count > len(log.dropped_examples):
            lines.append(f"    ... and {log.dropped_count - len(log.dropped_examples)} more")
    lines.append(f"Warnings:                  {log.warn_count}")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def default_report_path(r14_path: str) -> str:
    """Sidecar reports live in the per-stick `.Assets/` folder, alongside the
    other ancillary materials. The folder is created on demand."""
    out = Path(r14_path)
    assets = out.parent / ".Assets"
    assets.mkdir(exist_ok=True)
    return str(assets / f"{out.stem}.report.txt")


def convert(r13_path: str, r14_path: str, log: Logger, report_path: str | None = None) -> None:
    tree = ET.parse(r13_path)
    r13 = tree.getroot()

    if r13.attrib.get("version") != "9":
        log.warn(f"Input profile version is {r13.attrib.get('version')!r}, expected '9'")

    r14 = ET.Element("profile", version="14")
    inputs_el = ET.SubElement(r14, "inputs")
    settings_el = ET.SubElement(r14, "settings")
    ET.SubElement(settings_el, "startup-mode").text = "Use Heuristic"
    ET.SubElement(settings_el, "macro-default-delay").text = parse_default_delay(r13)
    ET.SubElement(r14, "logical-device")

    # Library is built as a flat list and serialized in append order,
    # which is the dependency order JG R14 needs.
    library_actions: list[ET.Element] = []

    # Only emit devices in the R14 <devices> section if they actually produced
    # at least one bound input. R13 profiles often carry leftover device
    # declarations from disconnected/legacy hardware that have mode listings but
    # no actual button/axis/hat children. Listing such "ghost" devices in the
    # R14 profile causes JG R14 to attempt reconciliation against hardware that
    # isn't there, which can render an unrelated *connected* device blank in
    # the UI (verified against Sub's Virpil VMAX+Aeromax profile, where two
    # leftover VKBSim Space Gunfighter declarations caused the throttle to
    # render blank even though it was bound and connected).
    device_meta: dict[str, str] = {}
    bound_device_ids: list[str] = []
    seen_bound: set[str] = set()
    for device in r13.findall("./devices/device"):
        if device.attrib.get("type") != "joystick":
            continue
        guid = device.attrib["device-guid"]
        device_meta[guid] = device.attrib.get("name", "")
        for mode_el in device.findall("mode"):
            mode_name = mode_el.attrib["name"]
            for input_el in mode_el:
                if input_el.tag not in ("button", "axis", "hat"):
                    continue
                inp = convert_input(input_el, mode_name, guid, library_actions, log)
                if inp is not None:
                    inputs_el.append(inp)
                    if guid not in seen_bound:
                        seen_bound.add(guid)
                        bound_device_ids.append(guid)
    physical_devices = [(guid, device_meta[guid]) for guid in bound_device_ids]

    library_el = ET.SubElement(r14, "library")
    for a in library_actions:
        library_el.append(a)

    modes_section = ET.SubElement(r14, "modes")
    modes = collect_modes(r13)
    # Roots first (no parent), then descendants — keeps JG happy and is what Fixed does.
    for name, parent in modes.items():
        if parent is None:
            ET.SubElement(modes_section, "mode").text = name
    for name, parent in modes.items():
        if parent is not None:
            ET.SubElement(modes_section, "mode", parent=parent).text = name

    ET.SubElement(r14, "scripts")

    devices_section = ET.SubElement(r14, "devices")
    for guid, name in physical_devices:
        d = ET.SubElement(devices_section, "device")
        ET.SubElement(d, "device-id").text = normalize_device_id(guid)
        ET.SubElement(d, "device-name").text = name

    write_pretty(r14, r14_path)

    action_counts = Counter(a.attrib["type"] for a in library_actions)

    print(f"Wrote {r14_path}")
    print(f"  Inputs:          {len(inputs_el)}")
    print(f"  Library actions: {len(library_actions)}")
    type_summary = ", ".join(f"{t}={c}" for t, c in sorted(action_counts.items()))
    print(f"  Types:           {type_summary}")
    if log.tts_count:
        print(f"  TTS dropped:     {log.tts_count}")
    if log.dropped_count:
        print(f"  Other dropped:   {log.dropped_count}")
    if log.warn_count:
        print(f"  Warnings:        {log.warn_count}", file=sys.stderr)

    resolved_report = report_path if report_path else default_report_path(r14_path)
    write_report(resolved_report, action_counts, log, len(inputs_el), len(library_actions))
    print(f"Report:          {resolved_report}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="R13 (profile version 9) XML")
    p.add_argument("output", help="R14 (profile version 14) XML")
    p.add_argument("--verbose", action="store_true", help="Print each dropped TTS / other action as it happens")
    p.add_argument("--report", help="Override the report path (default: <output_dir>/.Assets/<output_stem>.report.txt)")
    args = p.parse_args()
    log = Logger(verbose=args.verbose)
    convert(args.input, args.output, log, args.report)
    return 1 if log.warn_count else 0


if __name__ == "__main__":
    sys.exit(main())
