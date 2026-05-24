"""
Generate voice-aligned HumanLabel proposals for the rows where the chart-text
matcher couldn't find a good match (source = csv_displayname OR xml_name_fallback).

Voice rules extracted from Sub's chart text (NXT / SOL-R / Gunfighter / Virpil / Moza):
  1. NEVER start with "Toggle" — always at end ("Door Toggle", "Cruise Control Toggle").
  2. Use compact abbreviations: Inc., Dec., Prev., PWR, REL., ABS.
  3. Direction at end for cycle/select actions ("Hostile Target Forward").
  4. Action verbs at front for transitive ops: Reset, Release, Set, Recenter, Cycle.
  5. Strip CIG verbosity in parens: (Press), (Hold), (Tap), (Long Press), (Short Press)
     — those are [M]/[H]/[DT] modifier tags on the chart, not in the label.
  6. Use SC player-speak renames:
       Boost → After Burner
       Autoland → Auto Land
       Spacebrake → Space Brake
       Headlights → Headlight (Sub uses singular)
  7. Slash for alternates / mode names CAPS: SCM Mode, NAV Mode, M/S Mode.
  8. Strip CIG section prefixes like "Cycle Lock - X - Direction" → "X Target Direction"
     and "Throttle - X" / "Bombs - X" → "X".
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings")
PROPOSALS = REPO / "tools" / "_humanlabel-proposals.json"
CSV_REF = REPO / "tools" / "_sc-keybinds-reference.csv"
OUT_JSON = REPO / "tools" / "_humanlabel-voice-proposals.json"

# Hand-curated SC player-speak renames (CIG-speak → Sub-speak)
RENAMES_EXACT = {
    "Autoland": "Auto Land",
    "Spacebrake": "Space Brake",
    "Headlights (Toggle)": "Headlight Toggle",
    "Headlights": "Headlight",
}

# XML-name driven renames: when XMLActionName contains the key,
# force the HumanLabel regardless of DisplayName. Lets us tell
# v_afterburner ("After Burner") apart from eva_boost ("Boost").
XML_NAME_LABELS = [
    (re.compile(r"afterburner", re.I), "After Burner"),
]

# SC acronyms — keep these uppercase in human labels.
SC_ACRONYMS = {
    "ESP", "IFCS", "NAV", "SCM", "MFD", "ATC", "ADS", "HUD", "VTOL", "EVA",
    "FOIP", "VOIP", "DOF", "QED", "EMP", "QID", "PIP", "VJOY", "ITS", "AIM",
    "FPS", "UI", "AI", "DPS", "TTK", "MS", "PVE", "PVP", "OKR", "PIT",
}

# Compound lowercase words to split — XMLActionNames like 'combathealtarget'
# don't have word boundaries; we add them here so the humanizer can split.
COMPOUND_SPLITS = {
    "combathealtarget": "combat heal target",
    "nextitem": "next item",
    "previtem": "prev. item",
    "nextweapon": "next weapon",
    "prevweapon": "prev. weapon",
    "thirdperson": "third person",
    "firstperson": "first person",
    "spectate_toggle_thirdperson": "spectate third person toggle",
    "attack1": "firearm attack",
    "attacksecondary": "tool secondary fire",
    "attackSecondary": "tool secondary fire",
    "toggleattachhelmet": "helmet equip toggle",
    "toggleAttachHelmet": "helmet equip toggle",
    "view_fstop_in": "camera f-stop inc.",
    "view_fstop_out": "camera f-stop dec.",
    "view_focus_in": "camera focus inc.",
    "view_focus_out": "camera focus dec.",
}

# Phrase-level rewrites — applied via substring
PHRASE_REWRITES = [
    (r"\bHeadlights\b", "Headlight"),
    (r"\bAfterburner\b", "After Burner"),
    (r"\bAutoland\b", "Auto Land"),
    (r"\bSpacebrake\b", "Space Brake"),
    (r"\bE\.V\.A\.\s*/\s*On Foot\b", "EVA/Foot"),
    # Targeting/pinning specific compound phrases — collapse to chart-style player speak
    # "Pin Index N - Pin / Unpin Selected Target" → "Pin/Unpin N"  (matches chart text Sub uses)
    (r"\bPin Index (\d+)\s*[-–]\s*Pin\s*/\s*Unpin Selected Target\b", r"Pin/Unpin \1"),
    # "Pin Index N - Lock / Unlock Pinned Target" → "Pin N Lock Toggle"
    (r"\bPin Index (\d+)\s*[-–]\s*Lock\s*/\s*Unlock Pinned Target\b", r"Pin \1 Lock Toggle"),
    # Generic "Pin Index N" → "Pin N" (catch any remaining)
    (r"\bPin Index (\d+)\b", r"Pin \1"),
    # Tight slash forms — Sub uses no spaces around / in chart text
    (r"\bPin\s*/\s*Unpin\b", "Pin/Unpin"),
    (r"\bLock\s*/\s*Unlock\b", "Lock/Unlock"),
    (r"\bOn\s*/\s*Off\b", "On/Off"),
    (r"\bLead\s*/\s*Lag\b", "Lead/Lag"),
    (r"\bFixed\s*/\s*Auto\b", "Fixed/Auto"),
]


def strip_paren_modifier_tags(s):
    """Drop (Press)/(Hold)/(Tap)/(Long Press)/(Short Press)/(Toggle) — these
    are [M]/[H]/[DT] modifier tags on chart, not part of the label name.
    PRESERVE (abs)/(rel) as ABS./REL. suffixes — those mark axis modes Sub
    uses in chart text (e.g. 'Mining Laser PWR ABS.')."""
    s = re.sub(r"\s*\(abs\)\s*", " ABS.", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(rel\)\s*", " REL.", s, flags=re.IGNORECASE)
    pat = r"\s*\((Press|Hold|Tap|Long Press|Short Press|Toggle|Toggle\s*/\s*Hold|hold|press|tap)\)\s*"
    s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def toggle_to_end(s):
    """'Toggle X' or 'X Toggle Y' → 'X Y Toggle'. Never start with Toggle.
    Also pulls a mid-string Toggle to the end so labels stay scannable."""
    # Start: 'Toggle X' → 'X Toggle'
    m = re.match(r"^Toggle\s+(.+)$", s)
    if m:
        return f"{m.group(1)} Toggle"
    # Mid: 'X Toggle Y' → 'X Y Toggle' (only when there's a Y to move it past)
    m = re.match(r"^(.+?)\s+Toggle\s+(.+)$", s)
    if m:
        return f"{m.group(1)} {m.group(2)} Toggle"
    return s


def cap_sc_acronyms(s):
    """Restore SC acronyms to all-caps. Word-boundary aware so 'navigation' isn't touched."""
    def fix(m):
        word = m.group(0)
        return word.upper() if word.upper() in SC_ACRONYMS else word
    return re.sub(r"\b[A-Za-z]{2,5}\b", fix, s)


def strip_cig_section_prefixes(s):
    """Strip leading section labels like 'Throttle - ', 'Bombs - ', 'Decoy - '.
    But NOT when the result would be a single word — keeping 'Shields Increase'
    is better than collapsing to 'Increase' which loses disambiguation."""
    m = re.match(
        r"^(Throttle|Bombs|Decoy|Shield|Shields|Weapon|Weapons|Missiles?|EVA|Tool|MFD|Notifications?|Firearm|Cooler|Comm)\s*[-–]\s*(.+)$",
        s,
    )
    if not m:
        return s
    prefix, rest = m.group(1), m.group(2).strip()
    # Count words in remainder; if 1 word, keep the prefix (collapse hyphen → space)
    if len(rest.split()) <= 1:
        return f"{prefix} {rest}"
    return rest


def transform_cycle_lock(s):
    """'Cycle Lock - Friendlies - Forward' → 'Friendly Target Forward'."""
    m = re.match(r"^Cycle\s+Lock\s*[-–]\s*(.+?)\s*[-–]\s*(.+)$", s)
    if not m:
        return s
    subj, dir_ = m.group(1).strip(), m.group(2).strip()
    if subj.lower() in ("friendlies", "friendly"):
        subj = "Friendly"
    elif subj.lower() in ("hostiles", "hostile"):
        subj = "Hostile"
    elif subj.lower() in ("attackers", "attacker"):
        subj = "Attacker"
    elif subj.lower() == "sub-target":
        subj = "Sub Target"
    elif subj.lower() in ("pinned",):
        subj = "Pinned"
    elif subj.lower() in ("in view",):
        subj = "In-View"
    if dir_.lower().startswith("reset"):
        dir_ = "Closest"
    return f"{subj} Target {dir_}"


def abbreviate(s):
    """Apply Sub's standard abbreviations."""
    s = re.sub(r"\bIncrease\b", "Inc.", s)
    s = re.sub(r"\bDecrease\b", "Dec.", s)
    s = re.sub(r"\bPrevious\b", "Prev.", s)
    return s


def apply_xml_decorators(xml_name, label):
    """Apply XML-name-driven label decorations:
      - `eva_` prefix in XML → "EVA " prefix on label (unless already present)
      - `_long` / `_hold` suffix in XML → "[H] " PREFIX on label. End users don't
        care whether the hold is implemented by SC (game-native, via _long/_hold)
        or by JG tempo — both show as [H] in chart, so the HumanLabel needs [H]
        wherever SC's action itself is hold-shaped.
      - `_short` suffix means the tap variant — no decoration; that's the base.
    """
    if not xml_name or not label:
        return label
    xml_low = xml_name.lower()
    out = label
    # Strip any pre-existing [H] suffix (legacy from when this was a suffix)
    out = re.sub(r"\s*\[H\]\s*$", "", out)
    # Game-native hold prefix
    if (xml_low.endswith("_long") or xml_low.endswith("_hold")) and "[H]" not in out:
        out = f"[H] {out}"
    # EVA prefix (applied after [H] so it ends up as "EVA [H] X" — wait no,
    # [H] should be the outermost prefix. Apply EVA first, then [H].)
    # Reorder: handle EVA first if not already present
    if xml_low.startswith("eva_") and not re.search(r"\bEVA\b", out):
        # Insert "EVA " after any "[H] " prefix
        if out.startswith("[H] "):
            out = f"[H] EVA {out[4:]}"
        else:
            out = f"EVA {out}"
    return out


def voice_transform(xml_name, display_name):
    """Apply Sub's voice rules to produce a player-speak HumanLabel."""
    # 0a. XML-name driven labels (lets us distinguish v_afterburner from eva_boost
    # even when both have DisplayName "Boost")
    for pat, label in XML_NAME_LABELS:
        if pat.search(xml_name or ""):
            return apply_xml_decorators(xml_name, label)

    # 0b. Compound-split overrides (when XML name has no word boundaries)
    if xml_name.lower() in COMPOUND_SPLITS:
        base = COMPOUND_SPLITS[xml_name.lower()]
        base = " ".join(w.capitalize() for w in base.split())
        return apply_xml_decorators(xml_name, cap_sc_acronyms(base))

    # 1. Start: prefer DisplayName if it's clean, otherwise humanize XMLActionName
    base = (display_name or "").strip()
    if not base or base.startswith("ui_") or base.startswith("@"):
        # Fallback: humanize XML name
        name = xml_name
        for p in ("v_", "ui_", "vehicle_"):
            if name.startswith(p):
                name = name[len(p):]; break
        for suffix in ("_long", "_short", "_hold", "_press"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]; break
        base = " ".join(p.capitalize() for p in name.replace("_", " ").split())

    # Pre-rename exact matches
    if base in RENAMES_EXACT:
        base = RENAMES_EXACT[base]

    # Phrase rewrites
    for pat, rep in PHRASE_REWRITES:
        base = re.sub(pat, rep, base, flags=re.IGNORECASE)

    # Strip paren modifier tags ((Press), (Hold), etc.)
    base = strip_paren_modifier_tags(base)

    # Special compound transforms
    base = transform_cycle_lock(base)
    base = strip_cig_section_prefixes(base)
    base = toggle_to_end(base)
    base = abbreviate(base)

    # Cleanup
    base = re.sub(r"\s+", " ", base).strip()
    base = base.strip("-").strip("/").strip(",").strip()
    base = cap_sc_acronyms(base)
    base = apply_xml_decorators(xml_name, base)
    return base


def voice_clean_existing(text, xml_name=None):
    """Apply Sub's voice rules to an already-named string (chart-sourced text).
    Conservative: only fixes clear violations (Toggle-at-start, trailing punctuation,
    acronym caps). Leaves correctly-voiced labels alone."""
    if not text:
        return text
    s = text.strip().strip(",").strip()  # trim trailing commas (SVG text glitch)
    # Toggle to end (start AND mid)
    m = re.match(r"^Toggle\s+(.+)$", s)
    if m:
        s = f"{m.group(1)} Toggle"
    m = re.match(r"^(.+?)\s+Toggle\s+(.+)$", s)
    if m:
        s = f"{m.group(1)} {m.group(2)} Toggle"
    # SC acronyms
    s = cap_sc_acronyms(s)
    # Strip CIG-paren modifier tags if they snuck through
    s = strip_paren_modifier_tags(s)
    # Dedupe adjacent identical words (chart-text concat artifact, e.g.
    # "Invoke Docking Docking Toggle" → "Invoke Docking Toggle")
    s = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    if xml_name:
        s = apply_xml_decorators(xml_name, s)
    return s


def main():
    with open(PROPOSALS, encoding="utf-8") as f:
        data = json.load(f)
    proposals = data["proposals"]

    # Pull ActionMap from canonical CSV for context
    by_xml = {}
    with open(CSV_REF, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            by_xml[r["XMLActionName"]] = r

    voice_drafts = {}
    for xml_name, p in proposals.items():
        if p["source"].startswith("chart"):
            continue  # leave chart-sourced alone
        disp = p.get("display_name", "")
        voiced = voice_transform(xml_name, disp)
        voice_drafts[xml_name] = {
            "xml_name": xml_name,
            "action_map": by_xml.get(xml_name, {}).get("ActionMap", ""),
            "display_name": disp,
            "current_proposal": p["proposal"],
            "voice_draft": voiced,
            "source": p["source"],
            "confidence": p["confidence"],
        }

    print(f"Generated {len(voice_drafts)} voice drafts (non-chart-sourced rows)")
    print()
    print("--- Sample by source ---")
    by_src = {"csv_displayname": [], "xml_name_fallback": []}
    for x, d in voice_drafts.items():
        by_src[d["source"]].append((x, d))
    for src, items in by_src.items():
        print(f"\n=== {src} ({len(items)}) — first 20 ===")
        for x, d in items[:20]:
            cur = (d["current_proposal"] or "")[:35]
            voi = (d["voice_draft"] or "")[:35]
            print(f"  {x:42s} disp={d['display_name'][:30]!r:32s} cur={cur!r:38s} voice={voi!r}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(voice_drafts, f, indent=2)
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
