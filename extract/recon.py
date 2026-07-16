import UnityPy, collections, sys, os
DATA = os.environ.get("SPIRITVALE_DATA_PATH", r"D:\Steam\steamapps\common\SpiritVale\SpiritVale_Data")
targets = ["sharedassets0.assets", "resources.assets", "globalgamemanagers.assets"]
counts = collections.Counter()
econ = collections.Counter()
KEYS = ("item","merchant","vendor","shop","price","currency","loot","recipe","economy")
for fn in targets:
    p = os.path.join(DATA, fn)
    if not os.path.exists(p): continue
    env = UnityPy.load(p)
    n=0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour": continue
        n+=1
        try:
            d = obj.read()
            sp = getattr(d, "m_Script", None)
            cls = "?"
            if sp:
                ms = sp.read()
                cls = getattr(ms, "m_ClassName", None) or getattr(ms, "m_Name", "?")
            counts[cls]+=1
            if any(k in cls.lower() for k in KEYS):
                econ[cls]+=1
        except Exception as e:
            counts["<err:%s>"%type(e).__name__]+=1
    print(f"[{fn}] MonoBehaviours={n}")
print("\n=== ECONOMY-RELATED CLASSES ===")
for c,n in econ.most_common(40): print(f"{n:5}  {c}")
print(f"\nTotal distinct MB classes: {len(counts)}")
