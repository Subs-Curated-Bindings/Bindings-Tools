# tools/

Maintenance and authoring scripts for the Curated Bindings repo. Most are
Python (3.10+ assumed); one PowerShell helper for the MFD-fix workflow.

All scripts are read-mostly except `load-layout-to-actionmaps.py`, which
modifies the live SC `actionmaps.xml`. None of them touch the GitHub repo
state -- they work on local files.

## What's in here

| Script | What it does |
|---|---|
| [r13_to_r14.py](r13_to_r14.py) | One-shot Joystick Gremlin R13 → R14 profile converter. Built for the 2026-05 conversion sprint. Auto-writes a sidecar report to `<output_dir>/#Assets/<output_stem>.report.txt`. |
| [load-layout-to-actionmaps.py](load-layout-to-actionmaps.py) | Copies a stick's layout XML into SC's `controls\mappings\` and rewrites the live `actionmaps.xml` from the layout body, bypassing SC's profile-import path (which has the `vehicle_mfd` wipe bug). Backs up actionmaps.xml first. SC must be fully closed. |
| [build-distribution-zip.py](build-distribution-zip.py) | Builds the user-facing release zip for a stick folder. Includes everything except `#Assets/`, `Thumbs.db`, and `*.af~lock~`. Output lands in `<stick-folder>/#Assets/<zip-name>.zip`. |
| [audit-jg-profile.py](audit-jg-profile.py) | Structural audit on a JG R14 profile: XML well-formedness, unique IDs, no missing references, no forward references, response-curve ordering invariant, orphan library actions. Run after any structural edit. Exits non-zero on any failure. |
| [audit-action-labels.py](audit-action-labels.py) | Reports which compound actions in a JG profile have generic vs custom `action-label` values, with length warnings against the project's ~80-char target / 100-char ceiling. See `references/jg-action-labels.md` in the skill. |
| [inspect-action-context.py](inspect-action-context.py) | Dumps per-action context (driving physical input, paired siblings, type-specific details) for compound actions in a JG profile. Useful when authoring action-labels in bulk -- gives the "what does this do, where does it live" view without clicking through JG's UI. |
| [remove-orphan-actions.py](remove-orphan-actions.py) | Removes orphan library actions from a JG R14 profile (defined-but-unreferenced entries that JG's UI tends to leave behind when an action is replaced). Safe by definition. Supports `--dry-run`. |
| [apply-action-labels.py](apply-action-labels.py) | Applies a JSON map of `{action-id: label}` to a JG profile in bulk. Action IDs may be full UUIDs or unique short prefixes. Refuses labels >150 chars, warns on >100. Companion to the audit + inspect scripts: audit finds the gaps, inspect gathers context, you author labels in JSON, this applies them. |
| [set-startup-mode.py](set-startup-mode.py) | Rewrites the `<startup-mode>` value in a JG profile's `<settings>` block. Verifies the target mode is declared in `<modes>` (or accepts the literal `"Use Heuristic"`). |
| [check-ps1-syntax.ps1](check-ps1-syntax.ps1) | AST sanity check for a PowerShell script. Reports parse errors without executing it. Used to verify MFD-fix scripts (`Fix MFD Binds [...].ps1`) before shipping. PowerShell 5.1's no-BOM-UTF-8 → CP-1252 misread bug makes this worth running on every script edit. |

## Typical workflows

### Polish a stick's JG profile (orphan cleanup, missing labels, startup mode)

Validated against SOL-R 2 and NXT on 2026-05-07. Run from this folder:

```bash
PROFILE="../[Enhanced] Dual TM SOL-R/Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][PTU][R14].xml"

# 1. Check what's there
python audit-jg-profile.py "$PROFILE"
python audit-action-labels.py "$PROFILE"

# 2. Remove orphan library actions (safe -- nothing references them by definition)
python remove-orphan-actions.py "$PROFILE" --dry-run    # preview
python remove-orphan-actions.py "$PROFILE"              # apply

# 3. Gather context for the actions still showing generic labels
python inspect-action-context.py "$PROFILE" --type response-curve
python inspect-action-context.py "$PROFILE" --type change-mode

# 4. Author labels in a JSON file (action-id -> label string)
#    Use the audit-action-labels.py output to find the IDs.
#    Use inspect-action-context.py output to write meaningful labels.

# 5. Apply
python apply-action-labels.py "$PROFILE" labels.json --dry-run
python apply-action-labels.py "$PROFILE" labels.json

# 6. Force a deterministic startup mode if the user has one
python set-startup-mode.py "$PROFILE" "SCM Mode"

# 7. Re-audit to confirm clean
python audit-jg-profile.py "$PROFILE"
python audit-action-labels.py "$PROFILE"

# 8. Rebuild the distribution zip so end-users get the polished profile
python build-distribution-zip.py \
    --stick-folder "../[Enhanced] Dual TM SOL-R" \
    --zip-name "[4.8.0][PTU][ENH] TM SOL-R 2 Binds.zip"
```

Step 8 is mandatory: any commit that touches a stick's source files must
also rebuild the `#Assets/` zip in the same commit, otherwise the zip in
the repo silently lags the source.

### After a Star Citizen patch — sync layout to live actionmaps

```bash
# Drop the new layout into SC's mappings folder + inject binds into actionmaps.
# SC must be fully closed (this script does not enforce that).
python load-layout-to-actionmaps.py \
    --layout "../[Enhanced] Dual TM SOL-R/layout_ENH_SOL-R2_480_PTU_exported.xml" \
    --channel PTU
```

## Conventions

- All scripts default-print to stdout; nothing is written silently.
- File modifications always create a timestamped backup adjacent to the target
  (`actionmaps.xml.bak-yyyyMMdd-HHmmss`).
- Path arguments accept absolute paths only -- relative paths break under
  Windows UNC mounts.
- Encoding behavior: scripts that touch `actionmaps.xml` and stick layout XMLs
  preserve no-BOM + CRLF (matches what SC writes). The JG R14 profile XML is
  saved with UTF-8 BOM by JG; scripts that edit it preserve the BOM.

## Adding a new script

1. Self-contained Python or PowerShell file in this directory.
2. Module docstring at the top describes what it does and how to invoke it.
3. Add a row to the table above.
4. Keep one-time / stick-specific operations (audio file renames, hardcoded
   label batches) out of this directory -- they're not reusable. Capture the
   workflow in the relevant skill reference instead.
