#!/usr/bin/env python3
"""
Clear every joystick bind in a live actionmaps.xml, in place.

Surgical: converts each <rebind input="js1_*"/> / <rebind input="js2_*"/> to
SC's native unbound-joystick placeholder <rebind input="js2_ "/>. Keyboard
(kb1_), mouse (mo1_), gamepad (gp1_) rebinds, all <options>/<deviceoptions>
blocks, and the file wrapper are left byte-identical.

Why placeholders, not deletion: SC represents a cleared joystick bind by keeping
the <rebind> element with an empty input (trailing-space form), not by removing
it. The 2026-05-07 verified-clean baseline uses js2_  placeholders universally.

Backs up the target to actionmaps.xml.bak-<ts> before writing. SC + RSI Launcher
must be fully closed (edits while running are silently overwritten on next save).

Usage:
  py tools/clear-joystick-binds.py <path to actionmaps.xml>
  py tools/clear-joystick-binds.py <path> --dry-run
"""
import sys, re, shutil, datetime, argparse

PLACEHOLDER = '<rebind input="js2_ "/>'
# match a joystick rebind element on js1 or js2, bound or already-placeholder.
# [^/>]* swallows any trailing attributes (multiTap="2", activationMode="...")
# so double-tap / press variants aren't missed (skill warns about this).
JS_REBIND = re.compile(r'<rebind input="js[12]_[^"]*"[^/>]*/>')
# a rebind is already unbound if its input button is empty (js1_ / js2_ )
UNBOUND = re.compile(r'<rebind input="js[12]_ "')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("actionmaps")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.actionmaps, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    matches = JS_REBIND.findall(text)
    total = len(matches)
    already = sum(1 for m in matches if UNBOUND.match(m))
    bound = total - already

    print(f"joystick rebinds found : {total}")
    print(f"  currently bound      : {bound}  (will be cleared)")
    print(f"  already unbound      : {already}")

    if args.dry_run:
        print("\n-- dry run, no file written --")
        # show a sample of what changes
        for m in matches[:8]:
            if m != PLACEHOLDER:
                print(f"  {m}  ->  {PLACEHOLDER}")
        return

    new_text = JS_REBIND.sub(PLACEHOLDER, text)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{args.actionmaps}.bak-{ts}"
    shutil.copy2(args.actionmaps, backup)
    print(f"\nbacked up -> {backup}")

    with open(args.actionmaps, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    print(f"wrote     -> {args.actionmaps} ({len(new_text)} bytes)")

    # verify
    after = JS_REBIND.findall(new_text)
    still_bound = sum(1 for m in after if not UNBOUND.match(m))
    print(f"verify: {still_bound} joystick binds remain (expected 0)")
    print(f'        kb1 rebinds preserved: {new_text.count(chr(34) + "kb1_")}')
    print(f'        mo1 rebinds preserved: {new_text.count(chr(34) + "mo1_")}')


if __name__ == "__main__":
    main()
