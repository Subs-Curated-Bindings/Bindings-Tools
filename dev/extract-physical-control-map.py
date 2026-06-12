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
mapping) pair: `solr` (default, TM SOL-R 2) or `gf` (dual VKB Gunfighter,
migrated 2026-06-11 `367ac23`). GF specifics: monikers match the chart's
per-direction bind.X groups nearly 1:1 (tempo-leaf `.tap`/`.hold` suffixes are
stripped to the base moniker); the A1 ministick's button-mode enumeration
(buttons 16-19) is excluded — its bound path is the POV hat (vjoy hat 1
SCM / hat 2 Modifier), which fans to the same `<S>-A1.<dir>` anchors at
generate time; button 20 (`<S>-A1.press-in`) IS charted (its template group
exists; unbound paints "Unbound"); main-flight axes (X/Y/Z) are hidden; the
mouse-camera axes (R 4/5, quoted labels with no moniker) fall back to the JG
HID axis name (`R-X-Rotation` / `R-Y-Rotation`) so the labeled camera rows get
a charted anchor instead of colliding on device-agnostic `axis.N`.

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
    # A1 ministick. Button-mode enumeration (16-19) is excluded — the bound
    # path is the POV hat, which fans to the same <S>-A1.<dir> anchors at
    # generate time. The press (button 20) IS its own charted control.
    if re.match(r"^[LR]-A1$", base) and itype == "button":
        return (mon, mon) if suf == "press-in" else (None, None)
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
    ap.add_argument("--stick", choices=("solr", "gf"), default="solr",
                    help="which stick's moniker→seed mapping + left GUID to "
                         "use in --monikers mode (default: solr)")
    args = ap.parse_args()
    left_guid = GF_LEFT_GUID if args.stick == "gf" else SOLR_LEFT_GUID

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
