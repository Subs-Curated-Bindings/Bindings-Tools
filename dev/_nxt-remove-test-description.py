"""
One-off: remove Sub's test description action (id=2d68df0a-...) from the JG profile.
Also removes its action-id reference from root action 0014759d's <actions> list.

This fixes a JG R14 vjoy-acquisition error caused by the description action being
processed as the FIRST child of an axis root (before the response-curve). The
test description was working pre-fix-library-order because it was a forward ref
that JG silently skipped — once the forward ref was resolved, JG started
processing the description and the axis chain broke.

Text-based edit to preserve formatting.
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

JG_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml"
TEST_DESC_ID = "2d68df0a-f1b1-460c-9ddf-5066b41aa2b3"


def main():
    with open(JG_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    # Remove the <action-id>UUID</action-id> reference (anywhere it appears)
    ref_pattern = re.compile(
        r"\s*<action-id>" + re.escape(TEST_DESC_ID) + r"</action-id>"
    )
    n_refs = len(ref_pattern.findall(text))
    text = ref_pattern.sub("", text)

    # Remove the action definition block itself
    # Match the entire <action id="UUID" type="description">...</action> block
    block_pattern = re.compile(
        r"\s*<action id=\"" + re.escape(TEST_DESC_ID) + r"\"[^>]*>.*?</action>",
        re.DOTALL,
    )
    n_blocks = len(block_pattern.findall(text))
    text = block_pattern.sub("", text)

    # Validate XML still parses
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: result fails XML parse: {e}", file=sys.stderr)
        sys.exit(1)

    with open(JG_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"Removed test-description action-id references: {n_refs}")
    print(f"Removed test-description action blocks: {n_blocks}")


if __name__ == "__main__":
    main()
