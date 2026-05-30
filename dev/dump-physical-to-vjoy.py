"""
Dump the physical-button -> virtual-(vJoy)-button map from a JG R14 profile.

JG stores this as a two-hop chain, not a flat line:
  <input> (device-id + mode + input-id = PHYSICAL button)
     -> <root-action> UUID
          -> <action type="map-to-vjoy"> (vjoy-device-id + vjoy-input-id = VIRTUAL button)
Tempos (short/long-actions) and macros (macro-action type="vjoy") are descended too.

This is the same pairing JG's editor shows (physical on the left, virtual on the right).

Usage:
  python dump-physical-to-vjoy.py "<path to JG profile.xml>" [--mode "SCM Mode"] [--axes]
"""
import argparse
import sys
import xml.etree.ElementTree as ET


def prop(el, name):
    """Return the <value> of a <property> child whose <name> matches."""
    for p in el.findall("property"):
        n = p.find("name")
        v = p.find("value")
        if n is not None and n.text == name and v is not None:
            return v.text
    return None


def collect_vjoy(action_id, lib, seen=None):
    """Walk an action subtree, returning list of (vjoy_device, vjoy_button, path)."""
    if seen is None:
        seen = set()
    if action_id in seen:
        return []
    seen.add(action_id)
    act = lib.get(action_id)
    if act is None:
        return []
    atype = act.get("type")
    out = []

    if atype == "map-to-vjoy":
        vtype = prop(act, "vjoy-input-type")  # button or axis
        out.append((prop(act, "vjoy-device-id"), prop(act, "vjoy-input-id"), vtype, "always"))

    # root: <actions> list of <action-id>
    for container, tag in (("actions", "always"), ("short-actions", "tap"), ("long-actions", "hold")):
        cont = act.find(container)
        if cont is not None:
            for aid in cont.findall("action-id"):
                for d, b, vt, _ in collect_vjoy(aid.text, lib, seen):
                    out.append((d, b, vt, tag))

    # macro vjoy sub-actions (press emissions only -> value True)
    for ma in act.findall("macro-action"):
        if ma.get("type") == "vjoy" and prop(ma, "input-type") == "button" and prop(ma, "value") == "True":
            out.append((prop(ma, "vjoy-id"), prop(ma, "input-id"), "button", "macro"))

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--mode", help="only this JG mode (e.g. 'SCM Mode')")
    ap.add_argument("--axes", action="store_true", help="include axis inputs too")
    ap.add_argument("--csv", action="store_true", help="emit CSV (one row per vjoy emission) to stdout")
    args = ap.parse_args()

    tree = ET.parse(args.profile)
    root = tree.getroot()

    # device-id -> friendly name
    devs = {}
    for d in root.iter("device"):
        did = d.find("device-id")
        dn = d.find("device-name")
        if did is not None and dn is not None:
            devs[did.text] = (dn.text or "").strip()

    # library: id -> action element
    lib = {}
    libroot = root.find("library")
    if libroot is not None:
        for a in libroot.findall("action"):
            lib[a.get("id")] = a

    rows = []
    for inp in root.iter("input"):
        itype = inp.find("input-type").text
        if itype != "button" and not args.axes:
            continue
        did = inp.find("device-id").text
        mode = inp.find("mode").text
        iid = inp.find("input-id").text
        if args.mode and mode != args.mode:
            continue
        ra = inp.find("action-configuration/root-action")
        targets = collect_vjoy(ra.text, lib) if ra is not None else []
        vjoys = [t for t in targets if t[0] is not None]
        rows.append((devs.get(did, did), mode, itype, int(iid), vjoys))

    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

    if args.csv:
        import csv
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(["device_name", "mode", "input_type", "physical_input",
                    "vjoy_device", "vjoy_input_type", "vjoy_input_id", "path"])
        for dev, mode, itype, iid, vjoys in rows:
            if vjoys:
                for d, b, vt, path in vjoys:
                    w.writerow([dev, mode, itype, iid, d, vt, b, path])
            else:
                w.writerow([dev, mode, itype, iid, "", "", "", "no-output"])
        return

    cur = None
    for dev, mode, itype, iid, vjoys in rows:
        hdr = (dev, mode)
        if hdr != cur:
            print(f"\n=== {dev}  |  mode: {mode} ===")
            cur = hdr
        if vjoys:
            mapped = ", ".join(
                f"vjoy{d} {vt} {b}" + ("" if path == "always" else f" [{path}]")
                for d, b, vt, path in vjoys
            )
        else:
            mapped = "(no vjoy output)"
        print(f"  physical {itype} {iid:>3}  ->  {mapped}")


if __name__ == "__main__":
    main()
