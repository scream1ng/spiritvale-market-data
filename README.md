# SpiritVale Market

A live price checker and inventory viewer for [SpiritVale](https://store.steampowered.com/)'s player-run vending market — built as a local web dashboard that reads directly from your own running game client.

No typing search terms in-game over and over, no guessing what an item's worth. Search once, see every live listing on the market sorted by price, with substat rolls broken out and filterable.

## What it does

- **Price Check** — search any item name, get every current vending listing (price, seller, quantity, refine level, substats) pulled live from the market.
- **Substat filter** — click any substat tag (or use the dropdown) to instantly filter listings down to that roll.
- **Inventory** — scan your own character's inventory and jump straight into a price check for any item you're carrying.
- **Item icons** — pulled from the game's own assets so listings are easy to scan visually.

## How it works

SpiritVale is a Unity/IL2CPP game with a shared player economy. This tool attaches to your own running game process (via [Frida](https://frida.re/)) and reads the same vending-market data your game client already receives from the server — it doesn't modify anything, place trades, or automate gameplay. It's a read-only viewer, nothing more.

It only works while you have the game open, and only reflects your own client's own network-visible market state.

## Setup

**Requirements**
- Your own legit copy of SpiritVale (Steam)
- Python 3.10+
- `pip install frida frida-tools flask UnityPy`

**One-time data setup** (per game version — needs redoing after a game update):
1. Dump the game's IL2Cpp metadata with [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) against your own install's `GameAssembly.dll` + `global-metadata.dat`, output into `extract/dumpout/`.
2. Run `python extract/extract.py` (set `SPIRITVALE_DATA_PATH` env var if your Steam library isn't on `D:`) — generates `data/items.json`, `data/stat_types.json`, and item icons into `data/icons/`.

**Run it**
1. Launch SpiritVale, open the vending search panel at least once.
2. `cd extract/frida && python server.py`
3. Open [http://localhost:5151](http://localhost:5151)

## Known limitations

- Substat display values are reconstructed from the game's own `Formula.GetSubstatRange`/`GetSubstatScaledValue` — confirmed exact for attribute and damage% substats; leech-family substats have been observed off by ±1.
- Artifact-type items (rune/jewel/scroll/relic) don't have a clean static display name in the game data — falls back to a lowercase search-key string instead of a pretty name.

## Support

This is a free hobby project, built and maintained in spare time — no ads, no paywall, no telemetry. If it's useful to you and you'd like to support continued upkeep (redoing the data dump every time the game patches, adding features), donations are welcome but never expected:

- PromptPay QR: *(add your QR code image here)*
- Ko-fi: *(add your ko-fi.com link here)*
