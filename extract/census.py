import UnityPy, collections, os
DATA = os.environ.get("SPIRITVALE_DATA_PATH", r"D:\Steam\steamapps\common\SpiritVale\SpiritVale_Data")
KEYS=("item","merchant","vendor","shop","price","currency","recipe","loot","econom","consumable","weapon","armor")
def scan(fn):
    p=os.path.join(DATA,fn)
    if not os.path.exists(p): return
    env=UnityPy.load(p); cc=collections.Counter()
    for obj in env.objects:
        if obj.type.name!="MonoBehaviour": continue
        try:
            d=obj.read(check_read=False)
            sp=getattr(d,"m_Script",None)
            if sp is None: continue
            ms=sp.read(); cls=getattr(ms,"m_ClassName",None) or "?"
            cc[cls]+=1
        except Exception: cc["<err>"]+=1
    print(f"\n## {fn}: {sum(cc.values())} MBs, {len(cc)} classes")
    econ=[(c,n) for c,n in cc.items() if any(k in c.lower() for k in KEYS)]
    for c,n in sorted(econ,key=lambda x:-x[1])[:40]: print(f"{n:6} {c}")
for f in ("sharedassets0.assets","resources.assets"): scan(f)
