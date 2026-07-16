import os
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
gen=TypeTreeGenerator("6000.0.64f1")
gen.load_local_dll_folder(os.path.join("dumpout","DummyDll"))
n=gen.get_nodes("Assembly-CSharp","MerchantConfig")
print("type:",type(n),"len:",len(n) if hasattr(n,'__len__') else '?')
print("elem0 type:",type(n[0]))
e=n[0]
print("elem0 attrs:",[a for a in dir(e) if not a.startswith('_')][:20])
for x in n[:6]:
    print(getattr(x,'m_Level',getattr(x,'level','?')), getattr(x,'m_Type',getattr(x,'type','?')), getattr(x,'m_Name',getattr(x,'name','?')))
