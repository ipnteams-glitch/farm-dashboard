/**
 * Farm Dashboard backend (Google Apps Script Web App).
 *
 * Data isolation: the public page shows ONLY anonymized aggregate totals.
 * Per-account detail is returned ONLY to the signed-in owner, verified by a
 * Google ID token whose email must match the row's email. data never leaves
 * this backend in raw form, so one user cannot read another user's ports.
 *
 * SETUP (once):
 *   1. Set CLIENT_ID below to your Google OAuth 2.0 Web client ID.
 *   2. Set SHARED_SECRET below (any long random string); put the SAME value in
 *      collector.py SHARED_SECRET.
 *   3. Run setup() once from the editor (creates the data spreadsheet, grants
 *      UrlFetch/Spreadsheet scopes). Check the log for the sheet URL.
 *   4. Deploy > New deployment > Web app:
 *        Execute as: Me        Who has access: Anyone
 *      Copy the /exec URL into collector.py WEBAPP_URL and index.html WEBAPP_URL.
 *
 * Read-only w.r.t. trading. Pure data store/serve.
 */

var CLIENT_ID     = "528165468683-1m8e24ei2oi7llh9jii0hhp245g0h9me.apps.googleusercontent.com";
var SHARED_SECRET = "PUT_A_LONG_RANDOM_SECRET_HERE";  // set to your real secret in the Apps Script editor, not in the public repo
var STALE_SEC     = 300;

var HEADERS = [
  "email","login","port","label","balance","equity","net_profit","win_rate",
  "profit_factor","closed_max_dd","max_equity_dd","max_equity_dd_pct","cur_dd",
  "trades","wins","losses","floating","start_date","daily_json","ts"
];

// ---------------- storage ----------------

function setup() {
  var ss = SpreadsheetApp.create("FarmDashboardData");
  PropertiesService.getScriptProperties().setProperty("SHEET_ID", ss.getId());
  var sh = ss.getSheets()[0];
  sh.setName("farm");
  sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  Logger.log("Sheet created: " + ss.getUrl());
}

function sheet_() {
  var id = PropertiesService.getScriptProperties().getProperty("SHEET_ID");
  var ss = id ? SpreadsheetApp.openById(id) : null;
  if (!ss) throw new Error("run setup() first");
  var sh = ss.getSheetByName("farm");
  if (!sh) { sh = ss.insertSheet("farm"); sh.getRange(1,1,1,HEADERS.length).setValues([HEADERS]); }
  return sh;
}

function colIndex_() {
  var m = {}; for (var i = 0; i < HEADERS.length; i++) m[HEADERS[i]] = i; return m;
}

// ---------------- write (collector -> here) ----------------

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    if (body.secret !== SHARED_SECRET) return json_({ error: "bad secret" });
    var accounts = body.accounts || [];
    var sh = sheet_();
    var data = sh.getDataRange().getValues();
    var ci = colIndex_();
    // map login -> row number (1-based data rows start at 2)
    var rowOf = {};
    for (var r = 1; r < data.length; r++) rowOf[String(data[r][ci.login])] = r + 1;

    accounts.forEach(function (a) {
      var row = HEADERS.map(function (h) {
        if (h === "daily_json") return JSON.stringify(a.daily || []);
        return (a[h] === undefined || a[h] === null) ? "" : a[h];
      });
      var key = String(a.login);
      if (rowOf[key]) sh.getRange(rowOf[key], 1, 1, HEADERS.length).setValues([row]);
      else           sh.appendRow(row);
    });
    return json_({ ok: true, n: accounts.length });
  } catch (err) {
    return json_({ error: String(err) });
  }
}

// ---------------- read (page -> here) ----------------

function doGet(e) {
  var mode = (e.parameter.mode || "overview");
  var cb   = e.parameter.callback || "";
  var out;
  if (mode === "mine") {
    out = mine_(e.parameter.token);               // per-user: NEVER cached
  } else {
    // overview is shared + public -> cache 60s so 50 open dashboards all hit
    // cache and the sheet is read at most once per minute, not once per request.
    var cache = CacheService.getScriptCache();
    var hit = cache.get("overview");
    if (hit) { out = JSON.parse(hit); }
    else { out = overview_(); cache.put("overview", JSON.stringify(out), 60); }
  }
  return cb ? jsonp_(cb, out) : json_(out);
}

function rows_() {
  var sh = sheet_();
  var data = sh.getDataRange().getValues();
  var ci = colIndex_();
  var now = Math.floor(Date.now() / 1000);
  var out = [];
  for (var r = 1; r < data.length; r++) {
    var row = data[r];
    if (!row[ci.login]) continue;
    var o = {};
    HEADERS.forEach(function (h) { o[h] = row[ci[h]]; });
    o.age_sec = now - Number(o.ts || 0);
    o.stale = o.age_sec > STALE_SEC;
    out.push(o);
  }
  return out;
}

function overview_() {
  var rs = rows_();
  var sum = function (k) { return rs.reduce(function (s, a) { return s + (Number(a[k]) || 0); }, 0); };
  var wins = sum("wins"), losses = sum("losses");
  return {
    generated_ts: Math.floor(Date.now() / 1000),
    accounts: rs.length,
    ports: rs.length,
    users: uniqueCount_(rs, "email"),
    equity: round2_(sum("equity")),
    net_profit: round2_(sum("net_profit")),
    floating: round2_(sum("floating")),
    total_trades: sum("trades"),
    win_rate: (wins + losses) ? round2_(wins / (wins + losses) * 100) : 0,
    max_equity_dd: round2_(rs.reduce(function (m, a) { return Math.max(m, Number(a.max_equity_dd) || 0); }, 0))
  };
}

function mine_(token) {
  var email = verify_(token);
  if (!email) return { error: "unauthorized" };
  var rs = rows_().filter(function (a) {
    return String(a.email).toLowerCase() === email.toLowerCase();
  });
  rs.forEach(function (a) {
    try { a.daily = JSON.parse(a.daily_json || "[]"); } catch (x) { a.daily = []; }
    delete a.daily_json;
  });
  var sum = function (k) { return rs.reduce(function (s, a) { return s + (Number(a[k]) || 0); }, 0); };
  var wins = sum("wins"), losses = sum("losses");
  return {
    email: email,
    accounts: rs,
    totals: {
      accounts: rs.length,
      balance: round2_(sum("balance")),
      equity: round2_(sum("equity")),
      net_profit: round2_(sum("net_profit")),
      floating: round2_(sum("floating")),
      trades: sum("trades"),
      win_rate: (wins + losses) ? round2_(wins / (wins + losses) * 100) : 0,
      max_equity_dd: round2_(rs.reduce(function (m, a) { return Math.max(m, Number(a.max_equity_dd) || 0); }, 0))
    }
  };
}

// ---------------- auth ----------------

function verify_(token) {
  if (!token) return null;
  try {
    var r = UrlFetchApp.fetch(
      "https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(token),
      { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) return null;
    var t = JSON.parse(r.getContentText());
    if (String(t.aud) !== String(CLIENT_ID)) return null;      // token meant for us
    if (t.email_verified !== true && t.email_verified !== "true") return null;
    return t.email || null;
  } catch (e) { return null; }
}

// ---------------- helpers ----------------

function uniqueCount_(rs, k) {
  var s = {}; rs.forEach(function (a) { if (a[k]) s[String(a[k]).toLowerCase()] = 1; });
  return Object.keys(s).length;
}
function round2_(n) { return Math.round(n * 100) / 100; }
function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o))
    .setMimeType(ContentService.MimeType.JSON);
}
function jsonp_(cb, o) {
  return ContentService.createTextOutput(cb + "(" + JSON.stringify(o) + ")")
    .setMimeType(ContentService.MimeType.JAVASCRIPT);
}
