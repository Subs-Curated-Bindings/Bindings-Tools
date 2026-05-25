import sys, xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding="utf-8")
tree = ET.parse(r"C:\Users\subli\OneDrive\Desktop\nxt-chart-machine-readable.svg")
root = tree.getroot()

def gather(elem):
    parts = []
    for t in elem.iter():
        tag = t.tag.split('}',1)[-1]
        if tag in ('text','tspan') and t.text:
            parts.append(t.text)
    return ' '.join(parts)

# Probe specific IDs
targets = ['bind.L-B1', 'bind.L-A3.up', 'bind.L-F1', 'bind.L-F2', 'bind.L-F3', 'bind.L-T1.up', 'bind.MAIN-TRIG-L']
for elem in root.iter():
    eid = elem.attrib.get('id', '')
    if eid in targets:
        tag = elem.tag.split('}', 1)[-1]
        text = gather(elem)
        text_clean = ' '.join(text.split())[:120]
        print(f"  {eid:25s} <{tag}>  text={text_clean!r}")
