"""
URR Stats Server — aggregates opt-in citation verification events from all extension installs.

Endpoints:
  POST /event          { doi, status, source }  → record one verification
  GET  /stats          → global counters + top hallucinated DOIs
  GET  /stats/live     → Server-Sent Events stream (real-time counter pushes)
  GET  /               → public dashboard HTML
"""

import sqlite3, json, time, os
from datetime import datetime, timezone
from contextlib import contextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB = os.environ.get("DB_PATH", "urr_stats.db")
app = FastAPI(title="URR Stats")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                doi       TEXT NOT NULL,
                status    TEXT NOT NULL,   -- verified | hallucinated | error
                source    TEXT,            -- page domain (optional)
                ts        TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_status ON events(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_doi    ON events(doi)")
        db.commit()

init_db()

# ── Models ────────────────────────────────────────────────────────────────────

class Event(BaseModel):
    doi: str
    status: str          # verified | hallucinated | error
    source: str = ""     # page hostname — opt-in, may be empty

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_stats():
    db = get_db()
    total      = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    verified   = db.execute("SELECT COUNT(*) FROM events WHERE status='verified'").fetchone()[0]
    hallucin   = db.execute("SELECT COUNT(*) FROM events WHERE status='hallucinated'").fetchone()[0]
    today      = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_tot  = db.execute("SELECT COUNT(*) FROM events WHERE ts LIKE ?", (f"{today}%",)).fetchone()[0]
    top_fake   = db.execute("""
        SELECT doi, COUNT(*) n FROM events
        WHERE status='hallucinated'
        GROUP BY doi ORDER BY n DESC LIMIT 10
    """).fetchall()
    db.close()
    rate = round(hallucin / total * 100, 1) if total else 0
    return {
        "total": total, "verified": verified, "hallucinated": hallucin,
        "hallucination_rate_pct": rate, "today": today_tot,
        "top_hallucinated": [{"doi": r["doi"], "count": r["n"]} for r in top_fake],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/event", status_code=202)
async def record_event(ev: Event):
    # Minimal validation
    if not ev.doi.startswith("10.") or ev.status not in ("verified","hallucinated","error"):
        return JSONResponse({"error": "invalid"}, status_code=400)
    ts = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute("INSERT INTO events(doi,status,source,ts) VALUES(?,?,?,?)",
               (ev.doi[:200], ev.status, ev.source[:100], ts))
    db.commit()
    db.close()
    return {"ok": True}

@app.get("/stats")
def stats():
    return get_stats()

@app.get("/stats/live")
async def stats_live():
    """Server-Sent Events — pushes updated stats every 5 seconds."""
    def generate():
        while True:
            data = json.dumps(get_stats())
            yield f"data: {data}\n\n"
            time.sleep(5)
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML

# ── Dashboard HTML ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>URR Citation Verifier — Live Stats</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0d0d1a;color:#e8e8f0;min-height:100vh}
.header{background:#1a1a2e;padding:20px 32px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a4e}
.logo{font-size:28px}
h1{font-size:18px;font-weight:600}
.sub{font-size:12px;color:#888;margin-top:2px}
.live-dot{width:8px;height:8px;border-radius:50%;background:#28a745;animation:pulse 2s infinite;margin-left:auto}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;padding:32px;max-width:1100px;margin:0 auto}
.card{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:20px 24px}
.card .n{font-size:40px;font-weight:700;line-height:1;margin-bottom:4px}
.card .l{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.06em}
.blue{color:#4fa3e3}.green{color:#4caf7d}.red{color:#e35f5f}.yellow{color:#f0b429}
.section{max-width:1100px;margin:0 auto;padding:0 32px 32px}
.section h2{font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.fake-list{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;overflow:hidden}
.fake-row{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid #22223a;font-size:13px}
.fake-row:last-child{border-bottom:none}
.fake-doi{font-family:monospace;color:#e35f5f;flex:1}
.fake-n{color:#888;font-size:12px;white-space:nowrap}
.bar-wrap{width:120px;background:#22223a;border-radius:3px;height:6px;overflow:hidden}
.bar{height:6px;background:#e35f5f;border-radius:3px;transition:width .5s}
.footer{text-align:center;padding:20px;color:#444;font-size:11px}
.updated{font-size:11px;color:#444;margin-top:4px}
</style>
</head>
<body>
<div class="header">
  <span class="logo">🔬</span>
  <div>
    <h1>URR Citation Verifier — Live Stats</h1>
    <p class="sub">Opt-in telemetry from all extension installs · CrossRef + DataCite</p>
  </div>
  <div class="live-dot" title="Live"></div>
</div>

<div class="grid">
  <div class="card"><div class="n blue" id="n-total">–</div><div class="l">Total DOIs checked</div></div>
  <div class="card"><div class="n green" id="n-verified">–</div><div class="l">Verified real</div></div>
  <div class="card"><div class="n red" id="n-fake">–</div><div class="l">Hallucinated</div></div>
  <div class="card"><div class="n yellow" id="n-rate">–</div><div class="l">Hallucination rate</div></div>
  <div class="card"><div class="n blue" id="n-today">–</div><div class="l">Checked today</div></div>
</div>

<div class="section">
  <h2>Top hallucinated DOIs</h2>
  <div class="fake-list" id="fake-list"><div class="fake-row" style="color:#444">Loading…</div></div>
  <p class="updated" id="updated"></p>
</div>

<div class="footer">
  URR is open-source · <a href="https://github.com/sudhanshu/urr" style="color:#4fa3e3">github.com/sudhanshu/urr</a> ·
  All data opt-in, DOIs only, no personal info collected
</div>

<script>
const BASE = window.location.origin;

function update(s) {
  document.getElementById('n-total').textContent    = s.total.toLocaleString();
  document.getElementById('n-verified').textContent = s.verified.toLocaleString();
  document.getElementById('n-fake').textContent     = s.hallucinated.toLocaleString();
  document.getElementById('n-rate').textContent     = s.hallucination_rate_pct + '%';
  document.getElementById('n-today').textContent    = s.today.toLocaleString();
  document.getElementById('updated').textContent    = 'Updated ' + new Date(s.updated_at).toLocaleTimeString();

  const max = s.top_hallucinated[0]?.count || 1;
  const list = document.getElementById('fake-list');
  if (!s.top_hallucinated.length) {
    list.innerHTML = '<div class="fake-row" style="color:#444">No hallucinated DOIs yet</div>';
    return;
  }
  list.innerHTML = s.top_hallucinated.map(r => `
    <div class="fake-row">
      <span class="fake-doi">${r.doi}</span>
      <div class="bar-wrap"><div class="bar" style="width:${Math.round(r.count/max*100)}%"></div></div>
      <span class="fake-n">${r.count}×</span>
    </div>`).join('');
}

// SSE for live updates
const es = new EventSource(BASE + '/stats/live');
es.onmessage = e => update(JSON.parse(e.data));
es.onerror   = () => {
  // fallback to polling every 10s
  setInterval(() => fetch(BASE+'/stats').then(r=>r.json()).then(update), 10000);
  fetch(BASE+'/stats').then(r=>r.json()).then(update);
};
</script>
</body>
</html>
"""
