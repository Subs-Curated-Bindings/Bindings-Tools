"""Split SOL-R side-less monikers (BTN.35/39, MAIN-TRIGGER.stage1/2) into L-/R-.
Side = vjoy-device-id (1->L-, 2->R-). Scoped per action id; preserves BOM+EOL."""
import xml.etree.ElementTree as ET, re, sys
PROF="[Enhanced] Dual TM SOL-R/Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
TARGETS={"BTN.35","BTN.39","MAIN-TRIGGER.stage1","MAIN-TRIGGER.stage2"}

t=ET.parse(PROF); r=t.getroot()
def prop(a,name):
    for p in a.findall("property"):
        n=p.find("name"); v=p.find("value")
        if n is not None and n.text==name: return v
    return None
changes=[]
for a in r.find("library").iter("action"):
    if a.get("type")!="map-to-vjoy": continue
    lv=prop(a,"action-label")
    if lv is None or lv.text not in TARGETS: continue
    side={"1":"L-","2":"R-"}[prop(a,"vjoy-device-id").text]
    changes.append((a.get("id"), lv.text, side+lv.text))
assert len(changes)==16, f"expected 16, got {len(changes)}"

raw=open(PROF,"r",encoding="utf-8",newline="").read()
applied=0
for aid,old,new in changes:
    # locate this action's block (map-to-vjoy has no nested <action>)
    m=re.search(r'(<action id="'+re.escape(aid)+r'"[^>]*>)(.*?)(</action>)', raw, re.S)
    if not m: sys.exit(f"block not found: {aid}")
    block=m.group(0)
    needle=f"<value>{old}</value>"
    if block.count(needle)!=1: sys.exit(f"label '{old}' not unique in {aid}: {block.count(needle)}")
    newblock=block.replace(needle, f"<value>{new}</value>")
    raw=raw[:m.start()]+newblock+raw[m.end():]
    applied+=1
assert applied==16

with open(PROF,"w",encoding="utf-8",newline="") as f:
    f.write(raw)

# validate: still parses, zero bare targets remain as labels, 16 new prefixed labels
t2=ET.parse(PROF); r2=t2.getroot()
bare=new_n=0
for a in r2.find("library").iter("action"):
    if a.get("type")!="map-to-vjoy": continue
    lv=prop(a,"action-label")
    if lv is None: continue
    if lv.text in TARGETS: bare+=1
    if re.match(r'^[LR]-(BTN\.(35|39)|MAIN-TRIGGER\.stage[12])$', lv.text or ""): new_n+=1
print(f"applied={applied}  bare-remaining={bare}  prefixed-now={new_n}")
assert bare==0 and new_n==16, "validation failed"
print("OK: parses clean, 0 bare, 16 prefixed")
