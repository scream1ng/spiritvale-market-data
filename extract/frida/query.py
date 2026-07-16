import frida, sys, json, time, argparse, os

HERE = os.path.dirname(os.path.abspath(__file__))
STAT_TYPES = json.load(open(os.path.join(HERE, "..", "..", "data", "stat_types.json"), encoding="utf-8"))
NAME_TO_STAT = {v.lower(): int(k) for k, v in STAT_TYPES.items()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("item", help="search text, e.g. 'stiletto'")
    p.add_argument("--stat", help="filter to listings that rolled this substat, e.g. 'agi'")
    p.add_argument("--pid", type=int, default=None, help="attach by PID instead of process name")
    p.add_argument("--process", default="SpiritVale.exe")
    p.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args()

    log_lines = []

    def on_message(message, data):
        if message["type"] == "send":
            log_lines.append(message["payload"])
        elif message["type"] == "error":
            log_lines.append("ERR:" + message["stack"])

    try:
        session = frida.attach(args.pid if args.pid else args.process)
    except frida.ProcessNotFoundError:
        print(f"Could not find a running process named '{args.process}'. Start the game first, or pass --pid.")
        return
    src = open(os.path.join(HERE, "combined_hook.js"), encoding="utf-8").read()
    script = session.create_script(src)
    script.on("message", on_message)
    script.load()

    resp = script.exports_sync.search(args.item)
    if not resp.get("ok"):
        print("ERROR:", resp)
        session.detach()
        return

    deadline = time.time() + args.timeout
    listings = None
    seen = len(log_lines)
    while time.time() < deadline:
        time.sleep(0.3)
        for line in log_lines[seen:]:
            if isinstance(line, str) and line.startswith("["):
                listings = json.loads(line)
        if listings is not None:
            break

    session.detach()

    if listings is None:
        print("TIMEOUT: no results (is the vending search panel open in-game?)")
        return

    if args.stat:
        stat_id = NAME_TO_STAT.get(args.stat.lower())
        if stat_id is None:
            print("unknown stat:", args.stat)
            return
        listings = [d for d in listings if any(s["type"] == stat_id for s in d.get("substats", []))]

    listings.sort(key=lambda d: int(d["price"]))
    print(f"{len(listings)} listing(s)")
    for d in listings:
        substr = ", ".join(f"{STAT_TYPES.get(str(s['type']), 't'+str(s['type']))}:{s.get('valueStr') or s['value']}" for s in d.get("substats", []))
        name = d.get("baseItemId") or d["itemId"]
        refine = f" +{d['refine']}" if d.get("refine") else ""
        print(f"{int(d['price']):>9}g  {name}{refine}  x{d['itemCount']}  [{substr}]  seller={d['sellerName']}")


if __name__ == "__main__":
    main()
