"""Fix malformed negative-direction mini-stick axis-as-button thresholds.
The 4 negative configs (L/R axis4 .left, L/R axis5 .up) use zero-width
[-1.0,-1.0] or inverted [-0.95,-1.0]; canonicalize to [-1.0,-0.95] mirroring
the positive [0.95,1.0]. Only negative-lower virtual-buttons match; preserves
BOM + line endings."""
import re, sys
P="[Enhanced] Dual TM SOL-R/Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
raw=open(P,"r",encoding="utf-8",newline="").read()
# match a virtual-button whose lower-limit is negative (the neg-direction button)
pat=re.compile(
    r'(<virtual-button>\s*<lower-limit>)(-[0-9.]+)(</lower-limit>\s*<upper-limit>)(-[0-9.]+)(</upper-limit>)')
n=0
def repl(m):
    global n
    lo,hi=m.group(2),m.group(4)
    if lo=="-1.0" and hi=="-0.95":  # already canonical
        return m.group(0)
    n+=1
    return m.group(1)+"-1.0"+m.group(3)+"-0.95"+m.group(5)
out=pat.sub(repl,raw)
if n!=4: sys.exit(f"expected 4 fixes, got {n}")
open(P,"w",encoding="utf-8",newline="").write(out)
# verify
import xml.etree.ElementTree as ET
r=ET.parse(P).getroot()
bad=0
for inp in r.find("inputs").findall("input"):
    if inp.findtext("input-type")!="axis":continue
    for ac in inp.findall("action-configuration"):
        vb=ac.find("virtual-button")
        if vb is None:continue
        lo=float(vb.findtext("lower-limit"))
        if lo<0:
            hi=float(vb.findtext("upper-limit"))
            if not(abs(lo+1.0)<1e-9 and abs(hi+0.95)<1e-9):bad+=1
print(f"fixed {n} thresholds; remaining malformed neg = {bad}")
assert bad==0
print("OK")
