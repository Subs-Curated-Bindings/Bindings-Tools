#!/usr/bin/env python3
"""
Extract a {physical input -> control name} table from an R14 JG profile.

This is the bridge the interactive chart needs to support a NO-JG upload:
the chart is keyed to vJoy slots, but a non-JG user's layout.xml references
PHYSICAL buttons. This table maps each physical input id -> the etched control
name (from the profile's <action type="description"> bridge), and also records
the vJoy slot(s) that physical input emits (the physical->vJoy half of the
bridge that the JG profile owns).

Two source conventions are supported:
  * default (em-dash): control name = the head of a description bridge,
    "<etched-name>[ [Mode]] — <chart text>" (NXT and the other em-dash sticks).
  * --monikers: control name = the input's PHYSICAL MONIKER, verbatim (leading
    bare token on an action-label: L30.up, L-SW-1.up, LL-BTN.6, ...). The JG
    profile is the source of truth for the chart's control identity — one box
    per moniker — so the moniker is carried through as the control. The chart
    cluster the moniker maps to is recorded separately as `seed_group` (the
    template bind.X group the box starts near on the blank chart). SOL-R 2
    dropped its em-dash bridges in favour of monikers (2026-06-05), so its
    control map must be extracted this way.

In --monikers mode, `--stick` picks the per-stick (left GUID, moniker → seed
mapping) pair: `solr` (default, TM SOL-R 2), `gf` (dual VKB Gunfighter,
migrated 2026-06-11 `367ac23`), `vmax` (Virpil VMAX Throttle + Aeromax-R,
migrated 2026-06-12 `aae6858`) or `moza` (MOZA MTQ + MHG, migrated
2026-06-12). GF specifics: monikers match the chart's
per-direction bind.X groups nearly 1:1 (tempo-leaf `.tap`/`.hold` suffixes are
stripped to the base moniker); the A1 ministick's WHOLE button-mode enumeration
(buttons 16-20, incl. the press-in btn 20) is excluded — the analog ministick
has no press, and its bound path is the POV hat (vjoy hat 1 SCM / hat 2
Modifier), which fans to the same `<S>-A1.<dir>` anchors at generate time;
main-flight axes (X/Y/Z) are hidden; the
mouse-camera axes (R 4/5, quoted labels with no moniker) fall back to the JG
HID axis name (`R-X-Rotation` / `R-Y-Rotation`) so the labeled camera rows get
a charted anchor instead of colliding on device-agnostic `axis.N`.

VMAX specifics: throttle (T-*) = left/js1, Aeromax grip (R-*) = right/js2.
Button monikers ARE the chart's bind.X group names (tempo leaves stripped).
The `.pm` suffix is the Aeromax's PHYSICAL MODIFIER layer (R-B3 hardware
shift; shifted presses arrive as distinct HID buttons 25-36) — kept verbatim
in the control; the chart generator folds `<base>.pm` rows onto the base
control's box tagged [PM]. Mini-stick analog axes anchor X → `<M1>.left`,
Y → `<M1>.up` (the SOL-R convention, so distributeMiniStickAxes fans the
bidirectional labels onto the opposing arrows); the R-M1 threshold emits
(axis-as-button) fan to their own directional monikers at generate time.
Axis table: T-Z-Rotation = T-T1 thumb slider, T-Slider/T-Dial = the E1/E2
encoder rotations, R-Z-Rotation's threshold = R-BRAKE (space brake; the
analog lever itself is uncharted); main-flight + EVA axes hidden.

MOZA specifics: MTQ throttle (T-*) = left/vjoy 1, MHG grip (R-*) = right/
vjoy 2. Button monikers ARE the chart's bind.X group names (tempo leaves
`.tap`/`.hold`/`.double-tap` stripped) with three seed exceptions: T-B1 (the
Modifier; chart has only the label.T-B1 "MODIFIER" frame), R-BB-3 (the chart's
BB-3 body frame is the typo'd label.R-BB-31, no bind group), and the
single-frame encoders (T-E2.up/.down and T-E3.up/.down seed near bind.T-E2 /
bind.T-E3 — only E1 is direction-split on the chart). bind.R-BB-2 stays
physically driverless (vjoy 32 is reachable only as Modifier+R-LNCH, which
charts on R-LNCH). Axis table: T-X/Y-Axis = the T-M1 analog mini-stick
(anchor X -> .left, Y -> .up); T-Slider/T-Dial = the T-2/T-3 thumb dials;
R-Slider = R-RT2 (anchored at R-RT2.up, fanned to the .down arrow at render);
the MHG X-Rotation/Y-Rotation mouse-camera axes keep their HID names (GF
precedent — quoted Camera rows need a charted anchor); throttle levers
(T-X/Y-Rotation, incl. their >90% Boost thresholds), main-flight axes and
the unbound R-RT1/R-Dial are hidden.

Output JSON keyed by device role (left-stick / right-stick), each a list of
{ index, type, control, seed_group, vjoy } entries.

Usage:
  py tools/extract-physical-control-map.py "<JG profile>.xml" [-o out.json]
  py tools/extract-physical-control-map.py "<SOL-R>.xml" --monikers -o out.json
  py tools/extract-physical-control-map.py "<GF>.xml" --monikers --stick gf -o out.json
"""
import sys, json, re, argparse
import xml.etree.ElementTree as ET

CHILD_CONTAINERS = ("actions", "short-actions", "long-actions",
                    "single-actions", "double-actions")

# --- SOL-R moniker -> chart-cluster mapping --------------------------------
# Used only in --monikers mode. KEEP IN SYNC with the authoritative copy in
# tools/_sol-r-descriptions-from-monikers.py (the hyphenated filename can't be
# imported). Mapping confirmed by Sub 2026-06-04.
SOLR_LEFT_GUID = "141b1470-1081-11f0-8006-444553540000"
_DIRS = ("up", "down", "left", "right", "press")
# leading moniker token on an action-label, e.g. "L30.up", "MAIN-TRIGGER.stage1"
MONIKER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)+)")


def moniker_to_cluster(mon, side):
    """moniker -> chart cluster head (or None unmapped / '__AXIS__' hidden)."""
    parts = mon.split(".")
    base = parts[0]
    suf = parts[1] if len(parts) > 1 else None
    m = re.match(r"^([LR])(30|40)$", base)
    if m:
        d = suf if suf in _DIRS else None
        head = f"4WAY-HAT-{m.group(1)}-{m.group(2)}"
        return f"{head}.{d}" if d else head
    m = re.match(r"^[LR]-SW-([1-4])$", base)
    if m:
        n = int(m.group(1))
        return f"{side}{'L' if n <= 2 else 'R'}-SWITCH"
    m = re.match(r"^([LR][LR])-BTN$", base)
    if m:
        return f"{m.group(1)}-BTNS"
    if re.match(r"^[LR]-ENCODER$", base):
        return f"{side}-ENCODER"
    if re.match(r"^[LR]-KNOB$", base):
        return f"{side}-KNOB"
    if base == "MAIN-TRIGGER" or re.match(r"^[LR]-MAIN-TRIGGER$", base):
        return f"MAIN-TRIG-{side}"
    if re.match(r"^[LR]-RF$", base):
        return f"RAPID-TRIG-{side}"
    if re.match(r"^[LR]-PINKY$", base):
        return f"PINKY-{side}"
    if base in ("L-Z-Axis", "R-Z-Axis"):
        return f"{side}-THROTTLE"
    if base in ("ANALOG-HAT-L", "ANALOG-HAT-R"):
        return base
    if re.match(r"^[LR]-ANALOG$", base) or re.match(r"^[LR]-(X|Y)-Rotation$", base):
        return f"ANALOG-HAT-{side}"
    if re.match(r"^[LR]-SCROLL$", base):
        return mon            # L-SCROLL.up etc. — own bind, no cluster
    if re.match(r"^(?:[LR]-)?BTN$", base):
        # loose base buttons: own bind, no cluster (control keeps the full
        # side-prefixed moniker; seed near the template's bare BTN group)
        return f"BTN.{suf}" if suf else "BTN"
    if (re.match(r"^[LR]-(X|Y|Z)-Axis$|^[LR]-Z-Rotation$"
                 r"|^[LR]-(Slider|Dail|Dial)(-[12])?$", base)
            or base == "R-stick"):
        return "__AXIS__"     # hidden main flight axis / spare slider — not charted
    return None               # unmapped — report, leave null


# --- GF (dual VKB Gunfighter) moniker -> (control, seed_group) --------------
# The GF monikers (NXT grip names) match the chart template's bind.X groups
# nearly 1:1, so unlike the SOL-R there is no separate cluster vocabulary —
# the mapping mostly returns the (normalized) moniker itself as the seed group.
GF_LEFT_GUID = "0dcdeb30-d727-11ef-8013-444553540000"
GF_AXIS_NAME = {1: "X-Axis", 2: "Y-Axis", 3: "Z-Axis",
                4: "X-Rotation", 5: "Y-Rotation"}
_GF_UNMAPPED = object()   # sentinel: real moniker we couldn't place — report


def gf_control_and_seed(mon, side, itype, iid):
    """GF moniker -> (control, seed_group).

    control None = uncharted (hidden axis / excluded enumeration); the
    _GF_UNMAPPED sentinel as seed marks a moniker that SHOULD have mapped.
    seed_group None = charted but no template group (the bake places it)."""
    if mon is None:
        # The mouse-camera axes (R 4/5) carry a quoted label, no moniker —
        # fall back to the side-prefixed JG HID axis name so the labeled
        # camera rows anchor to a real charted control.
        if itype == "axis":
            name = GF_AXIS_NAME.get(int(iid)) if str(iid).isdigit() else None
            if name in ("X-Rotation", "Y-Rotation"):
                return (f"{side}-{name}", None)
        return (None, None)
    # Tempo leaves carry the full <moniker>.tap/.hold — strip to the base
    # moniker (the box identity; tap/hold are rows inside the box).
    parts = mon.split(".")
    while len(parts) > 1 and parts[-1] in ("tap", "hold"):
        parts.pop()
    mon = ".".join(parts)
    base = parts[0]
    suf = parts[1] if len(parts) > 1 else None
    # A1 ministick. The ENTIRE button-mode enumeration (16-20) is excluded —
    # the bound path is the POV hat, which fans to the same <S>-A1.<dir> anchors
    # at generate time. Button 20 (`<S>-A1.press-in`) is excluded too: the
    # analog ministick has no press-in (Sub, 2026-06-12), and it's unbound on
    # both grips anyway.
    if re.match(r"^[LR]-A1$", base) and itype == "button":
        return (None, None)
    if re.match(r"^[LR]-A1$", base) and itype == "hat":
        return (mon, None)        # directions fan out at generate time
    if re.match(r"^[LR]-(A3|A4|C1)$", base) and suf:
        return (mon, mon)         # per-direction template groups exist
    if re.match(r"^[LR]-(A2|B1|D1)$", base):
        # B1 seeds near the old chart's "A1B" group name (the moniker pass
        # renamed the control to the grip-identical NXT name).
        seed = f"{base[0]}-A1B" if base.endswith("-B1") else mon
        return (mon, seed)
    if base.startswith("MAIN-TRIG-"):
        # The template stage-splits only the RIGHT trigger; left stages seed
        # near the single MAIN-TRIG-L group.
        return (mon, mon if base.endswith("-R") else base)
    if base.startswith("RAPID-TRIG-"):
        return (mon, base)        # template has one group per rapid trigger
    if re.match(r"^[LR]-(X|Y)-Rotation$", base):
        return (mon, None)        # ministick analog axes — bake places them
    if re.match(r"^[LR]-(X|Y|Z)-Axis$", base):
        return (None, None)       # main flight axes (strafe / yaw-pitch-roll / twist) — hidden
    return (None, _GF_UNMAPPED)


# --- VMAX+AERO (Virpil VMAX Throttle + Aeromax-R) moniker -> (control, seed) --
# Monikers match the painted chart's bind.X groups nearly 1:1, so buttons pass
# through verbatim. Axes are table-driven (the moniker walk can pick up noise
# tokens like "Mini-stick" from prose action-labels, and the charted identity
# of an axis isn't always its HID-name moniker).
VMAX_LEFT_GUID = "63b4c490-c93b-11f0-8004-444553540000"   # VPC CDT-VMAX Throttle
# (side, axis-id) -> (control, seed_group). None = uncharted (hidden axis).
VMAX_AXIS = {
    # Throttle: mini-stick X/Y anchor to the .left/.up arrows (SOL-R convention
    # — distributeMiniStickAxes fans the bidirectional labels at render).
    ("L", "1"): ("T-M1.left", "T-M1.left"),
    ("L", "2"): ("T-M1.up", "T-M1.up"),
    ("L", "4"): (None, None),            # T-X-Rotation — EVA axis, uncharted
    ("L", "5"): (None, None),            # T-Y-Rotation — main throttle, uncharted
    ("L", "6"): ("T-T1", "T-T1"),        # T-Z-Rotation = thumb slider T-T1
    ("L", "7"): ("T-E1", "T-E1"),        # T-Slider = E1 encoder rotation
    ("L", "8"): ("T-E2", "T-E2"),        # T-Dial = E2 encoder rotation
    # Aeromax: main flight axes hidden; mini-stick like the throttle's (its
    # axis-as-button thresholds fan to R-M1.<dir> monikers at generate time,
    # and the Modifier-mode map-to-mouse camera rows ride the .left/.up boxes,
    # mirrored to the opposite arrows by distributeMiniStickAxes).
    ("R", "1"): (None, None),
    ("R", "2"): (None, None),
    ("R", "3"): (None, None),
    ("R", "4"): ("R-M1.left", "R-M1.left"),
    ("R", "5"): ("R-M1.up", "R-M1.up"),
    ("R", "6"): ("R-BRAKE", None),       # brake-lever threshold = space brake (new box, no template group)
    ("R", "7"): ("R-Slider", None),      # R-Slider — throttle at the right grip base; unbound in-game, charted as Unbound
    ("R", "8"): (None, None),            # R-Dial — unbound
}


def vmax_control_and_seed(mons, side, itype, iid):
    """VMAX moniker(s) -> (control, seed_group).

    Takes the full collected moniker LIST for the input (not just the first):
    tempo leaves carry `<moniker>.tap`/`.hold` variants that strip back to one
    base, and prose labels can contribute noise tokens the set-collapse drops.
    control None = uncharted; seed_group None = charted but no template group
    (the bake places it)."""
    if itype == "axis":
        return VMAX_AXIS.get((side, str(iid)), (None, None))
    # Collect the per-leaf base monikers IN ORDER (tempo .tap/.hold stripped).
    ordered = []
    for mon in mons:
        parts = mon.split(".")
        while len(parts) > 1 and parts[-1] in ("tap", "hold"):
            parts.pop()
        b = ".".join(parts)
        # Noise guard: a real VMAX button moniker starts with T- / R- / a
        # trigger cluster name. Drop prose tokens that matched MONIKER_RE.
        if re.match(r"^(?:[TR]-|MAIN-TRIG-R\.|FLIP-TRIG-R\.)", b):
            ordered.append(b)
    if not ordered:
        return (None, None)
    uniq = set(ordered)
    if len(uniq) > 1:
        # One physical button drives several CHART controls — e.g. the Aeromax
        # flip trigger's down-press (map-to-vjoy) vs its release macro (exit to
        # guns), now FLIP-TRIG-R.down / FLIP-TRIG-R.up. The control map is keyed
        # per physical input, so it can only anchor ONE: the FIRST (primary)
        # leaf. The generator routes the sibling leaves to their own boxes by
        # each leaf's own moniker (same-root reroute). Only siblings of one
        # control are expected here; if the roots differ it's a real ambiguity,
        # so still report it.
        roots = {b.rsplit(".", 1)[0] for b in uniq}
        if len(roots) > 1:
            return (None, _GF_UNMAPPED)
        mon = ordered[0]
    else:
        mon = ordered[0]
    if mon.endswith(".pm"):
        # Physical-Modifier layer: the generator folds these onto the base
        # control's box as [PM] rows — the .pm anchor itself never needs a seed.
        return (mon, None)
    if mon.startswith("FLIP-TRIG-R."):
        # .flip / .pull split the chart's single FLIP-TRIG-R cluster.
        return (mon, "FLIP-TRIG-R")
    return (mon, mon)


# --- MOZA MTQ + MHG moniker -> (control, seed) -------------------------------
# Monikers match the painted chart's bind.X groups nearly 1:1, so buttons pass
# through verbatim. Axes are table-driven (same rationale as the VMAX).
MOZA_LEFT_GUID = "b3167000-d436-11f0-8001-444553540000"   # MOZA MTQ throttle
# (side, axis-id) -> (control, seed_group). None = uncharted (hidden axis).
MOZA_AXIS = {
    # MTQ: the T-M1 mini-stick analog axes anchor to the .left/.up arrows
    # (SOL-R convention — distributeMiniStickAxes fans the bidirectional
    # labels at render).
    ("L", "1"): ("T-M1.left", "T-M1.left"),
    ("L", "2"): ("T-M1.up", "T-M1.up"),
    ("L", "4"): (None, None),            # throttle lever (X-Rotation) — uncharted,
    ("L", "5"): (None, None),            # ditto Y-Rotation; >90% Boost thresholds ride them
    ("L", "7"): ("T-2", "T-2"),          # T-Slider = T-2 thumb dial
    ("L", "8"): ("T-3", "T-3"),          # T-Dial = T-3 thumb dial
    # MHG: main flight axes hidden; the X/Y-Rotation pair is the R-POV's
    # analog mode, routed to mouse free-look — keep the HID names so the
    # quoted Camera rows get a charted anchor (GF precedent).
    ("R", "1"): (None, None),            # yaw
    ("R", "2"): (None, None),            # pitch
    ("R", "4"): ("R-X-Rotation", None),
    ("R", "5"): ("R-Y-Rotation", None),
    ("R", "6"): (None, None),            # roll twist
    ("R", "7"): ("R-RT2.up", "R-RT2.up"),  # speed-limiter wheel; fans to .down at render
    ("R", "8"): (None, None),            # R-RT1 / R-Dial — unbound spare
}


def moza_control_and_seed(mons, side, itype, iid):
    """MOZA moniker(s) -> (control, seed_group).

    Same contract as vmax_control_and_seed: takes the full collected moniker
    LIST, strips tempo/double-tap leaf suffixes, noise-guards prose tokens.
    control None = uncharted; seed_group None = charted but no template group
    (the bake places it)."""
    if itype == "axis":
        return MOZA_AXIS.get((side, str(iid)), (None, None))
    bases = set()
    for mon in mons:
        parts = mon.split(".")
        while len(parts) > 1 and parts[-1] in ("tap", "hold", "double-tap"):
            parts.pop()
        bases.add(".".join(parts))
    # Noise guard: a real MOZA button moniker starts with T- / R- / the
    # trigger cluster name. Drop anything else.
    bases = {b for b in bases if re.match(r"^(?:[TR]-|MAIN-TRIG\.)", b)}
    if not bases:
        return (None, None)
    if len(bases) > 1:
        return (None, _GF_UNMAPPED)      # ambiguous — report for review
    mon = bases.pop()
    if mon == "T-B1":
        return (mon, None)               # Modifier — label.T-B1 frame only
    if mon == "R-BB-3":
        return (mon, None)               # chart frame is the typo'd label.R-BB-31
    m = re.match(r"^(T-E[23])\.(up|down)$", mon)
    if m:
        return (mon, m.group(1))         # single-frame encoders: seed at the base
    return (mon, mon)


def prop(action, name):
    """Return the <value> of the named <property> child, or None."""
    for p in action.findall("property"):
        n = p.find("name")
        v = p.find("value")
        if n is not None and n.text == name:
            return v.text if v is not None else None
    return None


def walk(action_id, lib, seen, descriptions, vjoys, monikers):
    """Recursively collect description text + vJoy slots + monikers from an id."""
    if action_id in seen or action_id not in lib:
        return
    seen.add(action_id)
    act = lib[action_id]
    atype = act.get("type")
    if atype == "description":
        val = prop(act, "description")
        if val:
            descriptions.append(val)
    # leading moniker on an action-label (skip quoted friendly-labels)
    al = prop(act, "action-label")
    if al and not al.lstrip().startswith('"'):
        mm = MONIKER_RE.match(al.strip())
        if mm:
            monikers.append(mm.group(1))
    if atype in ("map-to-vjoy", "vjoy"):
        dev = prop(act, "vjoy-device-id")
        btn = prop(act, "vjoy-input-id")
        itype = prop(act, "vjoy-input-type")
        if btn is not None:
            vjoys.append({"device": dev, "id": btn, "type": itype})
    # macro vjoy sub-actions live as <macro-action type="vjoy"> inside the macro
    for ma in act.findall(".//macro-action"):
        if ma.get("type") == "vjoy":
            btn = None
            for p in ma.findall("property"):
                if (p.find("name") is not None
                        and p.find("name").text == "vjoy-input-id"):
                    btn = p.find("value").text
            if btn is not None:
                vjoys.append({"device": prop(ma, "vjoy-device-id"),
                              "id": btn, "type": "button"})
    # descend into every child-action container
    for cont in CHILD_CONTAINERS:
        c = act.find(cont)
        if c is not None:
            for aid in c.findall("action-id"):
                walk(aid.text, lib, seen, descriptions, vjoys, monikers)


def parse_etched(desc_value):
    """'MAIN-TRIG-L [Modifier] — After Burner Toggle' -> 'MAIN-TRIG-L'."""
    head = desc_value.split("—", 1)[0].strip()
    # strip a trailing [Mode]/[Modifier]/(...) tag if present
    head = re.sub(r"\s*\[[^\]]*\]\s*$", "", head)
    head = re.sub(r"\s*\([^)]*\)\s*$", "", head)
    return head.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("-o", "--out")
    ap.add_argument("--monikers", action="store_true",
                    help="derive control names from physical monikers, "
                         "not em-dash description bridges")
    ap.add_argument("--stick", choices=("solr", "gf", "vmax", "moza"),
                    default="solr",
                    help="which stick's moniker→seed mapping + left GUID to "
                         "use in --monikers mode (default: solr)")
    args = ap.parse_args()
    left_guid = {"gf": GF_LEFT_GUID, "vmax": VMAX_LEFT_GUID,
                 "moza": MOZA_LEFT_GUID}.get(args.stick, SOLR_LEFT_GUID)

    with open(args.profile, "r", encoding="utf-8", newline="") as fh:
        tree = ET.parse(fh)
    root = tree.getroot()

    # library: id -> action element
    lib = {a.get("id"): a for a in root.iter("action") if a.get("id")}

    # physical inputs: collect per (device, type, index) across all modes.
    # Walk EVERY <action-configuration> of an input (findall, not find) so the
    # axis/hat-as-button *holder* configs are seen regardless of order.
    inputs = {}
    for inp in root.iter("input"):
        dev = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = inp.findtext("input-id")
        if dev is None or iid is None:
            continue
        key = (dev, itype, iid)
        rec = inputs.setdefault(key, {"descs": [], "vjoys": [], "mons": []})
        for cfg in inp.findall("action-configuration"):
            rootact = cfg.findtext("root-action")
            if rootact:
                walk(rootact, lib, set(), rec["descs"], rec["vjoys"], rec["mons"])

    # collapse per device
    devices = {}
    unmapped = []
    for (dev, itype, iid), rec in inputs.items():
        if args.monikers:
            # The JG moniker IS the chart's control identity (one box per
            # moniker — the JG profile is the source of truth, the Affinity
            # template is just the blank chart). The mapped cluster is demoted
            # to `seed_group`: which template bind.X group the box starts near
            # on the blank chart. Hidden axes / unmapped monikers resolve to a
            # null control.
            control = None
            seed_group = None
            mon = rec["mons"][0] if rec["mons"] else None
            side = "L" if dev == left_guid else "R"
            if args.stick == "gf":
                # GF: monikers ≈ template group names; the mapper also handles
                # the moniker-less camera axes + tempo-leaf normalization.
                control, seed_group = gf_control_and_seed(mon, side, itype, iid)
                if seed_group is _GF_UNMAPPED:
                    seed_group = None
                    unmapped.append((dev, itype, iid, mon))
            elif args.stick == "vmax":
                # VMAX: buttons = moniker verbatim (.pm kept, tempo leaves
                # stripped); axes table-driven. Takes the full moniker list.
                control, seed_group = vmax_control_and_seed(
                    rec["mons"], side, itype, iid)
                if seed_group is _GF_UNMAPPED:
                    seed_group = None
                    unmapped.append((dev, itype, iid, mon))
            elif args.stick == "moza":
                # MOZA: buttons = moniker verbatim (tempo/double-tap leaves
                # stripped); axes table-driven. Takes the full moniker list.
                control, seed_group = moza_control_and_seed(
                    rec["mons"], side, itype, iid)
                if seed_group is _GF_UNMAPPED:
                    seed_group = None
                    unmapped.append((dev, itype, iid, mon))
            elif mon:
                a = moniker_to_cluster(mon, side)
                if a == "__AXIS__":
                    control = None
                elif a is None:
                    control = None
                    unmapped.append((dev, itype, iid, mon))
                else:
                    control = mon
                    # SOL-R: dotted direction suffix stripped to the group base.
                    seed_group = a.split(".")[0]
        else:
            # em-dash path: first description yielding an etched name, preferring
            # the "<CLUSTER>[ [Mode]] — <text>" bridge over bare monikers.
            control = None
            ordered = sorted(rec["descs"], key=lambda d: 0 if d and "—" in d else 1)
            for d in ordered:
                e = parse_etched(d)
                if e:
                    control = e
                    break
            # em-dash control IS the cluster, so it's its own seed group.
            seed_group = control
        # dedup vjoy slots, prefer device 1 buttons
        seen_v, vlist = set(), []
        for v in rec["vjoys"]:
            sig = (v["device"], v["id"], v["type"])
            if sig not in seen_v:
                seen_v.add(sig)
                vlist.append(v)
        devices.setdefault(dev, []).append({
            "index": int(iid) if iid.isdigit() else iid,
            "type": itype,
            "control": control,
            "seed_group": seed_group,
            "vjoy": vlist,
        })

    out = {}
    for dev, entries in devices.items():
        entries.sort(key=lambda e: (e["type"], e["index"] if isinstance(e["index"], int) else 999))
        if args.monikers:
            role = "left-stick" if dev == left_guid else "right-stick"
        else:
            # infer device role from the dominant -L / -R control-name suffix
            l = sum(1 for e in entries if e["control"] and e["control"].rstrip().endswith("-L"))
            r = sum(1 for e in entries if e["control"] and e["control"].rstrip().endswith("-R"))
            role = "left-stick" if l >= r else "right-stick"
        out[role] = {"device_guid": dev, "inputs": entries}

    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    # coverage summary + unmapped report to stderr
    for role, d in out.items():
        named = sum(1 for e in d["inputs"] if e["control"])
        print(f"{role}: {named}/{len(d['inputs'])} inputs have a control name",
              file=sys.stderr)
    if unmapped:
        print(f"UNMAPPED monikers ({len(unmapped)}) — review:", file=sys.stderr)
        for dev, it, iid, mon in unmapped:
            side = "L" if dev == left_guid else "R"
            print(f"  {side} {it} {iid}: {mon}", file=sys.stderr)


if __name__ == "__main__":
    main()
