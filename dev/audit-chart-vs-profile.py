"""
Three-way audit: cross-reference chart SVG ↔ JG profile descriptions ↔ SC layout XML.

For a stick whose JG profile carries description actions in the
"<etched-name>[ [Modifier]] — <chart-derived text>" convention, this tool
mechanically verifies that all three artifacts agree about each binding.

Checks:
  1. Chart-to-JG coverage. Every chart `bind.<etched-name>` cluster has at
     least one JG description naming that etched-name.
  2. JG-to-layout coverage. Every JG input that has a description action
     also reaches a map-to-vjoy whose vjoy slot appears in the layout XML.
  3. Layout-to-JG coverage. Every layout XML rebind targets a vjoy slot
     that at least one JG input emits.
  4. Etched-name consistency. Every etched-name referenced by a JG
     description corresponds to a real chart cluster.

Usage:
  python audit-chart-vs-profile.py <stick-folder>
  # The stick folder must contain:
  #   Binding Charts/<chart>.svg
  #   <jg profile>.xml          (matches *Joystick Gremlin Profile*[R14]*.xml)
  #   layout_*_exported.xml     (the non-Clear-Bindings layout)
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")


# ---------- File discovery ----------

def find_stick_files(stick_dir):
    """Locate the SVG, JG profile, and layout XML in a stick folder."""
    svgs = [f for f in os.listdir(os.path.join(stick_dir, "Binding Charts"))
            if f.lower().endswith(".svg")]
    if not svgs:
        sys.exit(f"No SVG found in {stick_dir}/Binding Charts/")
    svg = os.path.join(stick_dir, "Binding Charts", svgs[0])

    jgs = [f for f in os.listdir(stick_dir)
           if "Joystick Gremlin Profile" in f and "R14" in f and f.endswith(".xml")
           and "FROM-GIT-HEAD" not in f]
    if not jgs:
        sys.exit(f"No R14 JG profile found in {stick_dir}/")
    jg = os.path.join(stick_dir, jgs[0])

    layouts = [f for f in os.listdir(stick_dir)
               if f.startswith("layout_") and f.endswith("_exported.xml")
               and "Clear_Bindings" not in f]
    if not layouts:
        sys.exit(f"No stick-specific layout XML found in {stick_dir}/")
    layout = os.path.join(stick_dir, layouts[0])

    return svg, jg, layout


# ---------- Chart SVG parsing ----------

def parse_chart(svg_path):
    """Return {etched_name: cluster_text} for every bind.<etched-name> cluster.
    Also collapses suffixed-ID collisions (Affinity adds '1' suffix on dup ids;
    serif:id preserves the canonical name)."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    clusters = {}
    serif_ns = "{http://www.serif.com/}id"
    for elem in root.iter():
        eid = elem.attrib.get("id", "")
        # Prefer serif:id when present (canonical), fall back to id (mangled)
        serif_id = elem.attrib.get(serif_ns, "")
        canonical = serif_id or eid
        if not canonical.startswith("bind."):
            continue
        etched = canonical[len("bind."):]
        parts = []
        for t in elem.iter():
            tag = t.tag.split("}", 1)[-1]
            if tag in ("text", "tspan") and t.text:
                parts.append(t.text)
        text = " ".join(" ".join(parts).split())
        if text:
            clusters[etched] = text
    return clusters


# ---------- JG profile parsing ----------

# Patterns for parsing description text → etched-name + mode + body
# Variants we generate:
#   "L-B1 — Precision Aiming"
#   "L-A3.up — Flight Ready"
#   "L-A3.up [Modifier] — Toggle Power On/Off"
#   "L-A1 (8-way hat) — up=... | ..."
#   "L-A1 [Modifier] (8-way hat) — ..."
#   "RAPID-TRIG-L (Trigger Down) [Modifier] — ..."
#   "MAIN-TRIG-R.stage-1 — Stage 1: Fire ..."
#   "Left stick axis 1 (passthrough to vjoy 1 axis 1)"   ← documentation, no em-dash

ETCHED_PAT = re.compile(
    r"^(?P<etched>"
    # Generic multi-segment (covers SOL-R-style ANALOG-HAT-L, MAIN-TRIG-R.stage-1,
    # RAPID-TRIG-L, Moza R-BB-1 / T-NAV-1 / T-BTN-A1, VMAX T-B1, etc.). Listed
    # FIRST so multi-segment names aren't truncated by the simpler L-/R- alt below.
    r"(?:[A-Z0-9]+(?:-[A-Z0-9]+){1,4}(?:\.[a-z0-9-]+)*)"
    # VKB-style fallback: L-A1, R-A3, L-A1B (no extra -segment, optional .dir)
    r"|(?:[LR]-[A-Z0-9]+(?:\.[a-z0-9-]+)*)"
    r")"
)


def parse_description_text(desc):
    """Return (etched_name, mode_tag, body) or None for non-binding labels."""
    m = ETCHED_PAT.match(desc)
    if not m:
        return None
    etched = m.group("etched")
    rest = desc[m.end():].strip()

    mode_tag = ""
    if "[Modifier]" in rest:
        mode_tag = "Modifier"
        rest = rest.replace("[Modifier]", "").strip()

    # Strip any leading "(...)" tag like "(Trigger Down)" or "(8-way hat)"
    rest = re.sub(r"^\([^)]*\)\s*", "", rest).strip()

    # Body comes after em-dash
    if rest.startswith("—"):
        body = rest[1:].strip()
    elif "—" in rest:
        body = rest.split("—", 1)[1].strip()
    else:
        body = ""
    return etched, mode_tag, body


def collect_vjoy_targets(action, by_id, visited=None, path="always"):
    """Walk an action subtree and collect every (vjoy_dev, vjoy_input, type, path) tuple.

    `path` tags WHEN the vjoy press fires relative to the physical button event:
      - "always": fires on every press (no tempo gating above this node)
      - "tap":    inside a tempo's short-actions — fires only on short press
      - "hold":   inside a tempo's long-actions  — fires only after the threshold

    Tempo handling: when we encounter a `<tempo>`, we walk short-actions with
    path="tap" and long-actions with path="hold", inheriting "always" only if
    not already narrowed. This is the difference between "input emits N slots"
    (flat union) and "tap fires X, hold fires Y" (the way the user perceives it).

    Captures both `<action type="map-to-vjoy">` actions and `<macro-action type="vjoy">`
    sub-actions inside macros (the latter is how tempo-wrapped toggle binds emit —
    see references/sc-toggle-tap-pattern.md). Dedupes per (slot, path) since macros
    emit press+release on the same slot as two separate macro-actions.
    """
    if visited is None:
        visited = set()
    aid = action.attrib.get("id")
    if aid in visited:
        return []
    visited.add(aid)
    out = []
    atype = action.attrib.get("type", "")
    if atype == "map-to-vjoy":
        props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
        try:
            out.append((
                int(props.get("vjoy-device-id", "0")),
                int(props.get("vjoy-input-id", "0")),
                props.get("vjoy-input-type", ""),
                path,
            ))
        except ValueError:
            pass
    # Macros emit vjoy via <macro-action type="vjoy"> children, not nested actions.
    if atype == "macro":
        for ma in action.findall("macro-action"):
            if ma.attrib.get("type") != "vjoy":
                continue
            props = {p.findtext("name", ""): p.findtext("value", "") for p in ma.findall("property")}
            try:
                target = (
                    int(props.get("vjoy-id", "0")),
                    int(props.get("input-id", "0")),
                    props.get("input-type", ""),
                    path,
                )
                if target not in out:
                    out.append(target)
            except ValueError:
                pass
    # Tempo: split into tap (short-actions) and hold (long-actions) sub-paths
    if atype == "tempo":
        for short in action.findall("./short-actions/action-id"):
            if short.text and short.text in by_id and short.text != aid:
                out.extend(collect_vjoy_targets(by_id[short.text], by_id, set(visited), "tap"))
        for long_ in action.findall("./long-actions/action-id"):
            if long_.text and long_.text in by_id and long_.text != aid:
                out.extend(collect_vjoy_targets(by_id[long_.text], by_id, set(visited), "hold"))
        return out
    # Double-tap: uses <single-actions>/<double-actions> containers. Treat both
    # as the inherited path — the layout XML can't distinguish single vs double-tap
    # fires of the same vjoy slot anyway.
    if atype == "double-tap":
        for s in action.findall("./single-actions/action-id"):
            if s.text and s.text in by_id and s.text != aid:
                out.extend(collect_vjoy_targets(by_id[s.text], by_id, set(visited), path))
        for d in action.findall("./double-actions/action-id"):
            if d.text and d.text in by_id and d.text != aid:
                out.extend(collect_vjoy_targets(by_id[d.text], by_id, set(visited), path))
        return out
    # Non-tempo: walk any nested action-id refs with the same path
    for el in action.iter():
        if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
            # Skip — we'll get them via the parent's <actions> walk
            pass
    # Direct children only (not action.iter() — that pulls action-ids from tempo's
    # short/long-actions too, which we've already handled and would double-count).
    actions_el = action.find("actions")
    if actions_el is not None:
        for ch in actions_el.findall("action-id"):
            if ch.text and ch.text in by_id and ch.text != aid:
                out.extend(collect_vjoy_targets(by_id[ch.text], by_id, visited, path))
    return out


def parse_jg(jg_path):
    """Return a dict of per-input records:
      input_key = (device-id, input-type, input-id, mode)
      record = {
        'root_id', 'etched_name', 'mode_tag', 'description_body',
        'vjoy_targets': [(dev, inp, type), ...],
        'has_description': bool,
        'raw_desc': str | None,
      }
    Plus a set of all description-action ids that pointed to a non-binding doc label."""
    tree = ET.parse(jg_path)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    # For each input, find its root action and walk it.
    records = {}
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            root_id = ac.findtext("root-action", "")
            if not root_id or root_id not in by_id:
                continue
            root_action = by_id[root_id]

            # Find the description action (anywhere in the root's children)
            etched, mode_tag, body, raw = None, "", "", None
            actions_el = root_action.find("actions")
            if actions_el is not None:
                for c in actions_el.findall("action-id"):
                    if not c.text or c.text not in by_id:
                        continue
                    child = by_id[c.text]
                    if child.attrib.get("type") != "description":
                        continue
                    raw_value = ""
                    for p in child.findall("property"):
                        if p.findtext("name", "") == "description":
                            raw_value = p.findtext("value", "") or ""
                            break
                    raw = raw_value
                    parsed = parse_description_text(raw_value)
                    if parsed:
                        etched, mode_tag, body = parsed
                    break  # take first description only

            vjoy_targets = collect_vjoy_targets(root_action, by_id)
            key = (did, itype, iid, mode)
            existing = records.get(key)
            if existing is None:
                records[key] = {
                    "root_id": root_id,
                    "etched_name": etched,
                    "mode_tag": mode_tag,
                    "description_body": body,
                    "raw_desc": raw,
                    "has_description": raw is not None,
                    "vjoy_targets": list(vjoy_targets),
                }
            else:
                # Accumulate vjoy_targets across multiple action-configs
                # (axes commonly have two threshold-band action-configs).
                # Preserve first description if any.
                for vt in vjoy_targets:
                    if vt not in existing["vjoy_targets"]:
                        existing["vjoy_targets"].append(vt)
                if raw and not existing["raw_desc"]:
                    existing["etched_name"] = etched
                    existing["mode_tag"] = mode_tag
                    existing["description_body"] = body
                    existing["raw_desc"] = raw
                    existing["has_description"] = True
    return records


# ---------- Layout XML parsing ----------

def parse_layout(layout_path):
    """Return:
      vjoy_button[(dev, btn)] = [(actionmap, action_name), ...]
      vjoy_axis[(dev, axis_name)] = [...]
      vjoy_hat[(dev, hat_id, dir_)] = [...]
    """
    root = ET.parse(layout_path).getroot()
    button_map = defaultdict(list)
    axis_map = defaultdict(list)
    hat_map = defaultdict(list)
    for am in root.findall("./actionmap"):
        amname = am.attrib.get("name", "")
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    button_map[(int(m.group(1)), int(m.group(2)))].append((amname, aname))
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rx|ry|rz|throttle|slider1|slider2)$", inp)
                if m:
                    axis_map[(int(m.group(1)), m.group(2))].append((amname, aname))
                    continue
                m = re.match(r"js(\d+)_hat(\d+)_(up|down|left|right)$", inp)
                if m:
                    hat_map[(int(m.group(1)), int(m.group(2)), m.group(3))].append((amname, aname))
                    continue
    return button_map, axis_map, hat_map


# ---------- Audit logic ----------

def run_audit(stick_dir):
    svg_path, jg_path, layout_path = find_stick_files(stick_dir)
    print(f"Stick folder: {stick_dir}")
    print(f"  SVG    : {os.path.basename(svg_path)}")
    print(f"  JG     : {os.path.basename(jg_path)}")
    print(f"  Layout : {os.path.basename(layout_path)}")
    print()

    chart_clusters = parse_chart(svg_path)
    jg_records = parse_jg(jg_path)
    layout_btn, layout_axis, layout_hat = parse_layout(layout_path)

    # Build indices
    # JG: etched_name -> [input_keys that have a description naming it]
    jg_by_etched = defaultdict(list)
    for key, rec in jg_records.items():
        if rec["etched_name"]:
            jg_by_etched[rec["etched_name"]].append(key)

    # JG: which inputs reach which vjoy slot (key by slot, dropping the path tag)
    vjoy_to_inputs = defaultdict(list)
    for key, rec in jg_records.items():
        for v in rec["vjoy_targets"]:
            dev, inp, vtype = v[0], v[1], v[2]  # ignore path for layout->JG lookup
            vjoy_to_inputs[(dev, inp, vtype)].append(key)

    # ---- Check 1: Chart-to-JG coverage ----
    chart_etched_names = set(chart_clusters.keys())
    jg_etched_names = set(jg_by_etched.keys())

    # A chart cluster "X.dir[.role]" is also covered if JG has a description
    # for the base name "X" — e.g., JG's "L-A1" hat description covers chart
    # clusters L-A1.up, L-A1.down, L-A1.left, L-A1.right, L-A1.press-in.
    def base_name(etched):
        # Strip .role first (.device / .game), then .dir
        parts = etched.split(".")
        return parts[0]

    def is_unbound_cluster(body, cluster_name):
        """A cluster is considered self-documenting-unbound if the body's
        binding content consists only of unbound markers. Tolerates the
        cluster label, position numbers, and the word 'axis'."""
        if not body:
            return False
        if body.strip().upper() == "UNBOUND":
            return True
        # Tokenize body, lowercase, strip the cluster name fragments and numbers
        ignorable = {
            "unbound", "axis", "position",
            # cluster name fragments (label words)
            *cluster_name.lower().replace("-", " ").split(),
        }
        tokens = re.findall(r"[a-zA-Z]+", body.lower())
        meaningful = [t for t in tokens if t not in ignorable and len(t) > 1]
        # If every meaningful token is "unbound", cluster is unbound-only
        return bool(tokens) and all(t == "unbound" for t in meaningful) and "unbound" in tokens

    def chart_is_covered(etched):
        if etched in jg_etched_names:
            return True
        # Try base-name match (for hats / aggregated descriptions)
        if base_name(etched) in jg_etched_names:
            return True
        # Skip clusters the chart documents as unbound — no JG input
        # exists to attach a description to, and the chart is self-documenting.
        if is_unbound_cluster(chart_clusters.get(etched, ""), etched):
            return True
        return False

    chart_without_jg = sorted(c for c in chart_etched_names if not chart_is_covered(c))
    jg_without_chart = sorted(
        j for j in jg_etched_names
        if j not in chart_etched_names and not any(c.split(".")[0] == j for c in chart_etched_names)
    )

    # ---- Check 2: JG-to-layout coverage ----
    # For each JG input that has a description, classify its vjoy BUTTON emissions:
    #   - SILENT-BROKEN: every emission is unbound in layout → physical button does
    #     nothing in-game
    #   - PARTIAL:       some emissions bound, some not → physical button still
    #     works (via the bound slot), but emits dead slots alongside
    #   - COVERED:       all emissions bound
    #
    # This pattern arises because a single physical button often emits to multiple
    # vjoy slots in JG (e.g. one for the spaceship_movement actionmap, one for the
    # seat_general actionmap). The layout binds the slots it cares about; the
    # others are dead weight but harmless.
    # Group emissions by execution path (tap / hold / always) so we can classify
    # per-path coverage. A tempo input is silent-broken on a specific path only if
    # NO emission on that path lands in the layout; partial-coverage if some paths
    # have all-bound and others don't.
    silent_broken = []          # every path has zero bound emissions
    path_partial_coverage = []  # one or more paths have unbound emissions, but
                                # SOME path has a bound emission
    for key, rec in jg_records.items():
        if not rec["etched_name"]:
            continue
        # Group emissions by path
        by_path = defaultdict(lambda: {"bound": [], "unbound": []})
        for v in rec["vjoy_targets"]:
            dev, inp, vtype, path = v[0], v[1], v[2], v[3] if len(v) > 3 else "always"
            if vtype != "button":
                continue  # axes handled separately
            slot = (dev, inp)
            if layout_btn.get(slot):
                by_path[path]["bound"].append(v)
            else:
                by_path[path]["unbound"].append(v)
        if not by_path:
            continue

        # Per-path classification
        any_path_bound = any(p["bound"] for p in by_path.values())
        any_path_has_unbound = any(p["unbound"] for p in by_path.values())
        if not any_path_bound:
            # No path has any bound emission → genuinely broken across the whole input
            all_unbound = [v for p in by_path.values() for v in p["unbound"]]
            silent_broken.append((rec["etched_name"], key, all_unbound))
        elif any_path_has_unbound:
            path_partial_coverage.append((rec["etched_name"], key, dict(by_path)))

    # ---- Check 3: Layout-to-JG coverage ----
    # For each layout rebind (button only — axis/hat naming asymmetric here),
    # check that at least one JG input emits that vjoy slot.
    layout_orphans = []
    for (dev, btn), acts in layout_btn.items():
        if not vjoy_to_inputs.get((dev, btn, "button")):
            layout_orphans.append((dev, btn, acts))

    # ---- Check 4: Cluster over-attribution ----
    # A chart cluster (e.g. R-M1) has a fixed number of directional sub-clusters:
    #   * a button cluster has just itself (1)
    #   * a hat has up/down/left/right + optional press-in (4-5)
    #   * a multi-stage trigger has stage-1/stage-2 (2)
    #   * a rapid trigger ships as one base cluster but is functionally 2 inputs
    #     (Trigger Up / Trigger Down) — see Gunfighter / NXT
    # JG attaches one description per input root; the matcher should assign at
    # most one JG input per direction (per mode). If JG assigns MORE inputs to
    # a cluster than the chart has directions for it, the matcher has over-
    # attributed — usually because the input's true cluster is missing from the
    # chart and the matcher picked a tangentially-related cluster instead.
    #
    # Only meaningful for charts that use the directional sub-cluster convention
    # (NXT / Gunfighter / VMAX use bind.X.up/.down/.left/.right; SOL-R aggregates
    # multiple inputs into one flat cluster, so the per-direction count isn't a
    # signal there).
    chart_uses_direction_subclusters = any(
        n.endswith(".up") or n.endswith(".down") or n.endswith(".left") or n.endswith(".right")
        for n in chart_clusters
    )

    chart_directions_per_base = defaultdict(set)
    for cluster_name in chart_clusters:
        base = base_name(cluster_name)
        if cluster_name == base:
            chart_directions_per_base[base].add("(self)")
        else:
            chart_directions_per_base[base].add(cluster_name[len(base) + 1:])

    jg_inputs_per_base_mode = defaultdict(lambda: defaultdict(set))
    for key, rec in jg_records.items():
        if not rec["etched_name"]:
            continue
        base = base_name(rec["etched_name"])
        mode = key[3]
        jg_inputs_per_base_mode[base][mode].add((key[0], key[1], key[2]))

    # [PM] (Physical Modifier) is a hardware switch on the stick that toggles
    # the entire grip into a 2nd layer — each hat direction gets a separate
    # button press in the PM layer, doubling effective directional capacity.
    # Detect at chart level: if any cluster body uses [PM] notation, the stick
    # has the modifier. Doubled-capacity then applies to every hat-like cluster
    # (4+ directions), not just the ones whose body happens to spell out [PM].
    chart_has_pm_modifier = any("[PM]" in body for body in chart_clusters.values())

    over_attributed = []
    if chart_uses_direction_subclusters:
        for base, modes in jg_inputs_per_base_mode.items():
            if base not in chart_directions_per_base:
                continue
            expected = len(chart_directions_per_base[base])
            # Rapid triggers and Virpil flip triggers ship as one chart cluster
            # but split into 2 physical inputs at the JG layer (Trigger Up vs
            # Trigger Down on the rapid; mode-switch vs fire on the flip).
            if base.startswith("RAPID-TRIG-") or base.startswith("FLIP-TRIG-"):
                expected = max(expected, 2)
            # Hat-like cluster on a stick with [PM] hardware: each direction
            # exists in both the primary and PM layers, so 2x the capacity.
            if chart_has_pm_modifier and len(chart_directions_per_base[base]) >= 4:
                expected *= 2
            for mode, inputs in modes.items():
                if len(inputs) > expected:
                    over_attributed.append((base, mode, len(inputs), expected, sorted(inputs)))

    # ---- Report ----
    print("=" * 70)
    print(f"SUMMARY")
    print("=" * 70)
    print(f"  Chart bind clusters         : {len(chart_clusters)}")
    print(f"  JG inputs with descriptions : {sum(1 for r in jg_records.values() if r['etched_name'])}")
    print(f"  JG inputs (total)           : {len(jg_records)}")
    print(f"  Layout button rebinds       : {len(layout_btn)}")
    print()
    print(f"  Chart clusters w/o JG       : {len(chart_without_jg)}")
    print(f"  JG descriptions w/o chart   : {len(jg_without_chart)}")
    print(f"  JG inputs silent-broken (all vjoy emissions unbound) : {len(silent_broken)}")
    print(f"  JG inputs partial-coverage (bound + dead emissions)  : {len(path_partial_coverage)}  [informational]")
    print(f"  Layout buttons w/o JG emitter     : {len(layout_orphans)}")
    print(f"  Over-attributed clusters (more JG inputs than chart directions) : {len(over_attributed)}")
    print()

    if chart_without_jg:
        print("-" * 70)
        print("Chart clusters with no JG description")
        print("(every binding the chart claims should be described in the JG profile)")
        print("-" * 70)
        for etched in chart_without_jg:
            preview = chart_clusters[etched][:60]
            print(f"  {etched:30s} chart text: {preview}")
        print()

    if jg_without_chart:
        print("-" * 70)
        print("JG descriptions referencing an etched-name not on chart")
        print("(typo in JG description, or chart missing the cluster)")
        print("-" * 70)
        for etched in jg_without_chart:
            for key in jg_by_etched[etched]:
                rec = jg_records[key]
                print(f"  {etched:30s} {key[1]:6s} id={key[2]} mode={key[3]}")
        print()

    if silent_broken:
        print("-" * 70)
        print("Silent-broken JG inputs (every vjoy emission is unbound in layout)")
        print("(Physical button does nothing in-game — this is the real break.)")
        print("-" * 70)
        for etched, key, unbound in silent_broken:
            slots = ", ".join(f"vjoy {v[0]} button {v[1]}" for v in unbound)
            print(f"  {etched:30s} {key[1]:6s} id={key[2]} mode={key[3]:14s} -> {slots}")
        print()

    if path_partial_coverage:
        print("-" * 70)
        print("Partial-coverage JG inputs (informational — NOT an audit failure)")
        print("(Each input's emissions are grouped by trigger path:")
        print("   tap    = fires on short press (under the tempo threshold)")
        print("   hold   = fires after the tempo threshold")
        print("   always = no tempo gating — fires on any press")
        print(" Each path is BOUND if at least one of its emissions has a layout")
        print(" rebind, UNBOUND if all of its emissions are dead slots.)")
        print("-" * 70)
        for etched, key, by_path in path_partial_coverage:
            print(f"  {etched:30s} {key[1]:6s} id={key[2]} mode={key[3]:14s}")
            for path in ("always", "tap", "hold"):
                if path not in by_path:
                    continue
                p = by_path[path]
                bound_slots = ", ".join(f"vjoy {v[0]} btn {v[1]}" for v in p["bound"])
                unbound_slots = ", ".join(f"vjoy {v[0]} btn {v[1]}" for v in p["unbound"])
                if p["bound"] and p["unbound"]:
                    print(f"    {path:6s}: bound={bound_slots}  /  dead={unbound_slots}")
                elif p["bound"]:
                    print(f"    {path:6s}: bound={bound_slots}")
                else:
                    print(f"    {path:6s}: DEAD ONLY — {unbound_slots}")
        print()

    if layout_orphans:
        print("-" * 70)
        print("Layout XML rebinds with no JG input emitter")
        print("(SC listens for this vjoy button, but no JG input fires it)")
        print("-" * 70)
        for dev, btn, acts in layout_orphans:
            actions_str = ", ".join(f"{an}({am})" for am, an in acts[:3])
            print(f"  js{dev}_button{btn:<3d}  {actions_str}")
        print()

    if over_attributed:
        print("-" * 70)
        print("Over-attributed chart clusters")
        print("(Cluster claimed by more JG inputs than the chart has directions.")
        print(" Usually means the matcher fell back to a tangential cluster because")
        print(" the input's true cluster is missing from the chart. Fix by adding a")
        print(" dedicated chart cluster for the unattributed inputs, or by writing a")
        print(" manual override in the per-stick overrides JSON.)")
        print("-" * 70)
        for base, mode, n_inputs, expected, inputs in over_attributed:
            print(f"  {base:20s} mode={mode:14s}  {n_inputs} JG inputs vs {expected} chart directions:")
            for (did, itype, iid) in inputs:
                print(f"      dev:{did[:8]}  {itype}#{iid}")
        print()

    # Detailed table: per chart cluster, status
    print("=" * 70)
    print("PER-CLUSTER STATUS")
    print("=" * 70)
    for etched in sorted(chart_etched_names | jg_etched_names):
        in_chart = etched in chart_clusters
        in_jg_direct = etched in jg_by_etched
        in_jg_via_base = (not in_jg_direct) and (base_name(etched) in jg_etched_names)
        chart_marker = "OK" if in_chart else "--"
        if in_jg_direct:
            jg_marker = "OK"
        elif in_jg_via_base:
            jg_marker = "AGG"  # aggregated via base-name (hats)
        else:
            jg_marker = "--"
        jg_modes = sorted({k[3] for k in jg_by_etched.get(etched, [])})
        modes_str = ",".join(jg_modes) if jg_modes else "-"
        print(f"  chart={chart_marker} jg={jg_marker:3s} {etched:30s} jg_modes={modes_str}")

    # Final verdict
    print()
    print("=" * 70)
    # partial_coverage is informational, not an audit failure (the input still
    # works via its bound emissions — the unbound slots are dead weight, not breakage).
    total_issues = (len(chart_without_jg) + len(jg_without_chart)
                    + len(silent_broken) + len(layout_orphans)
                    + len(over_attributed))
    if total_issues == 0:
        print("AUDIT PASSED — chart, JG profile, and layout XML all agree.")
    else:
        print(f"AUDIT: {total_issues} issue(s) flagged. Review sections above.")
    print("=" * 70)
    return total_issues


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stick_folder", help="Path to a stick folder (e.g. '[Enhanced] Dual VKB Gladiator NXT')")
    args = p.parse_args()
    sys.exit(0 if run_audit(args.stick_folder) == 0 else 1)


if __name__ == "__main__":
    main()
