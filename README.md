# Farm Dashboard (multi-user)

A multi-port, multi-user MT5 dashboard.

- Each MT5 terminal runs the read-only `FarmReporter` EA. The EA requires a valid
  **owner email** (input `UserEmail`) — if the email is empty or malformed, the EA
  stops immediately and does nothing.
- A Python **collector** gathers every terminal's report and POSTs it to a Google
  **Apps Script** backend, which stores it in a Google Sheet.
- A static page on **GitHub Pages** shows an **anonymized overview** to everyone,
  and — after **Google Sign-In** — shows each person only their own ports
  (one person can own many ports; they are grouped by the email in the EA).

**Read-only.** Nothing here places, modifies, or closes an order.

## Why a backend (privacy)

GitHub Pages is static and cannot hide data: any file it serves is public. To keep
one user from reading another user's balances, per-account data lives only in the
Apps Script backend. The page gets detailed rows only through `mode=mine`, which
the backend returns **only** after verifying a Google ID token whose email matches
the row. The public `mode=overview` returns aggregate totals with no login, email,
or per-port rows.

```
EA (UserEmail) ── report_<login>.json ──► collector.py ──POST(secret)──► Apps Script ──► Google Sheet
                                                                              │
GitHub Pages (static UI) ──JSONP GET──────────────────────────────────────────┤
   mode=overview  → anonymized totals (public)                                  │
   mode=mine&token → that user's ports only (Google ID token verified) ◄────────┘
```

## Pieces

| File | Runs on | Job |
|---|---|---|
| `FarmReporter.mq5` | each MT5 terminal (one chart) | validates `UserEmail`; writes `report_<login>.json`; tracks real per-tick equity drawdown |
| `apps_script/Code.gs` | Google Apps Script web app | stores reports in a Sheet; serves `overview` (public) and `mine` (token-verified) |
| `collector.py` | a machine that can see the terminals' `Files` folders | globs reports, POSTs them to the backend |
| `index.html` + `lightweight-charts.js` | GitHub Pages | overview + Google Sign-In + per-user ports, history range, cumulative P/L chart |

## Setup

### 1. Google OAuth client (for Sign-In)
1. Google Cloud Console → **APIs & Services → Credentials → Create credentials →
   OAuth client ID → Web application**.
2. **Authorized JavaScript origins**: `https://ipnteams-glitch.github.io`
   (add `http://localhost:8751` too if you test locally).
3. Copy the **Client ID** (`...apps.googleusercontent.com`).

### 2. Apps Script backend
1. script.google.com → **New project** → paste `apps_script/Code.gs`.
2. Set `CLIENT_ID` (from step 1) and `SHARED_SECRET` (any long random string).
3. Run `setup()` once (authorize the scopes). The log prints the data Sheet URL.
4. **Deploy → New deployment → Web app**: *Execute as* **Me**, *Who has access*
   **Anyone**. Copy the **/exec** URL.

### 3. Fill config
- `collector.py`: set `WEBAPP_URL` = the /exec URL, `SHARED_SECRET` = same as Code.gs.
- `index.html` `CFG`: set `WEBAPP_URL` = the /exec URL, `CLIENT_ID` = the OAuth client ID.
- Commit + push `index.html` so GitHub Pages serves the configured page.

### 4. Deploy the EA
`FarmReporter.mq5` is in `MQL5\Experts\SGH\`. Compile in MetaEditor (Terminal2,
data folder `7A4204`), attach to one chart per terminal, and set:

- `UserEmail` — the owner's email (**required**; bad email = EA won't run).
- `PortTag` — a port number you assign per terminal.
- `StartDate` — history lookback start (default `2026.01.01`).

### 5. Run the collector
```
python collector.py            # one shot
python collector.py --loop 30  # every 30s
python collector.py --dry      # show payload, send nothing
```

## EA email validation

No regex in MQL5, so the EA checks manually: non-empty, length 6–254, no spaces,
no `;` or `,`, exactly one `@`, a valid local part and domain, and an alphabetic
TLD of 2+ chars. Example rejected: `d;affisa wiyrtrt@gmail.com a;fjkash`
(spaces + `;`). On failure the EA prints/alerts and returns `INIT_FAILED`.

## Drawdown note

`max_equity_dd` is the real equity drawdown measured **tick by tick, going forward
only** — it starts when the EA first runs and is persisted in
`dd_state_<login>.txt` so it survives restarts. It cannot be back-filled (history
has no tick equity). `closed_max_dd` is derived from the closed-trade curve and
does go back to `StartDate`.

## Add terminals on other machines

Append the machine's report glob to `GLOBS` in `collector.py`, or run a second
collector on that machine against the same `WEBAPP_URL`.
