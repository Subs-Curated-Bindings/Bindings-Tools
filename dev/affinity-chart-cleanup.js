// Affinity chart cleanup — three idempotent passes against the active document.
//
// (1) Removes BrightnessContrastAdjustmentRasterNode descendants — these get accidentally
//     introduced when nodes are copy-pasted between charts and don't belong in the bindings
//     chart art at all.
// (2) Removes ALL layer effects (drop-shadow, outer-glow, bevel, etc.) from every descendant.
//     These trip Affinity's safe-mode SVG export and cause text frames to rasterize.
// (3) Iteratively deletes empty groups (groups with no children) until none remain.
//
// Run this against any Subs-Curated-Bindings chart in Affinity to normalize it for the
// three-way bridge workflow. Idempotent — safe to re-run.
//
// This source lives at tools/affinity-chart-cleanup.js in the repo, and is also registered in
// the Affinity script library as "Chart Cleanup: empty groups + effects + BrightnessContrast".

const { app } = require('/application');
const { getNodeChildren, NodeChildType } = require('/nodes');
const { Selection } = require('/selections');
const { DocumentCommand } = require('/commands');
const cur = app.documents.current;
if (!cur) { console.log('No active document'); }
else {
  console.log('Cleanup running on:', cur.title);
  const spread = cur.spreads.first;

  function walkAll(parent, out) {
    for (const c of getNodeChildren(parent.handle, NodeChildType.Main, false)) {
      out.push(c);
      if (c.isGroupNode || c.isContainerNode) walkAll(c, out);
    }
  }

  // ---- Pass 1: BrightnessContrast adjustment nodes ----
  function pass1_brightnessContrast() {
    const all = [];
    walkAll(spread.layers.first, all);
    const victims = all.filter(n => n.constructor.name === 'BrightnessContrastAdjustmentRasterNode');
    if (victims.length === 0) { console.log('Pass 1 (BrightnessContrast): nothing to delete'); return 0; }
    // Multi-select all then delete in one command
    cur.selection = Selection.create(cur, victims);
    cur.deleteSelection();
    console.log(`Pass 1 (BrightnessContrast): deleted ${victims.length}`);
    return victims.length;
  }

  // ---- Pass 2: layer effects on every node that has any ----
  function pass2_layerEffects() {
    const all = [];
    walkAll(spread.layers.first, all);
    const victims = all.filter(n => n.layerEffectsInterface && n.layerEffectsInterface.hasActiveEffects);
    if (victims.length === 0) { console.log('Pass 2 (layer effects): nothing to remove'); return 0; }
    // List what we're about to scrub (for the log)
    for (const n of victims) {
      const ud = (n.descriptionInterface && n.descriptionInterface.userDescription) || '';
      const dn = (n.userDescription || ud || n.constructor.name);
      console.log(`  removing effects from: ${n.constructor.name} "${dn}" (${n.layerEffectsInterface.effectCount} effects)`);
    }
    // IMPORTANT: cur.removeAllLayerEffects() is a live-preview-only API — it does NOT
    // persist. The Affinity Layers panel keeps showing the FX tag and the SVG export
    // still chokes on the un-removed effects. Use DocumentCommand.createRemoveAllLayerEffects
    // per node to get a persistent removal. (Verified 2026-05-23 on the SOL-R chart.)
    let cleared = 0;
    for (const n of victims) {
      try {
        const sel = Selection.create(cur, n);
        cur.executeCommand(DocumentCommand.createRemoveAllLayerEffects(sel));
        cleared++;
      } catch (e) {
        console.log(`  FAIL on ${n.constructor.name}: ${e.message}`);
      }
    }
    console.log(`Pass 2 (layer effects): cleared on ${cleared} nodes via DocumentCommand`);
    return cleared;
  }

  // ---- Pass 3: iterative empty-group deletion ----
  function isEmptyGroup(n) {
    if (!n.isGroupNode) return false;
    for (const _c of getNodeChildren(n.handle, NodeChildType.Main, false)) return false;
    return true;
  }

  function pass3_emptyGroups() {
    let totalDeleted = 0;
    for (let iter = 0; iter < 10; iter++) {
      const all = [];
      walkAll(spread.layers.first, all);
      const victims = all.filter(isEmptyGroup);
      if (victims.length === 0) break;
      cur.selection = Selection.create(cur, victims);
      cur.deleteSelection();
      totalDeleted += victims.length;
      console.log(`Pass 3 (empty groups), iter ${iter + 1}: deleted ${victims.length}`);
    }
    if (totalDeleted === 0) console.log('Pass 3 (empty groups): nothing to delete');
    else console.log(`Pass 3 (empty groups): ${totalDeleted} total deleted`);
    return totalDeleted;
  }

  const r1 = pass1_brightnessContrast();
  const r2 = pass2_layerEffects();
  const r3 = pass3_emptyGroups();
  console.log();
  console.log(`Cleanup complete. BrightnessContrast=${r1} effects=${r2} emptyGroups=${r3}`);
}
