#!/usr/bin/env python3
"""
Farm dashboard collector.

Globs every terminal's  MQL5\\Files\\farm_report\\report_<login>.json  (written
by the FarmReporter EA), merges them into one data.json, REDACTS fields the
published page must not show, then git-commits + pushes to the GitHub Pages repo.

Read-only w.r.t. MT5. Never touches trading. Stdlib only.

Usage:
    python collector.py              # one shot: build + push
    python collector.py --loop 30    # rebuild + push every 30s
    python collector.py --no-push    # build data.json only, skip git
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- where EA report files live (add paths for extra machines here) ----
GLOBS = [
    # main attended terminal (7A4204 = ATFXGM Terminal2)
    r"C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\7A420438090D9D1897FB4FB211B5EAE9\MQL5\Files\farm_report\report_*.json",
    # portable farm
    r"C:\MT5_Portable_Farm\mt5_*\MQL5\Files\farm_report\report_*.json",
]

# ---- privacy: what the PUBLIC page may show ----
SHOW_PORT   = True    # port/terminal number
SHOW_LOGIN  = True    # account login number
SHOW_BROKER = False   # server + broker company  (hidden by default)

STALE_SEC   = 300     # report older than this is flagged stale (still shown)

DATA_JSON   = os.path.join(HERE, "data.json")


def redact(acc):
    """Strip fields the published page must not reveal."""
    if not SHOW_LOGIN:
        acc.pop("login", None)
    if not SHOW_PORT:
        acc.pop("port", None)
    if not SHOW_BROKER:
        acc.pop("server", None)
        acc.pop("broker", None)
    return acc


def collect():
    now = int(datetime.now(timezone.utc).timestamp())
    files = []
    for pat in GLOBS:
        files.extend(glob.glob(pat))

    accounts = []
    seen = set()
    for fp in files:
        try:
            with open(fp, "r", encoding="ansi", errors="replace") as f:
                acc = json.load(f)
        except Exception as e:
            print(f"  skip {fp}: {e}")
            continue
        login = acc.get("login")
        if login in seen:           # same account reported by 2 paths -> keep newest
            continue
        seen.add(login)
        acc["stale"] = (now - int(acc.get("ts", 0))) > STALE_SEC
        acc["age_sec"] = now - int(acc.get("ts", 0))
        accounts.append(redact(dict(acc)))

    accounts.sort(key=lambda a: a.get("port", 0) or a.get("login", 0))

    # combined totals (sums over live accounts)
    def s(key):
        return round(sum(float(a.get(key, 0) or 0) for a in accounts), 2)

    totals = {
        "accounts": len(accounts),
        "balance": s("balance"),
        "equity": s("equity"),
        "net_profit": s("net_profit"),
        "floating": s("floating"),
        "trades": int(sum(int(a.get("trades", 0) or 0) for a in accounts)),
        "wins": int(sum(int(a.get("wins", 0) or 0) for a in accounts)),
        "losses": int(sum(int(a.get("losses", 0) or 0) for a in accounts)),
        "max_equity_dd": round(max([float(a.get("max_equity_dd", 0) or 0)
                                    for a in accounts] + [0.0]), 2),
    }
    tw, tl = totals["wins"], totals["losses"]
    totals["win_rate"] = round(tw / (tw + tl) * 100, 1) if (tw + tl) else 0.0

    out = {
        "generated_ts": now,
        "generated_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "show": {"port": SHOW_PORT, "login": SHOW_LOGIN, "broker": SHOW_BROKER},
        "totals": totals,
        "accounts": accounts,
    }
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  data.json: {len(accounts)} account(s), "
          f"equity={totals['equity']} net={totals['net_profit']}")
    return len(accounts)


def git_push():
    def run(*args):
        return subprocess.run(["git", "-C", HERE, *args],
                              capture_output=True, text=True)
    run("add", "data.json")
    st = run("status", "--porcelain", "data.json")
    if not st.stdout.strip():
        print("  no change, skip push")
        return
    msg = "data: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run("commit", "-m", msg)
    p = run("push", "origin", "HEAD")
    if p.returncode != 0:
        print("  push FAIL:", p.stderr.strip()[:300])
    else:
        print("  pushed:", msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="rebuild+push every N sec")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    def once():
        collect()
        if not a.no_push:
            git_push()

    if a.loop > 0:
        print(f"collector loop every {a.loop}s  (Ctrl+C to stop)")
        while True:
            try:
                once()
            except Exception as e:
                print("  error:", e)
            time.sleep(a.loop)
    else:
        once()


if __name__ == "__main__":
    main()
