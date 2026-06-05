#!/usr/bin/env python3
"""
Extract a {physical input -> control name} table from an R14 JG profile.

This is the bridge the interactive chart needs to support a NO-JG upload:
the chart is keyed to vJoy slots, but a non-JG user's layout.xml references
PHYSICAL buttons. This table maps each physical input id -> the etched control
name (from the profile's <action type="description"> bridge), and also records
the vJoy slot(s) that physical input emits (the physical->vJoy half of the
bridge that the JG profile owns).

Source of truth: the JG profile's description actions, written in the
em-dash convention "<etched-name>[ [Mode]] — <chart text>".

Output JSON keyed by device role (left-stick / right-stick), each a list of
{ index, type, control, vjoy } entries.

Usage:
  py tools/extract-physical-control-map.py "<JG profile>.xml" [-o out.json]
"""
import sys, json, re, argparse
import xml.etree.ElementTree as ET

CHILD_CONTAINERS = ("actions", "short-actions", "long-actions",
                    "single-actions", "double-actions")


def prop(action, name):
    """Return the <value> of the named <property> child, or None."""
    for p in action.findall("property"):
        n = p.find("name")
        v = p.find("value")
        if n is not None and n.text == name:
            return v.text if v is not None else None
    return None


def walk(action_id, lib, seen, descriptions, vjoys):
    """Recursively collect description text + vJoy slots reachable from an id."""
    if action_id in seen or action_id not in lib:
        return
    seen.add(action_id)
    act = lib[action_id]
    atype = act.get("type")
    if atype == "description":
        val = prop(act, "description")
        if val:
            descriptions.append(val)
    elif atype in ("map-to-vjoy", "vjoy"):
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
                walk(aid.text, lib, seen, descriptions, vjoys)


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
    args = ap.parse_args()

    with open(args.profile, "r", encoding="utf-8", newline="") as fh:
        tree = ET.parse(fh)
    root = tree.getroot()

    # library: id -> action element
    lib = {a.get("id"): a for a in root.iter("action") if a.get("id")}

    # physical inputs: collect per (device, type, index) across all modes
    inputs = {}
    for inp in root.iter("input"):
        dev = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = inp.findtext("input-id")
        if dev is None or iid is None:
            continue
        cfg = inp.find("action-configuration")
        if cfg is None:
            continue
        rootact = cfg.findtext("root-action")
        key = (dev, itype, iid)
        rec = inputs.setdefault(key, {"descs": [], "vjoys": []})
        if rootact:
            walk(rootact, lib, set(), rec["descs"], rec["vjoys"])

    # collapse per device
    devices = {}
    for (dev, itype, iid), rec in inputs.items():
        # pick the first description that yields a non-empty etched name,
        # PREFERRING the em-dash cluster-bridge form ("<CLUSTER>[ [Mode]] —
        # <text>") over bare bottom-tier action-label monikers (which carry no
        # cluster identity). A stable sort keeps original order within each
        # group, so the first bridge wins; bare monikers are only a fallback.
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

    # infer device role from the dominant -L / -R suffix of its control names
    out = {}
    for dev, entries in devices.items():
        entries.sort(key=lambda e: (e["type"], e["index"] if isinstance(e["index"], int) else 999))
        l = sum(1 for e in entries if e["control"] and e["control"].rstrip().endswith("-L"))
        r = sum(1 for e in entries if e["control"] and e["control"].rstrip().endswith("-R"))
        role = "left-stick" if l >= r else "right-stick"
        out[role] = {"device_guid": dev, "inputs": entries}

    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        # quick coverage summary to stderr
        for role, d in out.items():
            named = sum(1 for e in d["inputs"] if e["control"])
            print(f"{role}: {named}/{len(d['inputs'])} inputs have a control name",
                  file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
