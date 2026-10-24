# Farm Dashboard

A multi-port MT5 dashboard. Each terminal runs the read-only `FarmReporter` EA,
which writes a JSON report of its account. A Python collector merges every
report into `data.json` and pushes it to this GitHub Pages site, where the
static page renders all accounts together.

**Read-only.** Neither the EA nor the collector places, modifies, or closes any
order. The EA only reads account info and trade history; the collector only
reads report files and runs git.

## Pieces

| File | Where it runs | Job |
|---|---|---|
| `FarmReporter.mq5` | each MT5 terminal (one chart) | writes `MQL5\Files\farm_report\report_<login>.json` every few seconds; tracks real equity drawdown on every tick |
| `collector.py` | the machine that can see every terminal's `Files` folder | globs all report files, redacts hidden fields, writes `data.json`, git-commits + pushes |
| `index.html` + `lightweight-charts.js` | GitHub Pages (static) | fetches `data.json`, shows totals, per-account table, history range, cumulative P/L chart |

## EA inputs (`FarmReporter`)

- `StartDate` — history lookback start (default `2026.01.01`). Closed-trade stats are computed from this date to now.
- `PublishIntervalS` — how often the report file is rewritten (default 5s).
- `PortTag` — a port/terminal number you assign per terminal (shown on the page).
- `Label` — optional display label.

**Drawdown note:** the real per-tick equity drawdown (`max_equity_dd`) can only be
measured going forward — it starts accumulating the moment the EA first runs on a
terminal and is persisted in `dd_state_<login>.txt` so it survives restarts. It
cannot be back-filled from history (history has no tick-by-tick equity). The
history-based `closed_max_dd` is derived from the closed-trade curve and does go
back to `StartDate`.

## Privacy

GitHub Pages is public. The collector redacts fields before publishing. Edit the
flags at the top of `collector.py`:

```python
SHOW_PORT   = True    # port/terminal number
SHOW_LOGIN  = True    # account login number
SHOW_BROKER = False   # server + broker company
```

`balance` / `equity` / profit are always shown — they are the point of the
dashboard. Only publish to a repo whose exposure you accept.

## Run the collector

```
python collector.py            # build data.json once + push
python collector.py --loop 30  # rebuild + push every 30 seconds
python collector.py --no-push  # build only, no git
```

Add terminals on other machines by appending their report glob to `GLOBS` in
`collector.py` (or run a collector on each machine against the same repo).

## Deploy EA

`FarmReporter.mq5` lives in `MQL5\Experts\SGH\`. Compile it in MetaEditor
(ATFXGM Terminal2 data folder `7A4204`), then attach it to any one chart on each
terminal you want reported. Set `PortTag` per terminal.
