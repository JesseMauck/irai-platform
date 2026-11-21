"""Live-source smoke test for the disclosures engines (run in a Railway fork sandbox)."""
import os, time, json
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/disc.db"); os.environ["IRAI_AUTO_CREATE_TABLES"] = "1"; os.environ["IRAI_MARKET_MODE"] = "live"
os.environ.setdefault("IRAI_JWT_SECRET", "fork-test-secret-fork-test-secret-123456")
from app.db import SessionLocal, init_db
init_db()
from app.disclosures import congress, thirteenf
with SessionLocal() as db:
    t = time.time(); print("13f", thirteenf.refresh(db, ["berkshire", "pershing", "duquesne", "ark", "scion"]), round(time.time() - t, 1))
    t = time.time(); print("congress", congress.refresh(db, max_docs=40, days=60), round(time.time() - t, 1))
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
j = c.get("/api/congress/trades").json(); print("trades", j["total"], [ (r["member"], r["party"], r["ticker"], r["type"], r["amount"], r["traded"], r.get("price_change_since")) for r in j["trades"][:5]])
s = c.get("/api/congress/summary").json(); print("summary", s["trades"], s["members"], s["most_traded"][:3], s["leaderboard"][:2])
f = c.get("/api/smart-money/funds").json(); print("funds", [(x["fund"], x["period"], round(x["aum_13f"]/1e9, 1), x["top_holding"]) for x in f["funds"]])
b = c.get("/api/smart-money/funds/berkshire").json(); print("brk", b["counts"], [(h["ticker"], h["status"], round(h["weight"] or 0, 3)) for h in b["holdings"][:8]])
cs = c.get("/api/smart-money/consensus").json(); print("consensus", [(r["ticker"], r["holders"]) for r in cs["most_held"][:5]])
print(c.get("/api/smart-money/symbol/AAPL").json()["smart_money"])
