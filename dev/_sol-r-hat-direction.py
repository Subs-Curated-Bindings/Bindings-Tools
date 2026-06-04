#!/usr/bin/env python3
"""SOL-R hat direction tagging — collaboration helper.

The four 4-way hats are groups of separate buttons (no native direction), so
the chart generator's split keys them `<cluster>.b<N>`. Sub wants the direction
appended (`<cluster>.b<N>.down`). Direction only lives in his head, so:

  --placeholder : append a `.xx` direction placeholder to each hat button's
      SCM-layer description etched-name (`4WAY-HAT-R-40` → `4WAY-HAT-R-40.xx`).
      Sub then opens the profile in JG and edits `.xx` → `.up`/`.down`/`.left`/
      `.right`/`.press` etc. on the SCM layer only. Idempotent: descriptions
      that already carry a direction suffix are left alone.

  --extrapolate : after Sub's edits, copy each hat button's SCM-layer direction
      onto that same physical button's descriptions in every other mode, so all
      layers agree. Pass --apply to write (default is a dry-run preview).

Preserves the profile's line endings (newline="").
"""
import sys, re, argparse
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
HAT = r"4WAY-HAT-[LR]-\d+"


def read():
    return JG.read_text(encoding="utf-8", newline="")


def write(text):
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def placeholder():
    # Match a hat cluster directly followed by " — " (SCM layer; mode-tagged
    # layers read " [Mode] — " and don't match) where there's no existing
    # `.suffix` — so re-runs and already-edited descriptions are untouched.
    pat = re.compile(r"(<value>)(" + HAT + r")( — )")
    text = read()
    new, n = pat.subn(r"\1\2.xx\3", text)
    write(new)
    print(f"Appended .xx to {n} SCM hat description(s).")


def _input_descs(root):
    """(device,type,id) → [(mode, full_description_value_string)]."""
    by_id = {a.get("id"): a for a in root.iter("action")}

    def desc_action(aid, seen=None):
        seen = seen or set()
        if aid in seen:
            return None
        seen.add(aid)
        a = by_id.get(aid)
        if a is None:
            return None
        if a.get("type") == "description":
            return a
        for sub in a.iter("action-id"):
            r = desc_action(sub.text, seen)
            if r:
                return r
        return None

    def val(action):
        for p in action.findall("property"):
            if (p.findtext("name") or "") == "description":
                v = p.find("value")
                return v.text if v is not None else None
        return None

    out = {}
    for inp in root.iter("input"):
        ac = inp.find("action-configuration")
        rootid = ac.findtext("root-action") if ac is not None else None
        if not rootid:
            continue
        d = desc_action(rootid)
        if d is None:
            continue
        v = val(d)
        if not v or not re.match(r"^" + HAT, v):
            continue
        key = (inp.findtext("device-id"), inp.findtext("input-type"), inp.findtext("input-id"))
        out.setdefault(key, []).append((inp.findtext("mode"), v))
    return out


def extrapolate(apply):
    text = read()
    root = ET.fromstring(text)
    descs = _input_descs(root)
    suffix_re = re.compile(r"^(" + HAT + r")\.([a-z][a-z-]*)\b")

    repls = []  # (old_full_value, new_full_value)
    unresolved = []
    for key, entries in descs.items():
        scm = next((v for (m, v) in entries if m == "SCM Mode"), None)
        if scm is None:
            continue
        mm = suffix_re.match(scm)
        if not mm or mm.group(2) == "xx":
            unresolved.append((key, scm.split(" — ")[0]))
            continue
        cluster, direction = mm.group(1), mm.group(2)
        for (mode, v) in entries:
            if mode == "SCM Mode":
                continue
            # set/replace the cluster's direction suffix, keep the rest verbatim
            nv = re.sub(r"^(" + re.escape(cluster) + r")(\.[a-z][a-z-]*)?", f"{cluster}.{direction}", v, count=1)
            if nv != v:
                repls.append((v, nv))

    print(f"{len(repls)} non-SCM hat description(s) to update.")
    if unresolved:
        print(f"{len(unresolved)} hat input(s) still on `.xx` (not yet assigned):")
        for key, etched in unresolved:
            print(f"   {key[1]} id={key[2]}  {etched}")
    for old, new in repls[:8]:
        print(f"   {old.split(' — ')[0]}  ->  {new.split(' — ')[0]}")
    if apply and repls:
        for old, new in repls:
            text = text.replace(f"<value>{old}</value>", f"<value>{new}</value>")
        write(text)
        print("APPLIED.")
    elif not apply:
        print("(dry-run — pass --apply to write)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--placeholder", action="store_true")
    ap.add_argument("--extrapolate", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.placeholder:
        placeholder()
    elif args.extrapolate:
        extrapolate(args.apply)
    else:
        ap.print_help()
        sys.exit(1)
