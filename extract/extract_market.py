import UnityPy, os, json
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
DATA=os.environ.get("SPIRITVALE_DATA_PATH", r"D:\Steam\steamapps\common\SpiritVale\SpiritVale_Data")
gen=TypeTreeGenerator("6000.0.64f1")
gen.load_local_dll_folder(os.path.join("dumpout","DummyDll"))
_cache={}
def tt(name, asm="Assembly-CSharp"):
    if name not in _cache:
        ns=gen.get_nodes(asm,name)
        _cache[name]=[{"m_Level":n.m_Level,"m_Type":n.m_Type,"m_Name":n.m_Name,
                       "m_MetaFlag":n.m_MetaFlag} for n in ns]
    return _cache[name]

env=UnityPy.load(os.path.join(DATA,"sharedassets0.assets"))
by_cls={}
for obj in env.objects:
    if obj.type.name!="MonoBehaviour": continue
    try:
        d=obj.read(check_read=False); by_cls.setdefault(d.m_Script.read().m_ClassName,[]).append(obj)
    except Exception: pass

mc=by_cls["MerchantConfig"][0].read_typetree(tt("MerchantConfig"))
inv=mc["Inventory"]
print("MerchantConfig.Inventory entries:",len(inv))
print(json.dumps(inv[:6],indent=1,default=str))
