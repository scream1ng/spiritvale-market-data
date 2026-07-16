import frida, json, time, os, re, threading
from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "..", "data")
ICON_DIR = os.path.join(DATA_DIR, "icons")
STAT_TYPES = json.load(open(os.path.join(DATA_DIR, "stat_types.json"), encoding="utf-8"))
ITEMS = json.load(open(os.path.join(DATA_DIR, "items.json"), encoding="utf-8"))
ID_TO_NAME = {i["id"]: i["name"] for i in ITEMS if i.get("id") and i.get("name")}
ICON_FILES = set(os.listdir(ICON_DIR)) if os.path.isdir(ICON_DIR) else set()


def icon_filename(id_):
    if not id_:
        return None
    fn = re.sub(r"[^A-Za-z0-9_\- ]", "_", id_) + ".png"
    return fn if fn in ICON_FILES else None

PROCESS_NAME = os.environ.get("SPIRITVALE_PROCESS", "SpiritVale.exe")

app = Flask(__name__)

log_lines = []
lock = threading.Lock()


def on_message(message, data):
    if message["type"] == "send":
        with lock:
            log_lines.append(message["payload"])


pid_override = os.environ.get("SPIRITVALE_PID")
try:
    session = frida.attach(int(pid_override) if pid_override else PROCESS_NAME)
except frida.ProcessNotFoundError:
    raise SystemExit(
        f"Could not find a running process named '{PROCESS_NAME}'. "
        "Start SpiritVale first, or set SPIRITVALE_PID/SPIRITVALE_PROCESS if it's named differently."
    )
script = session.create_script(open(os.path.join(HERE, "combined_hook.js"), encoding="utf-8").read())
script.on("message", on_message)
script.load()


def display_name(base_item_id):
    return ID_TO_NAME.get(base_item_id, base_item_id)


@app.route("/icons/<path:filename>")
def icons(filename):
    return send_from_directory(ICON_DIR, filename)


@app.route("/api/stat-types")
def api_stat_types():
    pairs = sorted(((int(k), v) for k, v in STAT_TYPES.items() if int(k) >= 0), key=lambda p: p[1])
    return jsonify(pairs)


@app.route("/api/inventory")
def api_inventory():
    resp = script.exports_sync.inventory()
    if not resp.get("ok"):
        return jsonify(resp), 500
    for it in resp["items"]:
        it["displayName"] = display_name(it["baseItemId"])
        it["icon"] = icon_filename(it["baseItemId"])
    return jsonify(resp)


@app.route("/api/price")
def api_price():
    query = request.args.get("item", "").strip()
    if not query:
        return jsonify({"error": "missing item param"}), 400

    with lock:
        seen = len(log_lines)
    resp = script.exports_sync.search(query)
    if not resp.get("ok"):
        return jsonify({"error": resp}), 400

    deadline = time.time() + 15
    listings = None
    while time.time() < deadline:
        time.sleep(0.2)
        with lock:
            new_lines = log_lines[seen:]
            seen = len(log_lines)
        for line in new_lines:
            if isinstance(line, str) and line.startswith("["):
                listings = json.loads(line)
        if listings is not None:
            break

    if listings is None:
        return jsonify({"error": "timeout waiting for search results"}), 504

    for l in listings:
        l["price"] = int(l["price"])
        key = l.get("baseItemId") or l["itemId"]
        l["displayName"] = ID_TO_NAME.get(key) or l.get("searchText") or key
        l["icon"] = icon_filename(key)
        for st in l.get("substats", []):
            st["typeName"] = STAT_TYPES.get(str(st["type"]), "t" + str(st["type"]))

    listings.sort(key=lambda l: l["price"])
    return jsonify({"query": query, "count": len(listings), "listings": listings})


INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SpiritVale Market</title>
<style>
  :root { --bg: #14141a; --card: #1c1c24; --border: #2c2c36; --accent: #3a5fd9; --accent2: #4a6fe9; --text: #e8e8ea; --muted: #8c8c96; --gold: #f0c674; --tag: #262632; --tagtext: #7fd8ff; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  .cards { display: flex; flex-direction: row; flex-wrap: wrap; align-items: flex-start; gap: 24px; max-width: 1400px; margin: 0 auto; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px 24px; min-width: 0; }
  .card.wide { flex: 2 1 560px; }
  .card.narrow { flex: 1 1 340px; }
  .card-head { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; }
  .card-title { font-size: 18px; font-weight: 700; margin: 0 0 4px 0; }
  .card-sub { color: var(--muted); font-size: 13px; margin: 0; }
  .stats { display: flex; gap: 28px; flex-wrap: wrap; }
  .stat-label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
  .stat-value { font-size: 20px; font-weight: 700; margin-top: 2px; }
  .controls { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
  button { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
  button:hover { background: var(--accent2); }
  button:disabled { background: #3a3a44; cursor: default; }
  button.small { padding: 5px 12px; font-size: 12px; }
  input[type=text], select { background: #262630; border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 13px; }
  input[type=text] { flex: 1; min-width: 180px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
  tr:hover td { background: #22222c; }
  .price { color: var(--gold); font-weight: 700; }
  .stat-tag { display: inline-block; background: var(--tag); border-radius: 4px; padding: 2px 7px; margin: 1px 3px 1px 0; font-size: 11px; color: var(--tagtext); cursor: pointer; }
  .stat-tag:hover { background: #33334a; }
  .seller { color: var(--muted); }
  .item-cell { display: flex; align-items: center; gap: 10px; }
  .item-icon { width: 32px; height: 32px; border-radius: 6px; background: #262630; object-fit: contain; flex-shrink: 0; }
  .item-icon.placeholder { display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--muted); }
  .empty { color: var(--muted); font-size: 13px; padding: 16px 0; }
  .pager { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
  .pager button:disabled { opacity: .4; }
</style>
</head>
<body>

<div class="cards">

  <div class="card wide">
    <div class="card-head">
      <div>
        <p class="card-title">Price Check</p>
        <p class="card-sub">Live prices pulled from the vending market. Leech-type substats may be &plusmn;1.</p>
      </div>
      <div class="stats" id="priceStats"></div>
    </div>
    <div class="controls">
      <input type="text" id="itemInput" placeholder="item name">
      <button onclick="checkPrice(document.getElementById('itemInput').value)">Check Price</button>
      <select id="statFilter" onchange="renderListings()"><option value="">All substats</option></select>
    </div>
    <div id="priceBox"><div class="empty">Search an item to see live listings.</div></div>
  </div>

  <div class="card narrow">
    <div class="card-head">
      <div>
        <p class="card-title">Inventory</p>
        <p class="card-sub">Keep the game running with the vending search panel opened at least once.</p>
      </div>
      <div class="stats">
        <div><div class="stat-label">Items</div><div class="stat-value" id="invCount">&mdash;</div></div>
      </div>
    </div>
    <div class="controls">
      <button onclick="loadInventory()">Scan Inventory</button>
    </div>
    <table id="invTable"><thead><tr><th>Item</th><th>Qty</th><th>Refine</th><th></th></tr></thead><tbody></tbody></table>
    <div class="pager">
      <span id="invPageInfo" class="stat-label"></span>
      <button class="small" id="invPrev" onclick="invPage--; renderInventory()">&laquo; Prev</button>
      <button class="small" id="invNext" onclick="invPage++; renderInventory()">Next &raquo;</button>
    </div>
  </div>

</div>

<script>
let lastListings = [];

function iconImg(it) {
  return it.icon
    ? `<img class="item-icon" src="/icons/${encodeURIComponent(it.icon)}">`
    : `<div class="item-icon placeholder">?</div>`;
}

async function loadStatTypes() {
  const res = await fetch('/api/stat-types');
  const pairs = await res.json();
  const sel = document.getElementById('statFilter');
  for (const [id, name] of pairs) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = name;
    sel.appendChild(opt);
  }
}
loadStatTypes();

let lastInventory = [];
let invPage = 0;
const INV_PAGE_SIZE = 10;

async function loadInventory() {
  const res = await fetch('/api/inventory');
  const data = await res.json();
  if (!data.ok) {
    document.querySelector('#invTable tbody').innerHTML = '<tr><td colspan=4>' + JSON.stringify(data) + '</td></tr>';
    return;
  }
  lastInventory = data.items;
  invPage = 0;
  renderInventory();
}

function renderInventory() {
  const tbody = document.querySelector('#invTable tbody');
  tbody.innerHTML = '';
  document.getElementById('invCount').textContent = lastInventory.length;

  const pageCount = Math.max(1, Math.ceil(lastInventory.length / INV_PAGE_SIZE));
  invPage = Math.max(0, Math.min(invPage, pageCount - 1));
  const start = invPage * INV_PAGE_SIZE;
  const pageItems = lastInventory.slice(start, start + INV_PAGE_SIZE);

  for (const it of pageItems) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><div class="item-cell">${iconImg(it)}<span>${it.displayName}</span></div></td>
      <td>${it.count}</td><td>${it.refine || ''}</td>
      <td><button class="small" onclick="checkPrice('${it.displayName.replace(/'/g, "\\\\'")}')">Check Price</button></td>`;
    tbody.appendChild(tr);
  }

  const shownTo = lastInventory.length === 0 ? 0 : start + pageItems.length;
  document.getElementById('invPageInfo').textContent =
    lastInventory.length === 0 ? '' : `Showing ${start + 1}-${shownTo} of ${lastInventory.length}`;
  document.getElementById('invPrev').disabled = invPage === 0;
  document.getElementById('invNext').disabled = invPage >= pageCount - 1;
}

async function checkPrice(item) {
  document.getElementById('itemInput').value = item;
  document.getElementById('statFilter').value = '';
  const box = document.getElementById('priceBox');
  box.innerHTML = '<div class="empty">searching...</div>';
  document.getElementById('priceStats').innerHTML = '';
  const res = await fetch('/api/price?item=' + encodeURIComponent(item));
  const data = await res.json();
  if (data.error) { box.innerHTML = '<div class="empty">Error: ' + JSON.stringify(data.error) + '</div>'; return; }
  lastListings = data.listings || [];
  renderListings();
}

function filterByStat(type) {
  document.getElementById('statFilter').value = String(type);
  renderListings();
}

function renderListings() {
  const box = document.getElementById('priceBox');
  const statsBox = document.getElementById('priceStats');
  const statFilter = document.getElementById('statFilter').value;

  const listings = statFilter
    ? lastListings.filter(l => (l.substats || []).some(s => String(s.type) === statFilter))
    : lastListings;

  if (listings.length === 0) {
    box.innerHTML = '<div class="empty">No listings match.</div>';
    statsBox.innerHTML = '';
    return;
  }

  const prices = listings.map(l => l.price);
  const median = prices[Math.floor(prices.length / 2)];
  const lowest = prices[0];
  statsBox.innerHTML = `
    <div><div class="stat-label">Lowest</div><div class="stat-value price">${lowest.toLocaleString()}g</div></div>
    <div><div class="stat-label">Median</div><div class="stat-value price">${median.toLocaleString()}g</div></div>
    <div><div class="stat-label">Offers</div><div class="stat-value">${listings.length}</div></div>`;
  let html = '<table><thead><tr><th>Item</th><th>Price</th><th>Qty</th><th>Refine</th><th>Substats</th><th>Seller</th></tr></thead><tbody>';
  for (const l of listings) {
    const substr = (l.substats || []).map(s => {
      const val = (s.displayValue !== undefined && s.displayValue !== null) ? ('+' + s.displayValue) : (s.value + '/100');
      const hl = statFilter && String(s.type) === statFilter ? ' style="background:#3a5fd9;color:#fff"' : '';
      return `<span class="stat-tag"${hl} onclick="filterByStat(${s.type})">${s.typeName} ${val}</span>`;
    }).join('');
    html += `<tr><td><div class="item-cell">${iconImg(l)}<span>${l.displayName}</span></div></td>
      <td class="price">${l.price.toLocaleString()}g</td><td>${l.itemCount}</td><td>${l.refine || ''}</td>
      <td>${substr}</td><td class="seller">${l.sellerName}</td></tr>`;
  }
  html += '</tbody></table>';
  box.innerHTML = html;
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return INDEX_HTML


if __name__ == "__main__":
    app.run(port=5151, debug=False)
