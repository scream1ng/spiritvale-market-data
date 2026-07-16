import UnityPy, os, json, sys, re
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
DATA=os.environ.get("SPIRITVALE_DATA_PATH", r"D:\Steam\steamapps\common\SpiritVale\SpiritVale_Data")
OUT=r"E:\Coding Project\spiritvale-market-data\data"; os.makedirs(OUT,exist_ok=True)
ICON_DIR=os.path.join(OUT,"icons"); os.makedirs(ICON_DIR,exist_ok=True)
ITEM_CLASSES=["ItemConfig","ConsumableConfig","GemConfig","CardConfig","JunkConfig","WeaponConfig","EquipConfig"]
ITYPE=["Junk","Consumable","Equip","Artifact","Card","Gem","Cosmetic"]

def safe_filename(id_):
    return re.sub(r"[^A-Za-z0-9_\- ]", "_", id_) + ".png"

def export_icon(obj, sprite_ref, id_):
    if not sprite_ref or not sprite_ref.get("m_PathID"): return
    fn = safe_filename(id_)
    path = os.path.join(ICON_DIR, fn)
    if os.path.exists(path): return
    try:
        sprite_obj = obj.assets_file.objects[sprite_ref["m_PathID"]]
        sprite_obj.read().image.save(path)
    except Exception: pass

gen=TypeTreeGenerator("6000.0.64f1"); gen.load_local_dll_folder(os.path.join("dumpout","DummyDll"))
_c={}
def tt(name):
    if name not in _c:
        ns=gen.get_nodes("Assembly-CSharp",name)
        _c[name]=[{"m_Level":n.m_Level,"m_Type":n.m_Type,"m_Name":n.m_Name,"m_MetaFlag":n.m_MetaFlag} for n in ns]
    return _c[name]

def clsname(obj):
    try: return obj.read(check_read=False).m_Script.read().m_ClassName
    except Exception: return None

items={}; merchants=[]
def harvest(path,label):
    env=UnityPy.load(path)
    for obj in env.objects:
        if obj.type.name!="MonoBehaviour": continue
        cn=clsname(obj)
        if cn in ITEM_CLASSES:
            try:
                d=obj.read_typetree(tt(cn))
                items[obj.path_id]={"path_id":obj.path_id,"cls":cn,"id":d.get("Id"),
                    "name":d.get("DisplayName"),"desc":d.get("Description"),
                    "drop_chance":d.get("DropChance"),"src":label}
                if d.get("Id"): export_icon(obj, d.get("Sprite"), d.get("Id"))
            except Exception as e: pass
        elif cn=="MerchantConfig":
            try:
                d=obj.read_typetree(tt("MerchantConfig"))
                merchants.append({"path_id":obj.path_id,"src":label,"inventory":d.get("Inventory",[])})
            except Exception as e: pass

for fn in ("sharedassets0.assets","resources.assets"):
    p=os.path.join(DATA,fn)
    if os.path.exists(p): harvest(p,fn); print("scanned",fn,"items=",len(items))

# join merchant entries -> item name via path_id
prices=[]
for m in merchants:
    for e in m["inventory"]:
        pid=e.get("Item",{}).get("m_PathID")
        it=items.get(pid)
        prices.append({"merchant_path_id":m["path_id"],"entry_name":e.get("Name"),
            "item_path_id":pid,"item_id":(it or {}).get("id"),
            "item_name":(it or {}).get("name"),"price":e.get("Price")})

json.dump(list(items.values()),open(os.path.join(OUT,"items.json"),"w"),indent=1,default=str)
json.dump(prices,open(os.path.join(OUT,"merchant_prices.json"),"w"),indent=1,default=str)
print("\nITEMS:",len(items)," MERCHANTS:",len(merchants)," PRICE ROWS:",len(prices))
print("\nMerchant prices (joined):")
for r in prices: print(f"  {r['price']:>7}  {r['item_name'] or r['entry_name']}  [{r['item_id']}]")
