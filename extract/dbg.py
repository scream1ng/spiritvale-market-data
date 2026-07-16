import UnityPy, collections, os
DATA = os.environ.get("SPIRITVALE_DATA_PATH", r"D:\Steam\steamapps\common\SpiritVale\SpiritVale_Data")
env = UnityPy.load(os.path.join(DATA,"sharedassets0.assets"))
cc=collections.Counter(); samp=None
for obj in env.objects:
    if obj.type.name!="MonoBehaviour": continue
    try:
        d=obj.read()
        # explore attributes once
        if samp is None:
            samp=[a for a in dir(d) if not a.startswith("__")][:40]
        sp=getattr(d,"m_Script",None)
        cls="?"
        if sp is not None:
            try:
                ms=sp.read(); cls=getattr(ms,"m_ClassName",None) or getattr(ms,"m_Name","?")
            except Exception as e: cls="<scriptErr:%s>"%type(e).__name__
        else:
            cls="<noScriptAttr>"
        cc[cls]+=1
    except Exception as e:
        cc["<readErr:%s>"%type(e).__name__]+=1
print("sample attrs:",samp)
print("top classes:")
for c,n in cc.most_common(25): print(f"{n:6} {c}")
