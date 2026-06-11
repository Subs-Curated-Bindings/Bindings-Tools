#!/usr/bin/env python3
"""Port the NXT Bindings Toolkit -> SOL-R 2 toolkit.

Structural removals use NXT-spelled anchors and run BEFORE the global token
swaps. Every edit asserts its expected hit count. Preserves LF / no-BOM.
"""
import re

SRC = "[Enhanced] Dual VKB Gladiator NXT/Tools/Bindings Toolkit [ENH][NXT][4.8.1][LIVE].ps1"
DST = "[Enhanced] Dual TM SOL-R/Tools/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].ps1"

with open(SRC, "r", encoding="utf-8", newline="") as f:
    t = f.read()
assert "\r\n" not in t, "expected LF source"

def repl(old, new, n=1):
    global t
    c = t.count(old)
    assert c == n, f"expected {n} of <<{old[:55]}>>, found {c}"
    t = t.replace(old, new)

# ---- 1. Remove the whole Non-EVO axis-flip section (bar-anchored) ----
si = t.index("#  OPERATION: NON-EVO AXIS FLIP")
bar = t.rindex("\n# =", 0, si) + 1
ei = t.index("#  MAIN")
ebar = t.rindex("\n# =", 0, ei) + 1
t = t[:bar] + t[ebar:]

# ---- 2. Remove the two VKB-only diagnostic helper functions (exact text) ----
repl("""function Get-ConnectedVkbDevices {
    # VKB Sim vendor id is 231D. PnP enumerates each device twice (USB
    # surface + HID surface) so we dedupe by PID, which uniquely
    # identifies the stick model. Returns a hashtable: PID -> FriendlyName.
    $devs = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
        $_.InstanceId -match 'VID_231D' -and $_.Status -eq 'OK'
    })
    $byPid = @{}
    foreach ($d in $devs) {
        if ($d.InstanceId -match 'PID_([0-9A-Fa-f]{4})') {
            $vkbPid = $Matches[1].ToUpper()
            if (-not $byPid.ContainsKey($vkbPid)) {
                $byPid[$vkbPid] = $d.FriendlyName
            }
        }
    }
    return $byPid
}

""", "")
repl("""function Get-VkbConfiguratorPath {
    # Returns path to VKBDevCfg-C.exe if installed, $null otherwise.
    $candidates = @(
        'C:\\Program Files\\VKB Sim\\VKBDevCfg\\VKBDevCfg-C.exe',
        "${env:ProgramFiles(x86)}\\VKB Sim\\VKBDevCfg\\VKBDevCfg-C.exe",
        'C:\\Program Files\\VKBsim\\VKBDevCfg\\VKBDevCfg-C.exe',
        "${env:ProgramFiles(x86)}\\VKBsim\\VKBDevCfg\\VKBDevCfg-C.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

""", "")

# ---- 3. Replace the Diagnostic VKB-hardware block (vendor-agnostic) ----
repl("""    # --- Sticks: profile expectations vs connected VKB hardware (raw, pre-cloak) ---
    $profDevs = Get-ProfileDevices -ProfilePath $shipped
    $vkb      = Get-ConnectedVkbDevices
    $vkbPids  = @($vkb.Keys | Sort-Object)
    if ($profDevs.Count -eq 0) {
        Write-Host "  VKB hardware: profile declares no physical devices (check <devices> block in profile XML)" -ForegroundColor Yellow
    }
    elseif ($vkbPids.Count -eq 0) {
        Write-Host ("  VKB hardware: profile expects {0} VKB device(s), 0 connected -- plug them in, re-check" -f $profDevs.Count) -ForegroundColor Red
        foreach ($d in $profDevs) { Write-Host ("                expects: {0}" -f $d.Name) -ForegroundColor Gray }
    }
    else {
        $stickColour = if ($vkbPids.Count -ge $profDevs.Count) { 'Green' } else { 'Yellow' }
        Write-Host ("  VKB hardware: {0} stick(s) plugged in (PIDs: {1}); profile expects {2}" -f $vkbPids.Count, ($vkbPids -join ', '), $profDevs.Count) -ForegroundColor $stickColour
        foreach ($d in $profDevs) { Write-Host ("                expects: {0}" -f $d.Name) -ForegroundColor Gray }
        if ($vkbPids -notcontains '0200') {
            Write-Host "                note: no PID 0200 (EVO Premium base) detected -- if you're on a non-EVO" -ForegroundColor Yellow
            Write-Host "                      base, run [7] Non-EVO axis flip to invert L-X / L-Y / R-Y" -ForegroundColor Yellow
        }
    }""",
"""    # --- Sticks: physical devices the profile declares ---
    $profDevs = Get-ProfileDevices -ProfilePath $shipped
    if ($profDevs.Count -eq 0) {
        Write-Host "  Profile devices: declares no physical devices (check <devices> block in profile XML)" -ForegroundColor Yellow
    }
    else {
        Write-Host ("  Profile devices: expects {0} physical stick(s) -- confirm all are plugged in" -f $profDevs.Count) -ForegroundColor Cyan
        foreach ($d in $profDevs) { Write-Host ("                   expects: {0}" -f $d.Name) -ForegroundColor Gray }
        Write-Host "                   (connected controllers are listed under 'Visible to SC' below)" -ForegroundColor Gray
    }""")

# ---- 4. Remove the VKB Configurator diagnostic block ----
repl("""    # --- VKB Configurator ---
    $vkbCfg = Get-VkbConfiguratorPath
    if ($vkbCfg) {
        Write-Host ("  VKB Configurator: installed -- {0}" -f $vkbCfg) -ForegroundColor Green
    }
    else {
        Write-Host "  VKB Configurator: not installed -- needed for firmware updates and stick-level config (download from vkbcontrollers.com)" -ForegroundColor Yellow
    }

""", "")

# ---- 5. Help block surgery ----
repl("exposes seven operations", "exposes six operations")
repl("""      7. Non-EVO axis flip        -- flips the three response curves the non-EVO
                                     NXT base reports inverted (left stick X+Y
                                     and right stick Y). Edits the JG profile
                                     XML, not actionmaps.xml. EVO users skip.
""", "")
repl("""    Skip the menu and run a single operation. One of: MFD, Invert, Clear,
    Restore, Diagnostic, Prune, NonEvoFlip. Useful for scripted /
    non-interactive runs. Clear, Restore, Prune, and NonEvoFlip still
    prompt for the confirm step.""",
"""    Skip the menu and run a single operation. One of: MFD, Invert, Clear,
    Restore, Diagnostic, Prune. Useful for scripted / non-interactive runs.
    Clear, Restore, and Prune still prompt for the confirm step.""")
repl(""".PARAMETER ProfilePath
    Path to the JG R14 profile XML to operate on (used only by NonEvoFlip).
    Defaults to the profile sibling-of-this-script:
        ..\\Joystick Gremlin Profile [ENH][NXT][4.8.1][LIVE][R14].xml
    Override if you've moved the profile into JG's own profiles folder.

""", "")

# ---- 6. param block: drop NonEvoFlip + $ProfilePath ----
repl("""    [ValidateSet('MFD', 'Invert', 'Clear', 'Restore', 'Diagnostic', 'Prune', 'NonEvoFlip')]
    [string]$Action,
    [string]$ProfilePath
)""",
"""    [ValidateSet('MFD', 'Invert', 'Clear', 'Restore', 'Diagnostic', 'Prune')]
    [string]$Action
)""")

# ---- 7. dispatch + menu wiring ----
repl("        'NonEvoFlip' { Invoke-NonEvoAxisFlip-Selection   -ProfilePathArg $ProfilePath }\n", "")
repl('    Write-Host "  [7] Non-EVO axis flip        -- flip the 3 axes the non-EVO NXT reports inverted"\n', "")
repl("        '7' { Invoke-NonEvoAxisFlip-Selection  -ProfilePathArg $ProfilePath }\n", "")

# ---- 8. MFD bind table -> SOL-R's 8 binds ----
repl("""$Binds = @(
    @{ name = 'v_mfd_interact_cycle_backwards_short'; input = 'js2_button54' }
    @{ name = 'v_mfd_interact_cycle_forwards_short';  input = 'js2_button52' }
    @{ name = 'v_mfd_movement_down_long';             input = 'js2_button53' }
    @{ name = 'v_mfd_movement_left_long';             input = 'js2_button54' }
    @{ name = 'v_mfd_movement_right_long';            input = 'js2_button52' }
    @{ name = 'v_mfd_movement_up_long';               input = 'js2_button51' }
    @{ name = 'v_mfd_quick_action_repair_all';        input = 'js2_button3'  }
    @{ name = 'v_mfd_soft_select_cast_left_short';    input = 'js2_button54'; multiTap = '2' }
    @{ name = 'v_mfd_soft_select_cast_right_short';   input = 'js2_button52'; multiTap = '2' }
)""",
"""$Binds = @(
    @{ name = 'v_mfd_interact_cycle_backwards_short'; input = 'js2_button19' }
    @{ name = 'v_mfd_interact_cycle_forwards_short';  input = 'js2_button18' }
    @{ name = 'v_mfd_movement_down_long';             input = 'js2_button16' }
    @{ name = 'v_mfd_movement_left_long';             input = 'js2_button19' }
    @{ name = 'v_mfd_movement_right_long';            input = 'js2_button18' }
    @{ name = 'v_mfd_movement_up_long';               input = 'js2_button17' }
    @{ name = 'v_mfd_soft_select_cast_left_short';    input = 'js2_button69' }
    @{ name = 'v_mfd_soft_select_cast_right_short';   input = 'js2_button68' }
)""")

# ---- 9. Global stick-identity token swaps (order matters) ----
repl("Dual VKB Gladiator NXT", "Dual TM SOL-R", n=2)        # $StickName + synopsis
repl("Gladiator NXT", "TM SOL-R", n=1)                      # comment line 80
t = t.replace("[ENH][NXT]", "[ENH][SOL-R 2]")              # filenames (many)
t = t.replace("layout_ENH_NXT_", "layout_ENH_SOL-R2_")     # layout filter (x2)
t = t.replace("NXT layout", "SOL-R 2 layout")              # "the/pick/loading the NXT layout"
t = t.replace("NXT profile", "SOL-R profile")              # "NXT profile expects ..." (x2)

# ---- 10. Final residual check ----
leftover = re.findall(r"NXT|VKB|EVO|Gladiator|NonEvo|ProfilePathArg|231D|vkbPid|vkbCfg", t)
assert not leftover, f"residual stick/vendor tokens remain: {sorted(set(leftover))}"

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write(t)
print("OK wrote", DST)
print("lines:", t.count("\n") + 1)
