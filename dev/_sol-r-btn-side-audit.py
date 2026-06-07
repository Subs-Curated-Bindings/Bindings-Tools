import xml.etree.ElementTree as ET
from collections import defaultdict
PROF="[Enhanced] Dual TM SOL-R/Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
t=ET.parse(PROF); r=t.getroot()
lib={a.get("id"):a for a in r.find("library").iter("action") if a.get("id")}

def prop(a,name):
    for p in a.findall("property"):
        n=p.find("name"); v=p.find("value")
        if n is not None and n.text==name: return v.text if v is not None else None
    return None

def collect(aid, seen=None, out=None):
    if seen is None: seen=set(); out=[]
    if aid in seen or aid not in lib: return out
    seen.add(aid)
    a=lib[aid]
    typ=a.get("type")
    if typ=="map-to-vjoy":
        out.append(("vjoy", prop(a,"action-label"), prop(a,"vjoy-device-id"), prop(a,"vjoy-input-id")))
    elif typ in ("map-to-mouse","macro","change-mode","map-to-keyboard"):
        out.append((typ, prop(a,"action-label"), None, None))
    for e in a.iter():
        if e.tag=="action-id" and e.text and e.text!=aid:
            collect(e.text, seen, out)
    return out

inputs=r.find("inputs")
rows=[]
for inp in inputs.findall("input"):
    dev=inp.findtext("device-id"); itype=inp.findtext("input-type")
    mode=inp.findtext("mode"); iid=inp.findtext("input-id")
    emits=[]
    for ac in inp.findall("action-configuration"):
        ra=ac.findtext("root-action")
        if ra: emits+=collect(ra)
    rows.append((dev,itype,mode,iid,emits))

GUID={"141b1470-1081-11f0-8006-444553540000":"DEV-A(141b)",
      "6686f980-1082-11f0-8008-444553540000":"DEV-B(6686)",
      "cbd05e70-101a-11f0-8002-444553540000":"DEV-C(cbd0)"}
def dn(d): return GUID.get(d,d[:8])

print("=== BUTTON 35 / 39 ===")
for dev,itype,mode,iid,emits in rows:
    if itype=="button" and iid in ("35","39"):
        e=[f"{lbl}[{ty} v{vd}.{vi}]" for ty,lbl,vd,vi in emits]
        print(f"{dn(dev):12} {mode:9} btn{iid}: {e}")

import re
print("\n=== moniker prefix by device (SCM Mode, button inputs) ===")
MONIK=re.compile(r'^[A-Za-z][A-Za-z0-9]*([.\-][A-Za-z0-9]+)+')
sidecount=defaultdict(lambda: defaultdict(int))
for dev,itype,mode,iid,emits in rows:
    for ty,lbl,vd,vi in emits:
        if not lbl: continue
        tok=lbl.split()[0]
        pre = tok.split('-')[0] if '-' in tok else tok.split('.')[0]
        sidecount[dn(dev)][pre]+=1
for d,pc in sidecount.items():
    print(d, dict(sorted(pc.items(), key=lambda x:-x[1])))

print("\n=== ALL monikers that lack L/R prefix (candidate for side split) ===")
seen=set()
for dev,itype,mode,iid,emits in rows:
    for ty,lbl,vd,vi in emits:
        if not lbl: continue
        tok=lbl.split()[0]
        # does it start with L-/R- or LL-/LR-/RL-/RR- ?
        has_side = bool(re.match(r'^(LL|LR|RL|RR|L|R)[-.]', tok))
        if not has_side:
            key=(dn(dev),tok)
            if key not in seen:
                seen.add(key); 
for (d,tok) in sorted(seen):
    print(d, tok)

print("\n=== ALL emits whose moniker token has NO side and is not a tempo-leaf/None/sentinel ===")
def first_tok(lbl): return lbl.split()[0] if lbl else lbl
sideless=defaultdict(lambda: defaultdict(list))  # token -> device -> [(mode,vjoy)]
LEAF={'.tap','.hold','.up','.down','.left','.right','.press'}
for dev,itype,mode,iid,emits in rows:
    for ty,lbl,vd,vi in emits:
        if not lbl: continue
        tok=first_tok(lbl)
        if tok in ('None','Map') or tok in LEAF or lbl.startswith('"'): continue
        if re.match(r'^(LL|LR|RL|RR)-', tok): continue
        if re.match(r'^[LR][0-9]', tok): continue   # L30/L40/R30/R40
        if re.match(r'^[LR]-', tok): continue       # L-/R-
        sideless[tok][dn(dev)].append((mode, f"v{vd}.{vi}"))
for tok,devs in sorted(sideless.items()):
    print(f"  {tok}: "+" || ".join(f"{d}:{v}" for d,v in devs.items()))
