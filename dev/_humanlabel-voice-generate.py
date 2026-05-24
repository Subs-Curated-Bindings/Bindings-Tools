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
    "Boost": "After Burner",
    "Autoland": "Auto Land",
    "Spacebrake": "Space Brake",
    "Headlights (Toggle)": "Headlight Toggle",
    "Headlights": "Headlight",
}

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
]


def strip_paren_modifier_tags(s):
    """Drop (Press)/(Hold)/(Tap)/(Long Press)/(Short Press)/(Toggle) — these
    are [M]/[H]/[DT] modifier tags on chart, not part of the label name."""
    pat = r"\s*\((Press|Hold|Tap|Long Press|Short Press|Toggle|Toggle\s*/\s*Hold|abs|rel|hold|press|tap)\)\s*"
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
    """Strip leading section labels like 'Throttle - ', 'Bombs - ', 'Decoy - '."""
    s = re.sub(
        r"^(Throttle|Bombs|Decoy|Shield|Shields|Weapon|Weapons|Missiles?|EVA|Tool|MFD|Notifications?|Firearm|Cooler|Comm)\s*[-–]\s*",
        "",
        s,
    )
    return s


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


def voice_transform(xml_name, display_name):
    """Apply Sub's voice rules to produce a player-speak HumanLabel."""
    # 0. Compound-split overrides (when XML name has no word boundaries)
    if xml_name.lower() in COMPOUND_SPLITS:
        base = COMPOUND_SPLITS[xml_name.lower()]
        base = " ".join(w.capitalize() for w in base.split())
        return cap_sc_acronyms(base)

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
    base = base.strip("-").strip("/").strip()
    base = cap_sc_acronyms(base)
    return base


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
