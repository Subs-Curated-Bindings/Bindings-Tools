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
  * --monikers: control name = the chart cluster the input's PHYSICAL MONIKER
    maps to (leading bare token on an action-label: L30.up, L-SW-1.up, ...).
    SOL-R 2 dropped its em-dash bridges in favour of monikers (2026-06-05), so
    its control map must be extracted this way.

Output JSON keyed by device role (left-stick / right-stick), each a list of
{ index, type, control, vjoy } entries.

Usage:
  py tools/extract-physical-control-map.py "<JG profile>.xml" [-o out.json]
  py tools/extract-physical-control-map.py "<SOL-R>.xml" --monikers -o out.json
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
    if base == "L-Z-Axis":
        return "L-THROTTLE"
    if base in ("ANALOG-HAT-L", "ANALOG-HAT-R"):
        return base
    if re.match(r"^[LR]-ANALOG$", base) or re.match(r"^[LR]-(X|Y)-Rotation$", base):
        return f"ANALOG-HAT-{side}"
    if re.match(r"^[LR]-SCROLL$", base):
        return mon            # L-SCROLL.up etc. — own bind, no cluster
    if re.match(r"^BTN$", base):
        return mon            # BTN.35 / BTN.39
    if (re.match(r"^[LR]-(X|Y|Z)-Axis$|^[LR]-Z-Rotation$"
                 r"|^[LR]-(Slider|Dail|Dial)(-[12])?$", base)
            or base == "R-stick"):
        return "__AXIS__"     # hidden main flight axis / spare slider — not charted
    return None               # unmapped — report, leave null


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
                    help="derive control names from physical monikers (SOL-R), "
                         "not em-dash description bridges")
    args = ap.parse_args()

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
            # control = the chart cluster the input's first physical moniker maps
            # to. Hidden axes and unmapped monikers resolve to a null control.
            control = None
            mon = rec["mons"][0] if rec["mons"] else None
            if mon:
                side = "L" if dev == SOLR_LEFT_GUID else "R"
                a = moniker_to_cluster(mon, side)
                if a == "__AXIS__":
                    control = None
                elif a is None:
                    control = None
                    unmapped.append((dev, itype, iid, mon))
                else:
                    control = a
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
            "vjoy": vlist,
        })

    out = {}
    for dev, entries in devices.items():
        entries.sort(key=lambda e: (e["type"], e["index"] if isinstance(e["index"], int) else 999))
        if args.monikers:
            role = "left-stick" if dev == SOLR_LEFT_GUID else "right-stick"
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
            side = "L" if dev == SOLR_LEFT_GUID else "R"
            print(f"  {side} {it} {iid}: {mon}", file=sys.stderr)


if __name__ == "__main__":
    main()
