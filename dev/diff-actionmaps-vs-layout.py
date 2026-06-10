#!/usr/bin/env python3
"""Semantic diff between the live SC actionmaps.xml and a stick's layout XML.

This is the read side of the "harvest in-game bind edits back into the layout"
workflow: Sub rebinds in-game, SC flushes the changes to actionmaps.xml, and we
compare against the repo layout to see exactly which (actionmap, action) pairs
diverged so they can be folded back in.

Unlike the coarse "fewest changed lines" diff used to identify which stick is
loaded, this compares per (actionmap, action) and captures each rebind's INPUT
*and* its trailing attributes (activationMode / multiTap). That matters because
an attribute-only edit — e.g. dropping double_tap from a bind whose input is
unchanged — is a real change a line-count diff would under-report.

Only joystick rebinds (input starts with "js") are compared; keyboard/mouse
rebinds and the <options> block are ignored.

Usage:
    python tools/diff-actionmaps-vs-layout.py --layout "<stick>/layout_*.xml" [--channel LIVE]
    python tools/diff-actionmaps-vs-layout.py --layout "<...>" --actionmaps "<path to actionmaps.xml>"

Exit code is 0 when there are no differences, 1 when there are (handy in scripts).
"""
import argparse
import re
import sys

DEFAULT_ACTIONMAPS = (
    r"C:\Program Files\Roberts Space Industries\StarCitizen"
    r"\{channel}\user\client\0\Profiles\default\actionmaps.xml"
)


def parse(path):
    """Return {(actionmap, action): [(input, ((attr, val), ...)), ...]} for js* rebinds."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    binds = {}
    for am in re.finditer(r'<actionmap name="([^"]+)">(.*?)</actionmap>', text, re.S):
        amname, body = am.group(1), am.group(2)
        for ac in re.finditer(
            r'<action name="([^"]+)">(.*?)</action>|<action name="([^"]+)"\s*/>', body, re.S
        ):
            acname = ac.group(1) or ac.group(3)
            acbody = ac.group(2) or ""
            for rb in re.finditer(r"<rebind\s+([^/>]*?)/?>", acbody):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', rb.group(1)))
                inp = attrs.get("input", "")
                if not inp.startswith("js"):
                    continue
                extra = tuple(sorted((k, v) for k, v in attrs.items() if k != "input"))
                binds.setdefault((amname, acname), []).append((inp, extra))
    return binds


def fmt(binds):
    if not binds:
        return "(absent)"
    parts = []
    for inp, extra in sorted(binds):
        if extra:
            parts.append(inp + " [" + ", ".join(f"{k}={v}" for k, v in extra) + "]")
        else:
            parts.append(inp)
    return ", ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", required=True, help="path to the stick's layout_*.xml")
    ap.add_argument("--channel", default="LIVE", help="SC channel (default LIVE; all symlink to one install)")
    ap.add_argument("--actionmaps", help="explicit actionmaps.xml path (overrides --channel)")
    args = ap.parse_args()

    am_path = args.actionmaps or DEFAULT_ACTIONMAPS.format(channel=args.channel)

    live = parse(am_path)
    layout = parse(args.layout)

    diffs = []
    for k in sorted(set(live) | set(layout)):
        lv, ly = sorted(live.get(k, [])), sorted(layout.get(k, []))
        if lv != ly:
            diffs.append((k, ly, lv))

    print(f"live={sum(len(v) for v in live.values())} binds / {len(live)} actions; "
          f"layout={sum(len(v) for v in layout.values())} binds / {len(layout)} actions; "
          f"differing actions={len(diffs)}")
    print()
    for (am, ac), ly, lv in diffs:
        print(f"{am} / {ac}")
        print(f"  layout: {fmt(ly)}")
        print(f"  live:   {fmt(lv)}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
