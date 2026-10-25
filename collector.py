#!/usr/bin/env python3
"""
Farm dashboard collector.

Globs every terminal's  MQL5\\Files\\farm_report\\report_<login>.json  (written
by the FarmReporter EA) and POSTs them to the Apps Script backend, which stores
them in a Google Sheet and serves per-user (auth-gated) + anonymized overview.

Privacy lives in the backend now: the page shows only aggregate totals until a
user signs in with Google; per-account rows are returned ONLY to the matching
email. So the collector sends full data (incl. email) to the backend only.

Read-only w.r.t. MT5. Stdlib only.

Usage:
    python collector.py              # one shot
    python collector.py --loop 30    # every 30s
    python collector.py --dry        # build payload, print, do NOT send
"""

import argparse
import glob
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

# folder of this script, or of the .exe when built with PyInstaller (--onefile)
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

# ---- CONFIG ----
# Secrets live in config.local.json (gitignored) so they never reach the public
# repo. Copy config.local.example.json -> config.local.json and fill it in.
WEBAPP_URL    = "PASTE_APPS_SCRIPT_EXEC_URL_HERE"   # .../exec  (overridden by config.local.json)
SHARED_SECRET = "PUT_A_LONG_RANDOM_SECRET_HERE"     # must match Code.gs (overridden by config.local.json)

_cfg_path = os.path.join(HERE, "config.local.json")
if os.path.exists(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as _f:
        _cfg = json.load(_f)
    WEBAPP_URL    = _cfg.get("WEBAPP_URL", WEBAPP_URL)
    SHARED_SECRET = _cfg.get("SHARED_SECRET", SHARED_SECRET)

# ---- where EA report files live: AUTO-DETECT every MT5 terminal on this PC ----
# No path editing needed. Covers normally-installed terminals (under %APPDATA%)
# and common portable-install locations. Add extra folders in config.local.json:
#   {"EXTRA_GLOBS": ["D:\\MyMT5\\*\\MQL5\\Files\\farm_report\\report_*.json"]}
def _auto_globs():
    tail = os.path.join("MQL5", "Files", "farm_report", "report_*.json")
    pats = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        pats.append(os.path.join(appdata, "MetaQuotes", "Terminal", "*", tail))
    # common portable-farm roots (each terminal folder holds its own MQL5\)
    for root in (r"C:\MT5_Portable_Farm", r"C:\MT5", r"C:\MT5_Farm",
                 r"C:\Program Files", r"C:\Program Files (x86)"):
        pats.append(os.path.join(root, "*", tail))
    return pats

EXTRA_GLOBS = _cfg.get("EXTRA_GLOBS", []) if os.path.exists(_cfg_path) else []
GLOBS = _auto_globs() + list(EXTRA_GLOBS)

STALE_SEC = 300   # skip reports older than this (EA/terminal offline)


def gather():
    now = int(datetime.now(timezone.utc).timestamp())
    files = []
    for pat in GLOBS:
        files.extend(glob.glob(pat))
    accounts, seen = [], set()
    for fp in files:
        try:
            with open(fp, "r", encoding="ansi", errors="replace") as f:
                a = json.load(f)
        except Exception as e:
            print(f"  skip {fp}: {e}")
            continue
        if not a.get("email"):          # EA refuses to run without valid email; guard anyway
            continue
        login = a.get("login")
        if login in seen:
            continue
        seen.add(login)
        if now - int(a.get("ts", 0)) > STALE_SEC:
            print(f"  stale, skip login {login}")
            continue
        accounts.append(a)
    return accounts


def send(accounts):
    payload = json.dumps({"secret": SHARED_SECRET, "accounts": accounts}).encode()
    req = urllib.request.Request(WEBAPP_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode(errors="replace")
    print("  backend:", body[:200])


def once(dry):
    accs = gather()
    print(f"  {len(accs)} live account(s): " +
          ", ".join(str(a.get("login")) for a in accs))
    if dry:
        print(json.dumps(accs, ensure_ascii=False)[:800])
        return
    if "PASTE_APPS_SCRIPT" in WEBAPP_URL:
        print("  WEBAPP_URL not set; skip send (edit collector.py)")
        return
    if accs:
        send(accs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.loop > 0:
        print(f"collector loop every {a.loop}s (Ctrl+C to stop)")
        while True:
            try:
                once(a.dry)
            except Exception as e:
                print("  error:", e)
            time.sleep(a.loop)
    else:
        once(a.dry)


if __name__ == "__main__":
    main()
