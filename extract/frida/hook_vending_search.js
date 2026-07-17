function log(msg) { send(String(msg)); }

function s(v) {
    try {
        if (v === null || v === undefined) return null;
        if (v.isNull && v.isNull()) return null;
        if (v.content !== undefined) return v.content;
        return v.toString();
    } catch (e) { return "<err:" + e.message + ">"; }
}

Il2Cpp.perform(() => {
    const image = Il2Cpp.domain.assembly("Assembly-CSharp").image;
    const cls = image.class("UIVendingSearch");
    const method = cls.method("<Search>b__10_0", 1);
    log("hooking " + method.name + " at " + method.virtualAddress);

    const formulaCls = image.class("Formula");
    const getSubstatConfigMethod = formulaCls.method("GetSubstatConfig", 1);
    const getSubstatRangeMethod = formulaCls.method("GetSubstatRange", 4);
    const int32Type = Il2Cpp.corlib.class("System.Int32").type;

    const equipConfigById = {};
    try {
        const gsInstances = Il2Cpp.gc.choose(image.class("GameServerConfig"));
        if (gsInstances.length > 0) {
            const equips = gsInstances[0].field("Equips").value;
            const ec = equips.method("get_Count").invoke();
            for (let i = 0; i < ec; i++) {
                const e = equips.method("get_Item", 1).invoke(i);
                const id = s(e.field("Id").value);
                if (id) equipConfigById[id] = e;
            }
        }
        log("EquipConfig cache built: " + Object.keys(equipConfigById).length + " entries");
    } catch (e) {
        log("EQUIP_CONFIG_CACHE_ERROR " + e.message);
    }

    const getArtifactSubstatConfigMethod = formulaCls.method("GetArtifactSubstatConfig", 0);
    let artifactRuntime = null;
    try { artifactRuntime = getArtifactSubstatConfigMethod.invoke(); } catch (e) { log("ARTIFACT_SUBSTAT_CONFIG_ERROR " + e.message); }

    const substatRuntimeCache = {};
    function getSubstatRuntime(baseItemId, isArtifact) {
        if (isArtifact) return artifactRuntime;
        if (baseItemId in substatRuntimeCache) return substatRuntimeCache[baseItemId];
        const config = equipConfigById[baseItemId];
        const runtime = config ? getSubstatConfigMethod.invoke(config) : null;
        substatRuntimeCache[baseItemId] = runtime;
        return runtime;
    }

    // displayed value = floor(min + (max-min) * raw/100), derived from the game's own
    // Formula.GetSubstatRange. Formula.GetSubstatScaledValue was previously used for the
    // raw->fraction step, but instrumenting it live showed it only spans ~0.667-1.0 over
    // raw 0-100 (not 0-1), which silently biased every display toward the top of its range
    // regardless of the actual roll - confirmed via a live Kunai listing with a low raw
    // CritDamage roll (5/100) still rendering near max. raw/100 is the game's own convention
    // for substat rolls (see the "value/100" fallback display elsewhere in this project).
    function computeDisplayValue(baseItemId, statType, rawValue, isArtifact) {
        const runtime = getSubstatRuntime(baseItemId, isArtifact);
        if (!runtime || runtime.isNull()) return null;
        const minRef = Il2Cpp.reference(0, int32Type);
        const maxRef = Il2Cpp.reference(0, int32Type);
        const ok = getSubstatRangeMethod.invoke(statType, runtime, minRef, maxRef);
        if (!ok) return null;
        const min = minRef.value, max = maxRef.value;
        const display = Math.floor(min + (max - min) * (rawValue / 100));
        return { min, max, display };
    }

    Interceptor.attach(method.virtualAddress, {
        onEnter(args) {
            try {
                const list = new Il2Cpp.Object(args[1]);
                const count = list.method("get_Count").invoke();
                log("SEARCH_CALLBACK count=" + count);
                const out = [];
                for (let i = 0; i < count; i++) {
                    const item = list.method("get_Item", 1).invoke(i);
                    const listing = item.field("Listing").value;
                    if (listing.isNull()) continue;
                    const row = {
                        itemId: s(listing.method("get_ItemId").invoke()),
                        searchText: s(item.field("SearchText").value),
                        price: listing.method("get_Price").invoke().toString(),
                        itemCount: listing.method("get_Count").invoke(),
                        sellerName: s(listing.method("get_SellerName").invoke()),
                        sellerId: s(listing.method("get_SellerId").invoke()),
                        expiresAt: listing.method("get_ExpiresAt").invoke().toString(),
                        json: s(listing.method("get_Json").invoke()),
                        refine: null,
                        substats: []
                    };
                    try {
                        const equip = listing.method("GetItem", 0).invoke();
                        if (!equip.isNull()) {
                            row.baseItemId = s(equip.method("get_Id").invoke());
                        }
                        const clsName = equip.isNull() ? null : equip.class.name;
                        const isArtifact = clsName === "ArtifactData";
                        if (!equip.isNull() && (clsName === "EquipData" || isArtifact || clsName === "GemData" || clsName === "CosmeticData")) {
                            try { row.refine = equip.method("get_Refine").invoke(); } catch (e4) {}
                            const substats = equip.method("get_Substats").invoke();
                            if (!substats.isNull()) {
                                const sc = substats.method("get_Count").invoke();
                                for (let j = 0; j < sc; j++) {
                                    const stat = substats.method("get_Item", 1).invoke(j);
                                    const type = stat.method("get_Type").invoke().field("value__").value;
                                    const value = stat.method("get_Value").invoke();
                                    const entry = { type, value };
                                    try {
                                        const computed = computeDisplayValue(row.baseItemId, type, value, isArtifact);
                                        if (computed) {
                                            entry.displayValue = computed.display;
                                            entry.range = [computed.min, computed.max];
                                        }
                                    } catch (e3) { entry.computeError = e3.message; }
                                    row.substats.push(entry);
                                }
                            }
                        }
                    } catch (e2) {
                        row.substatError = e2.message;
                    }
                    out.push(row);
                }
                log("RESULT_JSON_START");
                log(JSON.stringify(out));
                log("RESULT_JSON_END");
            } catch (e) {
                log("HOOK_ERROR " + e.message + "\n" + e.stack);
            }
        }
    });
    log("HOOK_INSTALLED");

    rpc.exports = {
        async search(text) {
            return await Il2Cpp.perform(() => {
                const searchCls = Il2Cpp.domain.assembly("Assembly-CSharp").image.class("UIVendingSearch");
                const instances = Il2Cpp.gc.choose(searchCls);
                if (instances.length === 0) return { error: "NO_SEARCH_UI_INSTANCE" };
                instances[0].method("Search", 2).invoke(Il2Cpp.string(text), true);
                return { ok: true };
            });
        },
        async inventory() {
            return await Il2Cpp.perform(() => {
                const img = Il2Cpp.domain.assembly("Assembly-CSharp").image;
                const gameCls = img.class("Game");
                const games = Il2Cpp.gc.choose(gameCls);
                if (games.length === 0) return { error: "NO_GAME_INSTANCE" };
                const player = games[0].method("get_Player").invoke();
                if (player.isNull()) return { error: "NO_PLAYER" };
                const charData = player.method("get_CharacterData").invoke();
                if (charData.isNull()) return { error: "NO_CHARACTER_DATA" };
                const inv = charData.method("get_Inventory").invoke();
                if (inv.isNull()) return { error: "NO_INVENTORY" };

                const getItems = img.class("InventoryExtensions").method("GetItems", 1);
                const items = getItems.invoke(inv);
                const count = items.method("get_Count").invoke();

                const out = [];
                for (let i = 0; i < count; i++) {
                    const item = items.method("get_Item", 1).invoke(i);
                    const row = { cls: item.class.name, baseItemId: s(item.method("get_Id").invoke()), count: 1 };
                    try { row.count = item.method("get_Count").invoke(); } catch (e) {}
                    try { row.refine = item.method("get_Refine").invoke(); } catch (e) {}
                    out.push(row);
                }
                return { ok: true, items: out };
            });
        }
    };
});
