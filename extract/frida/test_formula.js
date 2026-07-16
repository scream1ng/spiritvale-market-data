Il2Cpp.perform(() => {
    const img = Il2Cpp.domain.assembly("Assembly-CSharp").image;
    const gsCls = img.class("GameServerConfig");
    const instances = Il2Cpp.gc.choose(gsCls);
    send("GameServerConfig instances: " + instances.length);
    if (instances.length === 0) return;
    const gsc = instances[0];
    const equips = gsc.field("Equips").value;
    const count = equips.method("get_Count").invoke();
    send("Equips count: " + count);
    let target = null;
    for (let i = 0; i < count; i++) {
        const e = equips.method("get_Item", 1).invoke(i);
        const id = e.field("Id").value;
        if (id && !id.isNull() && id.content === "Kunai") { target = e; break; }
    }
    if (!target) { send("Kunai not found"); return; }
    send("found Kunai EquipConfig, Substats tag=" + target.field("Substats").value);

    const formulaCls = img.class("Formula");
    const runtime = formulaCls.method("GetSubstatConfig", 1).invoke(target);
    send("runtime null? " + runtime.isNull());

    const getRange = formulaCls.method("GetSubstatRange", 4);
    const getRangeText = formulaCls.method("GetSubstatRangeText", 2);
    const getScaled = formulaCls.method("GetSubstatScaledValue", 1);

    const int32Type = Il2Cpp.corlib.class("System.Int32").type;
    for (const [name, type, raw, expected] of [["Agi", 2, 79, 3], ["MatkMult", 70, 17, 4], ["Leech", 98, 2, 3]]) {
        const minRef = Il2Cpp.reference(0, int32Type);
        const maxRef = Il2Cpp.reference(0, int32Type);
        getRange.invoke(type, runtime, minRef, maxRef);
        const min = minRef.value, max = maxRef.value;
        const scaled = getScaled.invoke(raw);
        const computed = min + (max - min) * scaled;
        send(name + ": range=[" + min + "~" + max + "] raw=" + raw + " scaled=" + scaled +
            " computed=" + computed + " round=" + Math.round(computed) + " expectedDisplay=+" + expected);
    }
});

function s(v) {
    try { return v.isNull() ? null : v.content; } catch (e) { return "<err>"; }
}
