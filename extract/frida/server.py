import frida, json, time, os, re, sys, subprocess, tempfile, threading, urllib.request, webbrowser, logging
from flask import Flask, jsonify, request, send_from_directory

sys.stdout.reconfigure(line_buffering=True)

try:
    from _version import VERSION
except ImportError:
    VERSION = "0"

def version_tuple(s):
    return tuple(int(p) for p in s.split("."))

RELEASES_API = "https://api.github.com/repos/scream1ng/spiritvale-market-data/releases/latest"

def check_for_update():
    if not getattr(sys, "frozen", False):
        return
    try:
        req = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            rel = json.load(r)
        remote_version = rel["tag_name"].lstrip("v")
        if version_tuple(remote_version) <= version_tuple(VERSION):
            return
        asset = next((a for a in rel["assets"] if a["name"] == "SpiritValeMarket.exe"), None)
        if not asset:
            return
        print(f"Update available: v{VERSION} -> v{remote_version}, downloading...")
        new_path = sys.executable + ".new"
        urllib.request.urlretrieve(asset["browser_download_url"], new_path)
        updater = os.path.join(tempfile.gettempdir(), "svm_update.bat")
        with open(updater, "w") as f:
            f.write(f"""@echo off
set count=0
:wait
move /y "{new_path}" "{sys.executable}" >nul 2>&1
if not errorlevel 1 goto launch
set /a count+=1
if %count% geq 30 goto failed
timeout /t 1 /nobreak >nul
goto wait
:launch
start "" "{sys.executable}"
del "%~f0"
exit
:failed
echo Update failed: could not replace SpiritValeMarket.exe after 30 seconds.
echo The file may be locked by another process. Try running SpiritValeMarket.exe manually.
pause
del "%~f0"
""")
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(["cmd", "/c", updater], creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, close_fds=True)
        except OSError:
            subprocess.Popen(["cmd", "/c", updater], creationflags=flags, close_fds=True)
        print("Restarting to apply update...")
        os._exit(0)
    except Exception as e:
        print(f"Update check failed (continuing): {e}")

check_for_update()

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", HERE)
DATA_DIR = os.path.join(HERE, "data") if os.path.isdir(os.path.join(HERE, "data")) else os.path.join(HERE, "..", "..", "data")
ICON_DIR = os.path.join(DATA_DIR, "icons")
STAT_TYPES = json.load(open(os.path.join(DATA_DIR, "stat_types.json"), encoding="utf-8"))
PERCENT_STAT_TYPES = {48, 52, 57, 58, 63, 64, 68, 69, 70, 71, 72, 73, 74, 75, 76, 80, 90, 98, 102, 121}
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
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import flask.cli
flask.cli.show_server_banner = lambda *args, **kwargs: None

log_lines = []
lock = threading.Lock()


def on_message(message, data):
    if message["type"] == "send":
        with lock:
            log_lines.append(message["payload"])


def fatal_error(msg):
    print()
    print("=" * 60)
    print("ERROR: " + msg)
    print("=" * 60)
    if getattr(sys, "frozen", False):
        input("\nPress Enter to close this window...")
    sys.exit(1)


pid_override = os.environ.get("SPIRITVALE_PID")
try:
    session = frida.attach(int(pid_override) if pid_override else PROCESS_NAME)
except frida.ProcessNotFoundError:
    fatal_error(
        f"Could not find a running process named '{PROCESS_NAME}'.\n"
        "Start SpiritVale first, then run this again."
    )
except Exception as e:
    fatal_error(f"Failed to attach to {PROCESS_NAME}: {e}")

try:
    script = session.create_script(open(os.path.join(BUNDLE_DIR, "combined_hook.js"), encoding="utf-8").read())
    script.on("message", on_message)
    script.load()
except Exception as e:
    fatal_error(f"Failed to load the game hook: {e}")


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
        it["displayName"] = it["slot"] if it.get("cls") == "ArtifactData" and it.get("slot") else display_name(it["baseItemId"])
        it["icon"] = icon_filename(it["baseItemId"])
        for st in it.get("substats", []):
            st["typeName"] = STAT_TYPES.get(str(st["type"]), "t" + str(st["type"]))
            st["percent"] = st["type"] in PERCENT_STAT_TYPES
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
            st["percent"] = st["type"] in PERCENT_STAT_TYPES

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
  .topbar { display: flex; justify-content: space-between; align-items: center; max-width: 1400px; margin: 0 auto 20px; font-weight: 700; }
  .topbar a { color: var(--gold); text-decoration: none; font-size: 13px; font-weight: 600; padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; }
  .topbar a:hover { background: var(--tag); }
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
  button.tab { background: #262630; color: var(--muted); }
  button.tab.active { background: var(--accent); color: #fff; }
  input[type=text], select { background: #262630; border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 13px; }
  input[type=text] { flex: 1; min-width: 180px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
  tr:hover td { background: #22222c; }
  .price { color: var(--gold); font-weight: 700; }
  .stat-tag { display: inline-block; background: var(--tag); border-radius: 4px; padding: 2px 7px; margin: 1px 3px 1px 0; font-size: 11px; color: var(--tagtext); cursor: pointer; }
  .stat-tag:hover { background: #33334a; }
  .stat-tag.active { background: var(--accent); color: #fff; }
  #activeFilters:not(:empty) { margin-bottom: 14px; }
  .filter-value { width: 22px; height: 20px; margin-left: 5px; border: none; border-radius: 3px; padding: 1px 3px; font-size: 11px; text-align: center; -moz-appearance: textfield; }
  .filter-value::-webkit-inner-spin-button, .filter-value::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .filter-step { margin-left: 4px; cursor: pointer; padding: 0 2px; font-weight: 700; user-select: none; }
  .filter-remove { margin-left: 5px; cursor: pointer; }
  .suggestions { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; background: #262630; border: 1px solid var(--border); border-radius: 6px; max-height: 200px; overflow-y: auto; z-index: 10; }
  .suggestions.hidden { display: none; }
  .suggestion-item { padding: 8px 12px; font-size: 13px; cursor: pointer; }
  .suggestion-item:hover, .suggestion-item.active { background: #33334a; }
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

<div class="topbar">
  <span>SpiritVale Market</span>
  <a href="https://ko-fi.com/oakkyxd" target="_blank" rel="noopener">&#9749; Support on Ko-fi</a>
</div>

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
      <input type="text" id="itemInput" placeholder="item name" onkeydown="if(event.key==='Enter')checkPrice(this.value)">
      <button onclick="checkPrice(document.getElementById('itemInput').value)">Check Price</button>
    </div>
    <div class="controls" style="position:relative;">
      <input type="text" id="filterInput" placeholder="filter by substat name, press enter"
        oninput="renderFilterSuggestions(this.value)"
        onkeydown="handleFilterKeydown(event)"
        onblur="setTimeout(hideFilterSuggestions, 150)">
      <div id="filterSuggestions" class="suggestions hidden"></div>
    </div>
    <div id="activeFilters"></div>
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
    <div class="controls" id="invTabs">
      <button class="small tab active" data-tab="Equipment" onclick="setInvTab('Equipment')">Equipment</button>
      <button class="small tab" data-tab="Cards" onclick="setInvTab('Cards')">Cards</button>
      <button class="small tab" data-tab="Artifacts" onclick="setInvTab('Artifacts')">Artifacts</button>
      <button class="small tab" data-tab="Gems" onclick="setInvTab('Gems')">Gems</button>
      <button class="small tab" data-tab="Material" onclick="setInvTab('Material')">Material</button>
    </div>
    <table id="invTable"><thead><tr><th>Item</th><th>Substats</th><th>Rec. Price</th><th></th></tr></thead><tbody></tbody></table>
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

let statTypeNames = {};
let activeFilters = new Map(); // type -> {mode: 'ge'|'eq', value: number|null}

const PRIMARY_ATTR_NAMES = new Set(['Str', 'Dex', 'Agi', 'Int', 'Vit', 'Luk']);
function clearOtherPrimaryFilters(type) {
  if (!PRIMARY_ATTR_NAMES.has(statTypeNames[type])) return;
  for (const t of [...activeFilters.keys()]) {
    if (t !== type && PRIMARY_ATTR_NAMES.has(statTypeNames[t])) activeFilters.delete(t);
  }
}

async function loadStatTypes() {
  const res = await fetch('/api/stat-types');
  const pairs = await res.json();
  for (const [id, name] of pairs) statTypeNames[id] = name;
}
loadStatTypes();

function addFilterByName(name) {
  name = name.trim().toLowerCase();
  if (!name) return;
  const entries = Object.entries(statTypeNames);
  const match = entries.find(([id, n]) => n.toLowerCase() === name)
    || entries.find(([id, n]) => n.toLowerCase().includes(name));
  if (!match) return;
  addFilterById(match[0]);
}

function addFilterById(id) {
  id = Number(id);
  clearOtherPrimaryFilters(id);
  activeFilters.set(id, { mode: 'ge', value: null });
  renderActiveFilters();
  renderListings();
  renderInventory();
}

function setFilterValue(type, val) {
  val = val.trim();
  activeFilters.set(type, { mode: 'ge', value: val === '' ? null : Number(val) });
  renderListings();
}

let filterSuggestions = [];
let filterSuggestionIndex = -1;

function hideFilterSuggestions() {
  const box = document.getElementById('filterSuggestions');
  box.classList.add('hidden');
  box.innerHTML = '';
  filterSuggestions = [];
  filterSuggestionIndex = -1;
}

function renderFilterSuggestions(value) {
  const box = document.getElementById('filterSuggestions');
  const q = value.trim().toLowerCase();
  if (!q) { hideFilterSuggestions(); return; }
  filterSuggestions = Object.entries(statTypeNames)
    .filter(([id, name]) => name.toLowerCase().includes(q))
    .sort((a, b) => a[1].localeCompare(b[1]))
    .slice(0, 8);
  filterSuggestionIndex = -1;
  if (!filterSuggestions.length) { hideFilterSuggestions(); return; }
  box.innerHTML = filterSuggestions.map(([id, name]) =>
    `<div class="suggestion-item" onmousedown="selectFilterSuggestion(${id})">${name}</div>`
  ).join('');
  box.classList.remove('hidden');
}

function moveFilterSuggestion(delta) {
  if (!filterSuggestions.length) return;
  filterSuggestionIndex = (filterSuggestionIndex + delta + filterSuggestions.length) % filterSuggestions.length;
  const box = document.getElementById('filterSuggestions');
  [...box.children].forEach((el, i) => el.classList.toggle('active', i === filterSuggestionIndex));
}

function selectFilterSuggestion(id) {
  addFilterById(id);
  const input = document.getElementById('filterInput');
  input.value = '';
  hideFilterSuggestions();
}

function handleFilterKeydown(event) {
  if (event.key === 'ArrowDown') { event.preventDefault(); moveFilterSuggestion(1); }
  else if (event.key === 'ArrowUp') { event.preventDefault(); moveFilterSuggestion(-1); }
  else if (event.key === 'Enter') {
    if (filterSuggestionIndex >= 0 && filterSuggestions[filterSuggestionIndex]) {
      selectFilterSuggestion(filterSuggestions[filterSuggestionIndex][0]);
    } else {
      addFilterByName(event.target.value);
      event.target.value = '';
      hideFilterSuggestions();
    }
  } else if (event.key === 'Escape') {
    hideFilterSuggestions();
  }
}

function toggleFilter(type) {
  type = Number(type);
  if (activeFilters.has(type)) {
    activeFilters.delete(type);
  } else {
    clearOtherPrimaryFilters(type);
    activeFilters.set(type, { mode: 'ge', value: null });
  }
  renderActiveFilters();
  renderListings();
  renderInventory();
}

function toggleFilterWithValue(type, value) {
  type = Number(type);
  value = value === undefined || value === null ? null : Number(value);
  const current = activeFilters.get(type);
  if (current && current.mode === 'eq' && current.value === value) {
    activeFilters.delete(type);
  } else {
    clearOtherPrimaryFilters(type);
    activeFilters.set(type, { mode: 'eq', value });
  }
  renderActiveFilters();
  renderListings();
  renderInventory();
}

function stepFilterValue(type, delta) {
  const current = activeFilters.get(type);
  const floor = PRIMARY_ATTR_NAMES.has(statTypeNames[type]) ? 2 : 0;
  const next = current && current.value !== null ? Math.max(floor, current.value + delta) : floor;
  setFilterValue(type, String(next));
  renderActiveFilters();
}

function renderActiveFilters() {
  const box = document.getElementById('activeFilters');
  box.innerHTML = [...activeFilters].map(([t, f]) =>
    `<span class="stat-tag active">${statTypeNames[t] || ('t' + t)}` +
    `<span class="filter-step" onclick="stepFilterValue(${t}, -1)">&lsaquo;</span>` +
    `<input type="number" class="filter-value" placeholder="≥" value="${f.value ?? ''}" onclick="event.stopPropagation()" oninput="setFilterValue(${t}, this.value)">` +
    `<span class="filter-step" onclick="stepFilterValue(${t}, 1)">&rsaquo;</span>` +
    `<span class="filter-remove" onclick="toggleFilter(${t})">&times;</span></span>`
  ).join('');
}

let lastInventory = [];
let invPage = 0;
let invTab = 'Equipment';
const INV_PAGE_SIZE = 10;

const CLS_TO_TAB = {
  EquipData: 'Equipment',
  ArtifactData: 'Artifacts',
  CardData: 'Cards',
  GemData: 'Gems',
  JunkData: 'Material',
  ConsumableData: 'Material',
  CosmeticData: 'Material',
};

function setInvTab(tab) {
  invTab = tab;
  invPage = 0;
  document.querySelectorAll('#invTabs .tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  renderInventory();
}

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

function itemTab(it) {
  if (it.displayName && it.displayName.includes('Card')) return 'Cards';
  return CLS_TO_TAB[it.cls] || 'Material';
}

// Recommend a price by trying every substat-combination that includes the
// item's primary attribute (Str/Dex/Agi/Int/Vit/Luk) plus at least one other
// substat, e.g. primary 1 with substats 2,3: {1,2} {1,3} {1,2,3} - never
// {2,3}, since a combo without the primary attribute isn't representative.
// Each combo's floor (lowest matching listing price) is taken, then
// whichever combo has the highest floor wins - that's the most specific
// combo the market still has data for, since rarer/more specific combos
// price higher. Falls back to primary-attribute-only matching, then to the
// lowest price overall, when the item has no primary attribute or no combo
// matches.
const PRIMARY_ATTRS = new Set(['Str', 'Dex', 'Agi', 'Int', 'Vit', 'Luk']);

const invListingsCache = {}; // displayName -> listings[] | null | 'pending'
const invPriceCache = {};    // "name|substatTypes" -> {price, mode} | null | 'pending'
let invFetchToken = 0;

function primaryAttrType(it) {
  const s = (it.substats || []).find(s => PRIMARY_ATTRS.has(s.typeName));
  return s ? s.type : null;
}

function substatTypes(it) {
  return [...new Set((it.substats || []).map(s => s.type))];
}

function combosWithPrimary(types, primaryType) {
  const rest = types.filter(t => t !== primaryType);
  const combos = [];
  for (let mask = 0; mask < (1 << rest.length); mask++) {
    const combo = [primaryType, ...rest.filter((_, i) => mask & (1 << i))];
    if (combo.length >= 2) combos.push(combo);
  }
  return combos;
}

// A listing only counts as a comp for a given substat if its roll is no
// better than the item in hand's roll - a listing with a higher roll on
// that substat commands a premium the item in hand can't claim.
function substatValueOk(listingSub, itemSub) {
  if (!itemSub || itemSub.value === undefined || listingSub.value === undefined) return true;
  return listingSub.value <= itemSub.value;
}

function priceKey(it) {
  const types = substatTypes(it).sort((a, b) => a - b).join(',');
  return it.displayName + '|' + (types || 'none');
}

function priceCellHTML(key) {
  const cached = invPriceCache[key];
  if (cached === undefined) return '<span class="stat-label">&mdash;</span>';
  if (cached === 'pending') return '<span class="stat-label">loading&hellip;</span>';
  if (cached === null) return '<span class="stat-label">no listings</span>';
  const prefix = cached.mode === 'all' ? '≈' : '';
  const titles = {
    combo: 'lowest price among listings sharing the substat combination that reached the highest price',
    attr: 'lowest price among listings with the same primary attribute',
    all: 'no matching substat combination found: lowest price across all listings',
  };
  return `<span class="price" title="${titles[cached.mode]}">${prefix}${cached.price.toLocaleString()}g</span>`;
}

function recomputeItemPrice(it) {
  const key = priceKey(it);
  const listings = invListingsCache[it.displayName];
  if (listings === undefined) return;
  if (listings === 'pending') { invPriceCache[key] = 'pending'; }
  else if (listings === null || !listings.length) { invPriceCache[key] = null; }
  else {
    const substatByType = new Map((it.substats || []).map(s => [s.type, s]));
    let bestFloor = null;
    const primaryType = primaryAttrType(it);
    if (primaryType !== null) {
      for (const combo of combosWithPrimary(substatTypes(it), primaryType)) {
        const matched = listings.filter(l => combo.every(t =>
          (l.substats || []).some(s => s.type === t && substatValueOk(s, substatByType.get(t)))));
        if (!matched.length) continue;
        const floor = Math.min(...matched.map(l => l.price));
        if (bestFloor === null || floor > bestFloor) bestFloor = floor;
      }
    }
    if (bestFloor !== null) {
      invPriceCache[key] = { price: bestFloor, mode: 'combo' };
    } else {
      const matched = primaryType !== null ? listings.filter(l =>
        (l.substats || []).some(s => s.type === primaryType && substatValueOk(s, substatByType.get(primaryType)))) : [];
      const pool = matched.length ? matched : listings;
      invPriceCache[key] = { price: Math.min(...pool.map(l => l.price)), mode: matched.length ? 'attr' : 'all' };
    }
  }
  document.querySelectorAll(`[data-price-key="${CSS.escape(key)}"]`).forEach(td => td.innerHTML = priceCellHTML(key));
}

async function fetchInvPrices(pageItems) {
  const token = ++invFetchToken;
  const names = [...new Set(pageItems.map(it => it.displayName))].filter(n => !(n in invListingsCache));
  for (const name of names) {
    if (token !== invFetchToken) return;
    invListingsCache[name] = 'pending';
    pageItems.filter(it => it.displayName === name).forEach(recomputeItemPrice);
    let listings = null;
    try {
      const res = await fetch('/api/price?item=' + encodeURIComponent(name));
      const data = await res.json();
      if (!data.error) listings = data.listings || [];
    } catch (e) {}
    if (token !== invFetchToken) return;
    invListingsCache[name] = listings;
    pageItems.filter(it => it.displayName === name).forEach(recomputeItemPrice);
  }
}

function renderInventory() {
  const tbody = document.querySelector('#invTable tbody');
  tbody.innerHTML = '';

  const filtered = lastInventory
    .filter(it => itemTab(it) === invTab)
    .sort((a, b) => a.displayName.localeCompare(b.displayName));

  document.getElementById('invCount').textContent = filtered.length;

  const pageCount = Math.max(1, Math.ceil(filtered.length / INV_PAGE_SIZE));
  invPage = Math.max(0, Math.min(invPage, pageCount - 1));
  const start = invPage * INV_PAGE_SIZE;
  const pageItems = filtered.slice(start, start + INV_PAGE_SIZE);

  for (const it of pageItems) {
    const tr = document.createElement('tr');
    const substr = (it.substats || []).map(s => {
      const val = ((s.displayValue !== undefined && s.displayValue !== null) ? ('+' + s.displayValue) : (s.value + '/100')) + (s.percent ? '%' : '');
      const hl = activeFilters.has(s.type) ? ' active' : '';
      return `<span class="stat-tag${hl}" onclick="toggleFilterWithValue(${s.type}, ${s.displayValue ?? s.value})">${s.typeName} ${val}</span>`;
    }).join('');
    const refinePrefix = it.refine ? `+${it.refine} ` : '';
    const pKey = priceKey(it);
    tr.innerHTML = `<td><div class="item-cell">${iconImg(it)}<span>${refinePrefix}${it.displayName}</span></div></td>
      <td>${substr}</td>
      <td data-price-key="${pKey.replace(/"/g, '&quot;')}">${priceCellHTML(pKey)}</td>
      <td><button class="small" onclick="checkPrice('${it.displayName.replace(/'/g, "\\\\'")}')">Check Price</button></td>`;
    tbody.appendChild(tr);
  }

  const shownTo = filtered.length === 0 ? 0 : start + pageItems.length;
  document.getElementById('invPageInfo').textContent =
    filtered.length === 0 ? '' : `Showing ${start + 1}-${shownTo} of ${filtered.length}`;
  document.getElementById('invPrev').disabled = invPage === 0;
  document.getElementById('invNext').disabled = invPage >= pageCount - 1;

  fetchInvPrices(pageItems);
}

async function checkPrice(item) {
  document.getElementById('itemInput').value = item;
  activeFilters.clear();
  renderActiveFilters();
  renderInventory();
  const box = document.getElementById('priceBox');
  box.innerHTML = '<div class="empty">searching...</div>';
  document.getElementById('priceStats').innerHTML = '';
  const res = await fetch('/api/price?item=' + encodeURIComponent(item));
  const data = await res.json();
  if (data.error) { box.innerHTML = '<div class="empty">Error: ' + JSON.stringify(data.error) + '</div>'; return; }
  lastListings = data.listings || [];
  renderListings();
}

function renderListings() {
  const box = document.getElementById('priceBox');
  const statsBox = document.getElementById('priceStats');

  const listings = activeFilters.size
    ? lastListings.filter(l => [...activeFilters].every(([t, f]) => (l.substats || []).some(s => {
        if (s.type !== t || f.value === null) return s.type === t;
        const val = s.displayValue ?? s.value;
        return f.mode === 'eq' ? val === f.value : val >= f.value;
      })))
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
      const val = ((s.displayValue !== undefined && s.displayValue !== null) ? ('+' + s.displayValue) : (s.value + '/100')) + (s.percent ? '%' : '');
      const hl = activeFilters.has(s.type) ? ' active' : '';
      return `<span class="stat-tag${hl}" onclick="toggleFilterWithValue(${s.type}, ${s.displayValue ?? s.value})">${s.typeName} ${val}</span>`;
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
    PORT = 5151
    URL = f"http://127.0.0.1:{PORT}"
    print()
    print("=" * 60)
    print(f"  SpiritVale Market Data  v{VERSION}")
    print("=" * 60)
    print(f"  Attached to: {PROCESS_NAME}")
    print(f"  Web UI:      {URL}")
    print("=" * 60)
    print()
    threading.Timer(1.0, lambda: webbrowser.open(URL)).start()
    app.run(port=PORT, debug=False)
