"""
RUNNAUP — Ken's paid surveys + paid studies board. Spelled R-U-N-N-A-U-P.
Modeled on ClaimBoard / Workspace (FastAPI + SQLite, no-password admin by Ken's order).

Two modes: Surveys, and Study Mode (paid research studies / focus groups / interviews).

HARD RULES (built in, not optional):
  1. FREE ONLY — anything pay-to-join, paid plan, deposit, or purchase-required is
     REJECTED by the API (free_confirmed must be true, requires_payment must be false).
  2. HONEST RULE — the bot finds, joins (free accounts only), and preps items with
     Ken's REAL demographic info, then queues them "ready". Ken himself must answer
     the opinion / experience questions. A bot fake-answering surveys is fraud —
     it gets accounts banned and pay voided. There is NO fake-answer engine here.
  3. Earnings count ONLY real money: rows with status='paid' AND paid_amount > 0.
     Typical / advertised pay on a card is NOT earnings.

No DOB, phone, or SSN is stored in this app's DB or shown in any UI.
Ken's full filing profile lives only in the goal's hidden_files profile note.
"""
import os, datetime, sqlite3
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).parent
DB_PATH = os.environ.get("RUNNAUP_DB", str(BASE / "runnaup.db"))

app = FastAPI(title="RUNNAUP", version="1.0.0")

TYPES = ("survey", "study")
STATUSES = ("found", "joined", "ready", "started", "completed", "paid", "passed")
PAY_TYPES = ("cash", "PayPal", "gift card", "points")

# Missing screener info — Ken must provide these himself. NEVER invent answers.
PROFILE_CHECKLIST = [
    "Household size",
    "Employment status",
    "Income range",
    "Race / ethnicity (surveys ask — only with Ken's own answer)",
    "Marital status",
    "Education level",
    "Devices owned (phone / computer / tablet / game consoles)",
    "Car ownership / make & model",
]

# slug, title, provider, type, pay_amount (typical, USD), pay_type, est_minutes,
# url, eligibility, note
# Pay figures are honest typicals from each platform's own pages / reputable
# roundups checked 2026-11-07. They are NOT guarantees and NOT earnings.
SEED = [
    # ---------------- STUDY MODE (usually highest $/hr) ----------------
    ("prolific", "Academic & AI research studies online", "Prolific", "study", 4.00, "PayPal", 20,
     "https://www.prolific.com",
     "18+, US resident, PayPal account; join may start on a waitlist",
     "STUDY MODE — usually highest $/hr with Prolific + Connect. Enforced pay floor: at least $8/hr, $12/hr recommended. Cash out to PayPal from $6. Studies appear when your demographics match — no fake promises, availability varies."),
    ("cloudresearch-connect", "Academic surveys & behavioral studies", "CloudResearch Connect", "study", 3.00, "PayPal", 12,
     "https://www.cloudresearch.com/products/connect-for-participants/",
     "18+, US/UK/CA/AU/IE/NZ; ID verification at signup; approval can take time",
     "STUDY MODE — usually highest $/hr with Prolific. Platform advertises ~$15/hr, ~12 min studies; reviewers report roughly $8-$18/hr. Cash out from $5 via PayPal, bank, or Amazon gift card. Pay shown up front per project."),
    ("user-interviews", "Interviews, focus groups, diary studies & tests", "User Interviews", "study", 45.00, "gift card", 60,
     "https://www.userinterviews.com/hello",
     "Free profile; answer screeners fast — selection is competitive",
     "STUDY MODE — usually highest $/hr tier. Platform says average study pays over $45: 1-on-1 interviews $20-$300+, focus groups $40-$200+, diary studies $55-$400+. Paid a few days after via Tremendous (gift card / prepaid). Screeners are unpaid."),
    ("respondent", "Professional interviews & focus groups", "Respondent", "study", 75.00, "gift card", 60,
     "https://www.respondent.io",
     "Free profile; job title / industry drive invitations; identity verified once",
     "STUDY MODE — highest per-study pay for professional topics. Respondent states ~$75 average, most sessions $50-$250. Paid via Tremendous 7-10 business days after attendance is confirmed, minus a 5% fee (min $1). Fewer invites, bigger payouts."),
    ("dscout", "Phone diary missions & live research sessions", "dscout", "study", 50.00, "PayPal", 45,
     "https://dscout.com/participate-in-research-studies",
     "Smartphone app (iOS 16+ / Android 9+), camera + mic; verified PayPal for payout",
     "STUDY MODE. Missions = short videos / photos / diary entries using a product or app over days. dscout says most missions pay $25-$150. Applying is unpaid (like an audition). PayPal within ~10 business days after a mission closes."),
    ("playtestcloud", "Paid mobile game playtests + follow-up survey", "PlaytestCloud", "study", 7.00, "PayPal", 15,
     "https://www.playtestcloud.com",
     "Free to join — platform says it will never ask you to pay to take part; PayPal / Tremendous",
     "STUDY MODE (game testing). Play a mobile game ~15 min while talking out loud, then answer a survey. Platform benchmark: $5-$9 per 15-min playtest+survey. No minimum payout; paid via Tremendous within ~3 days. Onboarding test is unpaid."),

    # ---------------- SURVEYS ----------------
    ("branded-surveys", "Consumer opinion surveys", "Branded Surveys", "survey", 1.50, "PayPal", 15,
     "https://www.branded-surveys.com",
     "US/CA/UK resident; free account",
     "Typical surveys $0.50-$3, 5-20 min. Cash out from $5 (500 points) via PayPal, bank transfer, or gift cards. Branded itself tells members to expect roughly $5-$100/month — pocket money, not a wage."),
    ("survey-junkie", "Consumer opinion surveys (+ occasional focus groups)", "Survey Junkie", "survey", 2.00, "PayPal", 15,
     "https://www.surveyjunkie.com",
     "18+, US/CA/AU/UK; free account",
     "Most surveys $0.50-$5; 100 points = $1, cash out from $5 via PayPal, bank transfer, or gift card. You earn a few points even when you screen out. Focus groups ($25-$150) appear rarely."),
    ("swagbucks", "Surveys + other small reward tasks", "Swagbucks", "survey", 1.00, "points", 15,
     "https://www.swagbucks.com",
     "Free account; 13+ (Ken is an adult member)",
     "Points (SB): 100 SB = $1. Surveys are one of several earning tasks. Redeem from ~$3 in gift cards; PayPal from ~$5. Low $/hr — filler only, best used after the study platforms."),
    ("pinecone-research", "Product-opinion surveys + home product tests", "Pinecone Research", "survey", 3.00, "PayPal", 18,
     "https://www.pineconeresearch.com",
     "US address; registration opens only when the panel is recruiting — may not always be open",
     "Nielsen panel. Commonly reported ~$3-$5 per survey, ~15-20 min, plus occasional keep-the-product home tests. Low survey volume (often 1-2/month), but you are rarely screened out after being matched."),
    ("rakuten-insight", "Consumer opinion surveys", "Rakuten Insight", "survey", 1.00, "PayPal", 10,
     "https://insight.rakuten.com",
     "Free account; surveys matched to your profile",
     "Rakuten's research panel. Short surveys, points redeemable from $5 via PayPal or Amazon gift cards. Survey inventory is limited, so pay per survey varies widely — treat as filler."),
    ("ipsos-isay", "Consumer opinion surveys", "Ipsos iSay", "survey", 1.00, "gift card", 10,
     "https://www.ipsosisay.com",
     "Free account; US panel",
     "Panel from Ipsos, a major research firm. Points per survey, redeemed for gift cards / PayPal where offered. Low $/hr like most survey panels — volume and consistency are the value."),
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hourly(row):
    mins = row["est_minutes"] if isinstance(row, dict) else row["est_minutes"]
    pay = row["pay_amount"] if isinstance(row, dict) else row["pay_amount"]
    if pay and mins:
        return round(pay / (mins / 60.0), 2)
    return None

def row_out(r):
    d = dict(r)
    d["hourly"] = hourly(d)
    d["free_confirmed"] = bool(d.get("free_confirmed"))
    return d

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, provider TEXT DEFAULT '',
      type TEXT NOT NULL DEFAULT 'survey',
      pay_amount REAL DEFAULT 0, pay_type TEXT DEFAULT 'cash',
      est_minutes INTEGER DEFAULT 0, url TEXT DEFAULT '',
      eligibility TEXT DEFAULT '', deadline TEXT DEFAULT '',
      status TEXT DEFAULT 'found', paid_amount REAL DEFAULT 0,
      notes TEXT DEFAULT '', blocker TEXT DEFAULT '',
      free_confirmed INTEGER DEFAULT 1, date_found TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS profile_checklist(
      id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, provided INTEGER DEFAULT 0)""")
    today = datetime.date.today().isoformat()
    now = datetime.datetime.utcnow().isoformat()
    for (slug, title, provider, typ, pay, pay_type, mins, url, elig, note) in SEED:
        c.execute("""INSERT OR IGNORE INTO items
          (slug,title,provider,type,pay_amount,pay_type,est_minutes,url,eligibility,deadline,
           status,paid_amount,notes,blocker,free_confirmed,date_found,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?, 'Ongoing — no deadline', 'found', 0, ?, '', 1, ?, ?)""",
                  (slug, title, provider, typ, pay, pay_type, mins, url, elig, note, today, now))
    for item in PROFILE_CHECKLIST:
        c.execute("INSERT OR IGNORE INTO profile_checklist(item, provided) VALUES(?, 0)", (item,))
    c.commit(); c.close()
init_db()

@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "runnaup", "version": "1.0.0"}

@app.get("/api/items")
async def api_list(type: str | None = None, status: str | None = None):
    c = db()
    q = "SELECT * FROM items WHERE 1=1"; args = []
    if type and type in TYPES:
        q += " AND type=?"; args.append(type)
    if status and status in STATUSES:
        q += " AND status=?"; args.append(status)
    q += " ORDER BY type, pay_amount DESC"
    rows = c.execute(q, args).fetchall(); c.close()
    return [row_out(r) for r in rows]

@app.get("/api/summary")
async def api_summary():
    c = db(); rows = c.execute("SELECT * FROM items").fetchall(); c.close()
    earned = sum((r["paid_amount"] or 0) for r in rows if r["status"] == "paid" and (r["paid_amount"] or 0) > 0)
    pending_rows = [r for r in rows if r["status"] in ("joined", "ready", "started", "completed")]
    pending = sum((r["pay_amount"] or 0) for r in pending_rows)
    ready = [row_out(r) for r in rows if r["status"] == "ready"]
    ready.sort(key=lambda d: (d["hourly"] or 0), reverse=True)
    return {
        "total": len(rows),
        "by_type": {t: sum(1 for r in rows if r["type"] == t) for t in TYPES},
        "by_status": {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES},
        "earned_total": round(earned, 2),
        "pending_potential": round(pending, 2),
        "best_ready": ready[:5],
        "free_only": True,
        "updated": datetime.datetime.utcnow().isoformat(),
    }

@app.get("/api/profile-prep")
async def api_profile_prep():
    c = db(); rows = c.execute("SELECT * FROM profile_checklist ORDER BY id").fetchall(); c.close()
    return {
        # Only non-sensitive prep facts are exposed. DOB / phone / SSN are NEVER here.
        "profile_on_file": {
            "name": "Kendrick Cooley",
            "location": "Bismarck, ND 58501",
            "contact": "Email, personal phone, and DOB are on file in Ken's private filing profile (hidden) — not shown on this board.",
        },
        "missing_checklist": [dict(r) for r in rows],
        "rule": "Milli preps with Ken's REAL info only. Missing answers stay blank until Ken provides them — never invent a screener answer.",
    }

class StatusIn(BaseModel):
    status: str

@app.patch("/api/items/{slug}")
async def api_set_status(slug: str, body: StatusIn):
    # No password by Ken's standing order for these boards — admin is open.
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status.")
    c = db()
    cur = c.execute("UPDATE items SET status=?, updated_at=? WHERE slug=?",
                    (body.status, datetime.datetime.utcnow().isoformat(), slug))
    c.commit(); n = cur.rowcount; c.close()
    if not n: raise HTTPException(404, "Not found.")
    return {"ok": True, "slug": slug, "status": body.status}

class ItemIn(BaseModel):
    slug: str; title: str; provider: str = ""; type: str = "survey"
    pay_amount: float = 0; pay_type: str = "cash"; est_minutes: int = 0
    url: str = ""; eligibility: str = ""; deadline: str = ""
    status: str = "found"; notes: str = ""; blocker: str = ""
    free_confirmed: bool = True; requires_payment: bool = False

@app.post("/api/admin/items")
async def api_upsert(body: ItemIn):
    # HARD FILTER — free only. This is the enforcement point, not just a UI note.
    if body.requires_payment or not body.free_confirmed:
        raise HTTPException(400, "FREE ONLY: RUNNAUP rejects anything pay-to-join, paid plan, deposit, or purchase-required.")
    if body.type not in TYPES:
        raise HTTPException(400, "Invalid type (survey|study).")
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status.")
    if body.pay_type not in PAY_TYPES:
        raise HTTPException(400, "Invalid pay_type.")
    now = datetime.datetime.utcnow().isoformat()
    c = db()
    c.execute("""INSERT INTO items(slug,title,provider,type,pay_amount,pay_type,est_minutes,url,
        eligibility,deadline,status,notes,blocker,free_confirmed,date_found,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
      ON CONFLICT(slug) DO UPDATE SET title=excluded.title, provider=excluded.provider,
      type=excluded.type, pay_amount=excluded.pay_amount, pay_type=excluded.pay_type,
      est_minutes=excluded.est_minutes, url=excluded.url, eligibility=excluded.eligibility,
      deadline=excluded.deadline, notes=excluded.notes, blocker=excluded.blocker,
      free_confirmed=1, updated_at=excluded.updated_at""",
      (body.slug, body.title, body.provider, body.type, body.pay_amount, body.pay_type,
       body.est_minutes, body.url, body.eligibility, body.deadline, body.status,
       body.notes, body.blocker, datetime.date.today().isoformat(), now))
    c.commit(); c.close()
    return {"ok": True, "slug": body.slug}

class PaidIn(BaseModel):
    amount: float

@app.post("/api/admin/items/{slug}/paid")
async def api_paid(slug: str, body: PaidIn):
    if body.amount <= 0:
        raise HTTPException(400, "Paid amount must be > 0 — earnings count only real money received.")
    c = db()
    cur = c.execute("UPDATE items SET status='paid', paid_amount=?, updated_at=? WHERE slug=?",
                    (body.amount, datetime.datetime.utcnow().isoformat(), slug))
    c.commit(); n = cur.rowcount; c.close()
    if not n: raise HTTPException(404, "Not found.")
    return {"ok": True}

@app.delete("/api/admin/items/{slug}")
async def api_delete(slug: str):
    c = db()
    cur = c.execute("DELETE FROM items WHERE slug=?", (slug,))
    c.commit(); n = cur.rowcount; c.close()
    if not n: raise HTTPException(404, "Not found.")
    return {"ok": True}

@app.get("/api/operator/summary")
async def api_operator_summary():
    s = await api_summary()
    prep = await api_profile_prep()
    return {
        "service": "runnaup", "version": "1.0.0", **s,
        "missing_profile_count": sum(1 for r in prep["missing_checklist"] if not r["provided"]),
        "honest_rule": "Bot finds / joins free panels / preps with Ken's real demographics and queues Ready. Ken answers opinion & experience questions himself. No fake-answer engine — that is fraud, bans accounts, and voids pay.",
        "free_rule": "FREE ONLY: pay-to-join, paid plans, deposits, and purchase-required items are rejected by the API.",
    }

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(str(BASE / "static" / "index.html"))

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    return FileResponse(str(BASE / "static" / "admin.html"))

@app.get("/operator", response_class=HTMLResponse)
async def operator():
    return FileResponse(str(BASE / "static" / "operator.html"))

@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(str(BASE / "static" / "manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js")
async def sw():
    return FileResponse(str(BASE / "static" / "sw.js"), media_type="application/javascript")
