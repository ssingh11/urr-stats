import sqlite3, json, os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
DB = os.environ.get("DB_PATH", "urr_stats.db")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT NOT NULL, status TEXT NOT NULL,
            source TEXT, ts TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS i1 ON events(status)")
        c.commit()

init()

def stats():
    c = db()
    total    = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    verified = c.execute("SELECT COUNT(*) FROM events WHERE status='verified'").fetchone()[0]
    fake     = c.execute("SELECT COUNT(*) FROM events WHERE status='hallucinated'").fetchone()[0]
    today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_n  = c.execute("SELECT COUNT(*) FROM events WHERE ts LIKE ?", (f"{today}%",)).fetchone()[0]
    top      = c.execute("""SELECT doi, COUNT(*) n FROM events WHERE status='hallucinated'
                            GROUP BY doi ORDER BY n DESC LIMIT 10""").fetchall()
    c.close()
    return {
        "total": total, "verified": verified, "hallucinated": fake,
        "hallucination_rate_pct": round(fake/total*100,1) if total else 0,
        "today": today_n,
        "top_hallucinated": [{"doi": r["doi"], "count": r["n"]} for r in top],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": "0.1.0"})

@app.post("/event")
def event():
    d = request.get_json(silent=True) or {}
    doi, status, source = d.get("doi","").strip(), d.get("status",""), d.get("source","")
    if not doi.startswith("10.") or status not in ("verified","hallucinated","error"):
        return jsonify({"error":"invalid"}), 400
    ts = datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("INSERT INTO events(doi,status,source,ts) VALUES(?,?,?,?)",
                  (doi[:200], status, source[:100], ts))
        c.commit()
    return jsonify({"ok": True}), 202

@app.get("/stats")
def get_stats():
    return jsonify(stats())

@app.get("/stats/live")
def live():
    import time
    def stream():
        while True:
            yield f"data: {json.dumps(stats())}\n\n"
            time.sleep(5)
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/")
def dashboard():
    return open(os.path.join(os.path.dirname(__file__), "dashboard.html")).read()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
