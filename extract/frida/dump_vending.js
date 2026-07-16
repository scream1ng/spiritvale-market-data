require("./il2cpp-bridge.js");

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
    const GameClass = image.class("Game");
    console.log("Game class found:", GameClass.handle);

    const games = Il2Cpp.gc.choose(GameClass);
    console.log("Game instances:", games.length);
    if (games.length === 0) { console.log("NO_GAME_INSTANCE"); return; }
    const game = games[0];

    const vending = game.field("Vending").value;
    console.log("Vending manager null?", vending.isNull());
    if (vending.isNull()) { console.log("NO_VENDING_MANAGER"); return; }

    const listMethod = vending.method("RequestItemList", 1);
    const list = listMethod.invoke(Il2Cpp.string(""));
    const count = list.method("get_Count").invoke();
    console.log("ItemData count:", count);

    const out = [];
    for (let i = 0; i < count; i++) {
        try {
            const item = list.method("get_Item", 1).invoke(i);
            const listing = item.field("Listing").value;
            if (listing.isNull()) continue;
            out.push({
                itemId: s(listing.method("get_ItemId").invoke()),
                price: listing.method("get_Price").invoke().toString(),
                itemCount: listing.method("get_Count").invoke(),
                sellerName: s(listing.method("get_SellerName").invoke()),
                sellerId: s(listing.method("get_SellerId").invoke()),
                expiresAt: listing.method("get_ExpiresAt").invoke().toString()
            });
        } catch (e) {
            out.push({ error: e.message });
        }
    }
    console.log("RESULT_JSON_START");
    console.log(JSON.stringify(out));
    console.log("RESULT_JSON_END");
});
