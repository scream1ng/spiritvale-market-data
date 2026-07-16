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
    const popupCls = image.class("UIItemPopup");
    const statItemCls = image.class("UIStatItem");

    const popupDraw = popupCls.method("Draw", 3);
    const statDraw = statItemCls.method("Draw", 4);
    log("popup Draw at " + popupDraw.virtualAddress + ", statitem Draw at " + statDraw.virtualAddress);

    let currentItem = null;
    let capturedLines = [];

    Interceptor.attach(popupDraw.virtualAddress, {
        onEnter(args) {
            try {
                const data = new Il2Cpp.Object(args[1]);
                capturedLines = [];
                currentItem = null;
                if (data.isNull()) return;
                const className = data.class.name;
                if (className === "EquipData") {
                    const substats = data.method("get_Substats").invoke();
                    const rawSubstats = [];
                    if (!substats.isNull()) {
                        const sc = substats.method("get_Count").invoke();
                        for (let j = 0; j < sc; j++) {
                            const stat = substats.method("get_Item", 1).invoke(j);
                            rawSubstats.push({
                                type: stat.method("get_Type").invoke().field("value__").value,
                                rawValue: stat.method("get_Value").invoke()
                            });
                        }
                    }
                    currentItem = {
                        baseItemId: s(data.method("get_Id").invoke()),
                        refine: data.method("get_Refine").invoke(),
                        substatsRaw: rawSubstats
                    };
                }
            } catch (e) {
                log("POPUP_HOOK_ERROR " + e.message);
            }
        },
        onLeave(retval) {
            if (currentItem === null) return;
            log("TOOLTIP_RESULT_START");
            log(JSON.stringify({ item: currentItem, lines: capturedLines }));
            log("TOOLTIP_RESULT_END");
        }
    });

    Interceptor.attach(statDraw.virtualAddress, {
        onEnter(args) {
            this.self = args[0];
            log("STAT_DRAW_CALLED self=" + args[0]);
        },
        onLeave(retval) {
            try {
                const uiItem = new Il2Cpp.Object(this.self);
                const valueField = uiItem.field("Value").value;
                log("STAT_DRAW_LEAVE valueFieldNull=" + valueField.isNull());
                if (!valueField.isNull()) {
                    const text = valueField.method("get_text", 0).invoke();
                    log("STAT_DRAW_TEXT=" + s(text));
                    capturedLines.push(s(text));
                }
            } catch (e) {
                log("STATITEM_HOOK_ERROR " + e.message + "\n" + e.stack);
            }
        }
    });

    const statDrawStr = statItemCls.method("Draw", 1);
    if (statDrawStr) {
        Interceptor.attach(statDrawStr.virtualAddress, {
            onEnter(args) {
                this.self = args[0];
            },
            onLeave(retval) {
                try {
                    const uiItem = new Il2Cpp.Object(this.self);
                    const valueField = uiItem.field("Value").value;
                    if (!valueField.isNull()) {
                        const text = valueField.method("get_text", 0).invoke();
                        log("STAT_DRAW_STR_TEXT=" + s(text));
                        capturedLines.push(s(text));
                    }
                } catch (e) {
                    log("STATITEM_STR_HOOK_ERROR " + e.message);
                }
            }
        });
    }

    log("HOOK_INSTALLED");
});
