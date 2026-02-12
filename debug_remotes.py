import json

d = json.load(open(r"C:\Users\colin\.o3de\resolved_o3de_manifest.json"))
objs = d["objects"]

print("=== REPO OBJECTS ===")
for name, o in objs.items():
    if o.get("type") == "repo":
        children = o.get("children", [])
        remotes = o.get("remotes", [])
        print(f"{name}: children={len(children)}, remotes={remotes}")
        for c in children[:5]:
            co = objs.get(c, {})
            print(f"  child: {c} -> type={co.get('type', '?')}")
        if len(children) > 5:
            print(f"  ... and {len(children)-5} more")

print()
print("=== MANIFEST ROOT ===")
mr = d["manifest_root"]
ar = mr.get("all_remotes", [])
types = {}
for e in ar:
    t = e.get("type", "?")
    types[t] = types.get(t, 0) + 1
print(f"all_remotes: {len(ar)} total, breakdown: {types}")
for e in ar:
    print(f"  {e}")

print()
print("=== ENGINE ALL REMOTES ===")
eng = objs["org.o3de.engine.o3de"]
ear = eng.get("all_remotes", [])
etypes = {}
for e in ear:
    t = e.get("type", "?")
    etypes[t] = etypes.get(t, 0) + 1
print(f"all_remotes: {len(ear)} total, breakdown: {etypes}")
