# Bindings Toolkit (unified, stick-aware)

One PowerShell tool that handles the common Star Citizen binding-maintenance tasks for **every** supported stick. Replaces the old per-stick `Bindings Toolkit [ENH][…]` / `Fix MFD Binds` scripts.

## Run it

Double-click **`Bindings Toolkit.bat`** — it self-elevates (UAC) and runs the `.ps1` next to it.

On launch it figures out which stick you're on, in this order:

1. **`-Stick`** argument — `NXT` / `SOL-R` / `Gunfighter` / `VMAX` / `MOZA`
2. A **bundled marker** (set automatically when the toolkit ships inside a stick's download)
3. **Auto-detect** from the layout XML installed in your SC channels
4. A **menu** prompt (with the detected stick pre-selected)

## Operations

1. **Fix MFD binds** — reinjects the MFD binds SC's import wipes
2. **Reset axis inversions** — strips invert overrides so engine defaults reassert
3. **Clear all binds** — deletes `actionmaps.xml` (typed confirmation + backup)
4. **Restore from backup** — pick a timestamped backup to roll back to
5. **Diagnostic** — read-only state summary (safe to run anytime)
6. **Prune** — delete old `actionmaps.xml.bak-*` files

Every operation refuses to run while Star Citizen / the RSI Launcher is open, takes a timestamped backup before any change, and preserves the file's CRLF/BOM encoding.

## The registry

Each stick's only unique data is its MFD bind table, in `$Registry` at the top of the `.ps1`. When a stick's MFD vJoy slots change for a patch, update that stick's `Binds` block — everything else is shared.

> ℹ️ STECS STG + Gladiator NXT is WIP and not in the registry yet.

---

Part of **[SubliminalsTV Curated Bindings](https://github.com/Subs-Curated-Bindings)**.
