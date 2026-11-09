"""License server: NowPayments invoice → signed 30-day key → device activation.

Flow
----
  1. Client POST /invoice {prev_key?}      → {order_id, invoice_url}
  2. Buyer pays in the browser. Success page: GET /success/<order_id>
  3. NowPayments POST /ipn (HMAC-verified) → server mints a signed Ed25519 key
     (price $14.99, 30 days; a valid prev_key extends from its expiry).
  4. /success/<order_id> shows the key once issued; the client also polls
     GET /order/<order_id>/status and auto-fills it.
  5. Client POST /activate {key, device_id} binds the key to this device.
     Max DEVICE_CAP distinct devices per key — activation needs the server
     exactly once per device.
  6. Everyday launches validate the key OFFLINE (signature + expiry inside the
     key itself). Render being asleep can never lock out an activated device.
     Optional soft revocation: client POST /recheck {kid, device_id} when
     online; /admin/revoke flips the flag.

Database: PostgreSQL when DATABASE_URL is set (Render/Supabase), otherwise a
local SQLite file (server/licensing.db) so the whole flow is dev-testable.

MOCK_NOWPAYMENTS=1 replaces the real invoice with GET /mock-pay/<order_id>,
which simulates a finished payment end-to-end.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from html import escape

import keysign
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


def _load_dotenv(path: str) -> None:
    """Minimal .env loader for local dev (Render uses dashboard env instead).
    Existing environment variables always win. No dependency needed."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── Config ────────────────────────────────────────────────────────
PRICE = float(os.getenv("PRICE_USD", "14.99"))
PERIOD_DAYS = int(os.getenv("PERIOD_DAYS", "30"))
DEVICE_CAP = int(os.getenv("DEVICE_CAP", "2"))
NOW_API = os.getenv("NOWPAYMENTS_API_KEY", "")
NOW_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
MOCK = os.getenv("MOCK_NOWPAYMENTS", "1") == "1"
DATABASE_URL = os.getenv("DATABASE_URL", "")
PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SIGNING: "keysign.Ed25519PrivateKey | None" = None

app = FastAPI(title="Interview Assistant License Server")


def _require_signing() -> "keysign.Ed25519PrivateKey":
    if SIGNING is None:
        raise HTTPException(500, "SIGNING_PRIVATE_KEY not configured on server")
    return SIGNING


# ── Database (PostgreSQL, or SQLite for local development) ────────

def _is_sqlite() -> bool:
    return (not DATABASE_URL) or DATABASE_URL.startswith("sqlite")


def _sql(q: str) -> str:
    # Queries here use ? placeholders; psycopg2 wants %s.
    return q if _is_sqlite() else q.replace("?", "%s")


@contextmanager
def get_db():
    if _is_sqlite():
        path = DATABASE_URL.split("sqlite:///")[-1] if DATABASE_URL else \
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "licensing.db")
        conn = sqlite3.connect(path)
    else:
        url = DATABASE_URL
        if "sslmode" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        import psycopg2
        conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    prev_key TEXT DEFAULT '',
    created  BIGINT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS issued_keys (
    kid      TEXT PRIMARY KEY,
    key_str  TEXT NOT NULL,
    order_id TEXT DEFAULT '',
    note     TEXT DEFAULT '',
    iat      BIGINT DEFAULT 0,
    exp      BIGINT DEFAULT 0,
    revoked  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS activations (
    kid          TEXT NOT NULL,
    device_id    TEXT NOT NULL,
    activated_at BIGINT DEFAULT 0,
    PRIMARY KEY (kid, device_id)
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id   TEXT DEFAULT '',
    status     TEXT DEFAULT '',
    raw        TEXT DEFAULT '',
    ts         BIGINT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_issued_order ON issued_keys(order_id);
"""


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        for stmt in _SCHEMA.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cur.close()


@app.on_event("startup")
def _startup():
    global SIGNING
    try:
        SIGNING = keysign.load_private_key()
        signing_state = "yes"
    except Exception as exc:
        SIGNING = None
        signing_state = f"NO ({exc})"
    print(f"[server] mode={'MOCK' if MOCK else 'LIVE'} db={'sqlite' if _is_sqlite() else 'pg'} "
          f"signing={signing_state} price={PRICE} days={PERIOD_DAYS} cap={DEVICE_CAP}", flush=True)
    init_db()


@app.get("/status")
def status():
    return {"mode": "mock" if MOCK else "live",
            "database": "sqlite" if _is_sqlite() else "connected",
            "signing_key": "configured" if SIGNING else "missing",
            "price": PRICE, "days": PERIOD_DAYS, "device_cap": DEVICE_CAP}


# ── Key minting ───────────────────────────────────────────────────

def _mint(order_id: str, prev_key: str, note: str = "") -> dict:
    """Sign a fresh key. Renewal: a valid prev_key extends from its expiry.
    Idempotent per order_id — repeated IPNs return the already-issued key."""
    priv = _require_signing()
    now = int(time.time())
    base = now
    if prev_key:
        try:
            payload = keysign.parse_and_verify(keysign.public_key_hex(priv), prev_key)
            base = max(now, int(payload["exp"]))
        except Exception:
            base = now  # unverifiable prev key: treat as a fresh purchase
    kid = keysign.new_kid()
    exp = base + PERIOD_DAYS * 86400
    key_str = keysign.sign_key(priv, now, exp, kid)
    with get_db() as conn:
        cur = conn.cursor()
        if order_id:
            cur.execute(_sql("SELECT key_str, exp, kid FROM issued_keys WHERE order_id=?"),
                        (order_id,))
            row = cur.fetchone()
            if row:
                cur.close()
                return {"key": row[0], "exp": int(row[1]), "kid": row[2]}
        cur.execute(_sql(
            "INSERT INTO issued_keys(kid,key_str,order_id,note,iat,exp,revoked) "
            "VALUES(?,?,?,?,?,?,0)"), (kid, key_str, order_id, note, now, exp))
        cur.close()
    print(f"[mint] kid={kid} order={order_id or '-'} exp={exp}", flush=True)
    return {"key": key_str, "exp": exp, "kid": kid}


# ── Purchase flow ─────────────────────────────────────────────────

def _nowpayments_invoice(order_id: str) -> str:
    payload = {
        "price_amount": PRICE, "price_currency": "USD",
        "order_id": order_id,
        "order_description": f"Interview Assistant — {PERIOD_DAYS} days",
        "success_url": f"{PUBLIC_BASE}/success/{order_id}",
        "cancel_url": f"{PUBLIC_BASE}/success/{order_id}",
    }
    ipn = os.getenv("IPN_CALLBACK_URL", "").strip()
    if ipn:
        payload["ipn_callback_url"] = ipn
    req = urllib.request.Request(
        "https://api.nowpayments.io/v1/invoice",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": NOW_API, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise HTTPException(502, f"NOWPayments rejected invoice (HTTP {exc.code}): {detail}")
    try:
        return body["invoice_url"]
    except KeyError:
        raise HTTPException(502, f"NOWPayments gave no invoice_url: {json.dumps(body)[:500]}")


@app.post("/invoice")
def invoice(body: dict):
    prev_key = (body.get("prev_key") or "").strip()
    if prev_key:
        try:
            keysign.parse_and_verify(keysign.public_key_hex(_require_signing()), prev_key)
        except ValueError as exc:
            raise HTTPException(400, f"previous key is not valid: {exc}")
    order_id = "ORD-" + secrets.token_urlsafe(12)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("INSERT INTO orders(order_id, prev_key, created) VALUES(?,?,?)"),
                    (order_id, prev_key, int(time.time())))
        cur.close()
    url = (f"{PUBLIC_BASE}/mock-pay/{order_id}" if MOCK
           else _nowpayments_invoice(order_id))
    return {"order_id": order_id, "invoice_url": url,
            "price": PRICE, "days": PERIOD_DAYS, "device_cap": DEVICE_CAP}


@app.get("/order/{order_id}/status")
def order_status(order_id: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("SELECT key_str, exp, kid FROM issued_keys WHERE order_id=?"),
                    (order_id,))
        row = cur.fetchone()
        if row:
            cur.close()
            return {"status": "issued", "key": row[0], "exp": int(row[1]), "kid": row[2]}
        cur.execute(_sql("SELECT created FROM orders WHERE order_id=?"), (order_id,))
        known = cur.fetchone() is not None
        cur.close()
    return {"status": "pending" if known else "unknown"}


def _handle_payment(order_id: str, payment_id: str, status: str, raw: str = "") -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql(
            "INSERT INTO payments(payment_id,order_id,status,raw,ts) VALUES(?,?,?,?,?) "
            "ON CONFLICT (payment_id) DO NOTHING"),
            (payment_id or f"{order_id}-{int(time.time())}", order_id, status,
             raw[:4000], int(time.time())))
        cur.close()
    if status in ("finished", "confirmed") and order_id:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(_sql("SELECT prev_key FROM orders WHERE order_id=?"), (order_id,))
            row = cur.fetchone()
            cur.close()
        _mint(order_id, row[0] if row else "")


@app.post("/ipn")
async def ipn(req: Request, x_nowpayments_sig: str = Header(default="", alias="x-nowpayments-sig")):
    raw = await req.body()
    if NOW_IPN_SECRET:
        try:
            data = json.loads(raw)
            sig = hmac.new(NOW_IPN_SECRET.encode(),
                           json.dumps(data, separators=(",", ":")).encode(),
                           hashlib.sha512).hexdigest()
            if not hmac.compare_digest(sig, x_nowpayments_sig):
                raise HTTPException(401, "bad IPN signature")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "bad IPN signature")
    data = json.loads(raw or b"{}")
    _handle_payment(str(data.get("order_id", "")),
                    str(data.get("payment_id", "")),
                    str(data.get("payment_status", "")),
                    raw.decode(errors="replace"))
    return JSONResponse({"ok": True})


@app.get("/mock-pay/{order_id}")
def mock_pay(order_id: str):
    if not MOCK:
        raise HTTPException(404, "not found")
    _handle_payment(order_id, f"MOCK-{order_id}", "finished", "mock")
    return RedirectResponse(f"/success/{order_id}", status_code=302)


# ── Success page ──────────────────────────────────────────────────

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>Interview Assistant — your license key</title>
<style>
 body {{ background:#0b0f14; color:#c9d5e0; font:15px/1.5 system-ui,sans-serif;
        max-width:640px; margin:48px auto; padding:0 20px; }}
 h1 {{ color:#4fd1ff; font-weight:600; }}
 .key {{ background:#121a24; border:1px solid #2a3a4d; border-radius:8px;
        padding:14px 16px; font:14px/1.4 Consolas,monospace; color:#9ef01a;
        word-break:break-all; user-select:all; }}
 .muted {{ color:#7a8a9a; font-size:13px; }}
 a {{ color:#4fd1ff; }}
</style></head><body>
<h1>Interview Assistant</h1>
{body}
<p class="muted">Order <code>{order}</code> · ${price} / {days} days</p>
</body></html>"""


def _success_page(order_id: str) -> HTMLResponse:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("SELECT key_str, exp FROM issued_keys WHERE order_id=?"), (order_id,))
        row = cur.fetchone()
        cur.close()
    if row:
        key, exp = row[0], int(row[1])
        body = (f"<p>Payment received. Your license key (valid until "
                f"{time.strftime('%Y-%m-%d', time.gmtime(exp))}):</p>"
                f'<div class="key">{escape(key)}</div>'
                "<p>Copy it and paste it into the app's license window. "
                "The key works on up to {cap} devices.</p>").format(cap=DEVICE_CAP)
        refresh = ""
    else:
        body = ("<p>Payment not confirmed yet — this page refreshes every 5 seconds. "
                "Paid but stuck? Give it a couple of minutes; if it never appears, "
                "contact support with your order id.</p>"
                '<p class="muted">You can close this tab and come back later — '
                "the app is also watching this order and will fill the key in for you.</p>")
        refresh = '5'
    return HTMLResponse(_PAGE.format(refresh=refresh, body=body,
                                     order=escape(order_id), price=PRICE, days=PERIOD_DAYS))


@app.get("/success/{order_id}")
def success(order_id: str):
    return _success_page(order_id)


# ── Activation + soft recheck ─────────────────────────────────────

@app.post("/activate")
def activate(body: dict):
    priv = _require_signing()
    key = (body.get("key") or "").strip()
    device_id = (body.get("device_id") or "").strip()[:64]
    if not key or not device_id:
        raise HTTPException(400, "key + device_id required")
    try:
        payload = keysign.parse_and_verify(keysign.public_key_hex(priv), key)
    except ValueError as exc:
        raise HTTPException(403, f"license invalid: {exc}")
    kid, exp = str(payload["kid"]), int(payload["exp"])
    if exp < time.time():
        raise HTTPException(403, "license expired")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("SELECT revoked FROM issued_keys WHERE kid=?"), (kid,))
        row = cur.fetchone()
        if row and int(row[0]):
            cur.close()
            raise HTTPException(403, "license revoked")
        cur.execute(_sql("SELECT device_id FROM activations WHERE kid=? AND device_id=?"),
                    (kid, device_id))
        already = cur.fetchone() is not None
        if not already:
            cur.execute(_sql("SELECT COUNT(*) FROM activations WHERE kid=?"), (kid,))
            count = int(cur.fetchone()[0])
            if count >= DEVICE_CAP:
                cur.close()
                raise HTTPException(
                    403, f"device cap reached — this key is already active on "
                         f"{count} devices (limit {DEVICE_CAP})")
            cur.execute(_sql(
                "INSERT INTO activations(kid, device_id, activated_at) VALUES(?,?,?)"),
                (kid, device_id, int(time.time())))
        cur.execute(_sql("SELECT COUNT(*) FROM activations WHERE kid=?"), (kid,))
        count = int(cur.fetchone()[0])
        cur.close()
    return {"ok": True, "exp": exp, "kid": kid, "devices": count,
            "remaining": max(0, DEVICE_CAP - count)}


@app.post("/recheck")
def recheck(body: dict):
    """Soft revocation check. ok=False means revoked; the key's own signature
    and expiry remain authoritative for everything else."""
    kid = (body.get("kid") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not kid:
        raise HTTPException(400, "kid required")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("SELECT revoked, exp FROM issued_keys WHERE kid=?"), (kid,))
        row = cur.fetchone()
        activated = False
        if device_id:
            cur.execute(_sql("SELECT 1 FROM activations WHERE kid=? AND device_id=?"),
                        (kid, device_id))
            activated = cur.fetchone() is not None
        cur.close()
    revoked = bool(row and int(row[0]))
    return {"ok": not revoked, "revoked": revoked,
            "exp": int(row[1]) if row else 0, "activated": activated}


# ── Admin ─────────────────────────────────────────────────────────

def _admin_check(token: str):
    if not ADMIN_TOKEN or not secrets.compare_digest(str(token or ""), ADMIN_TOKEN):
        raise HTTPException(401, "bad admin token")


@app.post("/admin/mint")
def admin_mint(body: dict):
    """Mint a standalone key by hand — comps, or recovering a buyer whose
    payment landed while the server was asleep."""
    _admin_check(body.get("admin_token", ""))
    days = int(body.get("days", PERIOD_DAYS))
    now = int(time.time())
    priv = _require_signing()
    kid = keysign.new_kid()
    exp = now + days * 86400
    key_str = keysign.sign_key(priv, now, exp, kid)
    note = str(body.get("note", ""))[:200]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql(
            "INSERT INTO issued_keys(kid,key_str,order_id,note,iat,exp,revoked) "
            "VALUES(?,?,?,?,?,?,0)"),
            (kid, key_str, "", note, now, exp))
        cur.close()
    return {"ok": True, "key": key_str, "kid": kid, "exp": exp}


@app.post("/admin/revoke")
def admin_revoke(body: dict):
    _admin_check(body.get("admin_token", ""))
    kid = (body.get("kid") or "").strip()
    if not kid:
        raise HTTPException(400, "kid required")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("UPDATE issued_keys SET revoked=1 WHERE kid=?"), (kid,))
        cur.close()
    return {"ok": True}


@app.post("/admin/lookup")
def admin_lookup(body: dict):
    _admin_check(body.get("admin_token", ""))
    order_id = (body.get("order_id") or "").strip()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(_sql("SELECT key_str, exp, kid, revoked FROM issued_keys WHERE order_id=?"),
                    (order_id,))
        row = cur.fetchone()
        cur.execute(_sql("SELECT COUNT(*) FROM issued_keys"))
        total = int(cur.fetchone()[0])
        cur.close()
    if not row:
        return {"exists": False, "total_keys": total}
    return {"exists": True, "total_keys": total, "key": row[0], "exp": int(row[1]),
            "kid": row[2], "revoked": bool(int(row[3]))}
