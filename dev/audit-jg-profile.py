"""
Structural audit for a JG R14 profile.

Checks:
  - XML parses
  - All action IDs are unique
  - All action-id / root-action references resolve to a defined action
  - No forward references (every referenced action defined before its referencer
    -- JG R14 loads top-down and forward refs make the file load blank)
  - Response-curve ordering invariant: in any root whose actions include a
    response-curve, the response-curve action-id must appear before any
    map-to-vjoy / map-to-mouse action-id (otherwise the curve is a silent no-op)
  - Orphan library actions (defined but never referenced from any root, root,
    or input -- dead weight, candidate for cleanup)

Usage:
  python audit-jg-profile.py "<path to JG profile xml>"
"""
import sys
import xml.etree.ElementTree as ET


def audit(profile_path):
    tree = ET.parse(profile_path)
    root = tree.getroot()
    actions = root.findall('./library/action')
    action_type = {a.attrib['id']: a.attrib['type'] for a in actions}
    all_ids = set(action_type)

    # Duplicates
    seen = set()
    dups = []
    for a in actions:
        aid = a.attrib['id']
        if aid in seen:
            dups.append(aid)
        seen.add(aid)

    # Build reference set (action-id child elements + root-action elements from inputs)
    refs = set()
    input_root_refs = set()
    for el in root.iter():
        if el.tag == 'action-id' and el.text:
            refs.add(el.text)
        elif el.tag == 'root-action' and el.text:
            input_root_refs.add(el.text)
            refs.add(el.text)

    missing = refs - all_ids
    orphans = (all_ids - refs) - input_root_refs

    # Forward refs
    ids_in_order = [a.attrib['id'] for a in actions]
    pos = {aid: i for i, aid in enumerate(ids_in_order)}
    fwd = []
    for a in actions:
        parent = a.attrib['id']
        for el in a.iter('action-id'):
            if el.text and el.text in pos and pos[parent] < pos[el.text]:
                fwd.append((parent, el.text))

    # Response-curve ordering
    roots = {a.attrib['id']: [c.text for c in a.find('actions')]
             for a in actions if a.attrib['type'] == 'root'}
    broken_curves = []
    for rid, child_ids in roots.items():
        types = [action_type.get(c, '?') for c in child_ids]
        rc = [i for i, t in enumerate(types) if t == 'response-curve']
        other = [i for i, t in enumerate(types) if t != 'response-curve']
        if rc and other and max(rc) > min(other):
            broken_curves.append((rid, types))

    # Report
    print(f'Profile: {profile_path}')
    print(f'  Actions: {len(actions)}, unique: {len(all_ids)}, duplicates: {len(dups)}')
    print(f'  Missing references: {len(missing)}')
    print(f'  Forward refs: {len(fwd)}')
    print(f'  Response-curve order: {len(roots)} roots, {len(broken_curves)} broken')
    print(f'  Orphan library actions: {len(orphans)}')

    if dups:
        print('\nDuplicate IDs:')
        for d in dups[:20]:
            print(f'  {d}')

    if missing:
        print('\nMissing refs:')
        for m in list(missing)[:20]:
            print(f'  {m}')

    if fwd:
        print('\nForward refs (parent referencing later child):')
        for p, c in fwd[:20]:
            print(f'  {p[:8]} -> {c[:8]}')

    if broken_curves:
        print('\nBroken response-curve roots (curve placed after its mapping):')
        for rid, types in broken_curves[:20]:
            print(f'  {rid[:8]}: {types}')

    if orphans:
        print('\nOrphan library actions (defined but not referenced):')
        for o in list(orphans)[:30]:
            print(f'  {o[:8]} ({action_type[o]})')

    # Exit non-zero if anything is broken
    is_clean = (not dups and not missing and not fwd and not broken_curves)
    return 0 if is_clean else 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: audit-jg-profile.py <profile.xml>')
    sys.exit(audit(sys.argv[1]))
