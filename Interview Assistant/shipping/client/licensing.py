"""Client licensing: signed offline keys, online once-per-device activation.

Model
-----
  - Keys are Ed25519-signed by the license server ($14.99 / 30 days). The
    client embeds the PUBLIC key only — nothing secret ships in the binary.
  - Signature + expiry are validated OFFLINE on every launch.
  - First use on a device calls POST /activate, which binds the key to this
    device (server enforces the 2-device cap). After that, launches work even
    when the license server is asleep.
  - Soft revocation: when the server is reachable, the watchdog asks
    /recheck; a revoked key shuts down. Network failures never do.

State lives in %APPDATA%\\InterviewAssistant\\license.json.
No new deps: stdlib + cryptography (already bundled).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PLAN_PRICE = "14.99"
PLAN_DAYS = 30
DEVICE_CAP = 2
RECHECK_MINUTES = 30        # watchdog interval for the soft recheck

# Ed25519 public verification key (raw 32 bytes, hex). Rotating it requires a
# new client build; the private key exists only on the license server.
PUBLIC_KEY_HEX = "c336325513196d7971034fc8fb329458c5ae0f98e81f47c66bde27b9380a5e72"

KEY_PREFIX = "3L3-"
FORMAT_VERSION = 1

APP_DIR = Path(os.getenv("APPDATA") or Path.home()) / "InterviewAssistant"
LICENSE_FILE = APP_DIR / "license.json"


# ── Server location + HTTP ────────────────────────────────────────

def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def server_url() -> str:
    env = os.getenv("LICENSE_SERVER_URL", "").strip()
    if _looks_like_url(env):
        return env.rstrip("/")
    candidates: list[Path] = []
    try:
        candidates.append(Path(__file__).resolve().parent / "license_server.txt")
    except Exception:
        pass
    try:
        import sys as _sys
        if getattr(_sys, "frozen", False):
            candidates.append(Path(_sys.executable).resolve().parent / "license_server.txt")
    except Exception:
        pass
    for fp in candidates:
        try:
            if fp.exists():
                for line in fp.read_text().splitlines():
                    txt = line.strip()
                    if _looks_like_url(txt):
                        return txt.rstrip("/")
        except Exception:
            continue
    return "http://127.0.0.1:8000"


def _hidden_subprocess_kwargs() -> dict:
    kw: dict = {}
    try:
        if sys.platform.startswith("win"):
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kw["startupinfo"] = startupinfo
    except Exception:
        pass
    return kw


def _wmic_output(args: list[str], timeout: int = 20) -> str:
    """wmic with retries — right after boot wmic can be very slow, and a single
    timed-out attempt would produce a different device ID for the same machine."""
    last_exc: Exception = TimeoutError("wmic not attempted")
    for _ in range(3):
        try:
            return subprocess.check_output(
                ["wmic"] + args, stderr=subprocess.DEVNULL,
                text=True, timeout=timeout, **_hidden_subprocess_kwargs())
        except Exception as exc:
            last_exc = exc
            time.sleep(1)
    raise last_exc


def get_hwid() -> str:
    parts: list[str] = []
    try:
        out = _wmic_output(["csproduct", "get", "uuid"])
        for line in out.splitlines():
            s = line.strip()
            if s and "UUID" not in s:
                parts.append("mb:" + s)
                break
    except Exception:
        pass
    try:
        serials: list[str] = []
        try:
            out = _wmic_output(["diskdrive", "where",
                                "mediatype='Fixed hard disk media'",
                                "get", "serialnumber"])
            serials = sorted({ln.strip() for ln in out.splitlines()
                              if ln.strip() and "Serial" not in ln.strip()})
        except Exception:
            serials = []
        if not serials:
            out = _wmic_output(["diskdrive", "get", "serialnumber"])
            serials = sorted({ln.strip() for ln in out.splitlines()
                              if ln.strip() and "Serial" not in ln.strip()})
        if serials:
            parts.append("disk:" + "|".join(serials))
    except Exception:
        pass
    parts.append("host:" + platform.node())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _post(path: str, payload: dict, timeout: int = 60, attempts: int = 3,
          on_retry=None) -> dict:
    """POST JSON, tolerant of Render free-tier cold starts (~60s wake).
    HTTP errors raise immediately; only network errors/timeouts are retried."""
    import urllib.error

    total = max(1, attempts)
    last_exc: Exception = TimeoutError("no attempt made")
    for attempt in range(1, total + 1):
        try:
            req = urllib.request.Request(
                server_url() + path,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc
            if attempt < total:
                if on_retry is not None:
                    try:
                        on_retry(attempt, total, exc)
                    except Exception:
                        pass
                time.sleep(2)
    raise last_exc


def _http_detail(exc: Exception) -> str:
    try:
        raw = exc.read().decode(errors="replace")[:500]  # type: ignore[attr-defined]
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("detail"):
                return str(data["detail"])
        except Exception:
            pass
        return raw[:300]
    except Exception:
        return str(exc)


def _friendly_net_error(exc: Exception) -> str:
    msg = str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return f"Server rejected the request: {msg}"
    if isinstance(exc, TimeoutError) or "timed out" in msg:
        return ("Server took too long (it sleeps when idle and needs ~60s to wake). "
                "Wait a minute and try again — no charge was made.")
    if isinstance(exc, (ConnectionError, OSError)):
        return f"No connection to license server: {exc}"
    return msg


# ── Local key validation (offline) ────────────────────────────────

def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _now_monotonic(cached: dict) -> int:
    """Wall clock, but never earlier than the last seen time — blunts a
    simple clock-rollback of the expiry check."""
    return max(int(time.time()), int(cached.get("last_seen", 0) or 0))


def validate_local(key_str: str, cached: dict | None = None) -> tuple[dict | None, str]:
    """Verify signature + version + expiry offline. Returns (payload, 'ok') or
    (None, reason)."""
    s = (key_str or "").strip()
    if not s.startswith(KEY_PREFIX):
        return None, "not a 3lit3 license key"
    body = s[len(KEY_PREFIX):]
    if body.count(".") != 1:
        return None, "malformed key"
    payload_b64, sig_b64 = body.split(".")
    try:
        payload_raw = _b64d(payload_b64)
        sig = _b64d(sig_b64)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub.verify(sig, payload_raw)
        data = json.loads(payload_raw.decode())
    except Exception:
        return None, "key signature is invalid"
    if not isinstance(data, dict) or data.get("v") != FORMAT_VERSION:
        return None, "unsupported key version"
    if "kid" not in data or "exp" not in data:
        return None, "key payload is incomplete"
    if int(data["exp"]) < _now_monotonic(cached or {}):
        return None, "license expired"
    return data, "ok"


# ── Cache ─────────────────────────────────────────────────────────

def load_cache() -> dict:
    try:
        return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(data: dict) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


# ── Server calls ──────────────────────────────────────────────────

def activate(key: str, device_id: str, on_retry=None) -> tuple[bool, str, int]:
    """Bind the key to this device (once per device; server enforces the cap).
    Returns (ok, message, exp)."""
    import urllib.error
    try:
        resp = _post("/activate", {"key": key, "device_id": device_id},
                     timeout=45, attempts=3, on_retry=on_retry)
    except urllib.error.HTTPError as exc:
        return False, _http_detail(exc) or f"HTTP {exc.code}", 0
    except Exception as exc:
        return False, _friendly_net_error(exc), 0
    if resp.get("ok"):
        return True, "activated", int(resp.get("exp", 0))
    return False, str(resp.get("error", "activation failed")), 0


def recheck(kid: str, device_id: str):
    """Soft revocation check for the watchdog.
    True = ok, False = revoked, None = network problem (keep running)."""
    try:
        resp = _post("/recheck", {"kid": kid, "device_id": device_id},
                     timeout=20, attempts=2)
        return bool(resp.get("ok"))
    except Exception:
        return None


def create_invoice(prev_key: str | None = None, on_retry=None) -> tuple[str, str]:
    """Create an order; returns (order_id, invoice_url).
    Pass the previous key to extend it (renewal) instead of starting over."""
    payload: dict = {}
    if prev_key:
        payload["prev_key"] = prev_key
    resp = _post("/invoice", payload, timeout=60, attempts=3, on_retry=on_retry)
    if "order_id" not in resp:
        raise RuntimeError(
            f"license server at {server_url()} is running the OLD version "
            f"(no order_id in /invoice). Deploy the new shipping/server or "
            f"point LICENSE_SERVER_URL at a local server.")
    return str(resp["order_id"]), str(resp["invoice_url"])


def order_status(order_id: str) -> tuple[str, str | None]:
    """GET /order/<id>/status → (status, key|None). Raises on network error."""
    req = urllib.request.Request(
        server_url() + f"/order/{order_id}/status", method="GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    return str(data.get("status", "unknown")), data.get("key")


# ── The paywall ───────────────────────────────────────────────────

def ensure_licensed() -> tuple[str, str, str] | None:
    """Blocking paywall. Returns (key, kid, device_id) iff the key is valid
    and activated on this device; None if the user quits."""
    import tkinter as tk
    from tkinter import ttk

    hwid = get_hwid()
    cached = load_cache()

    def _store(key: str, kid: str, exp: int) -> None:
        now = int(time.time())
        save_cache({"key": key, "kid": kid, "exp": exp, "device_id": hwid,
                    "first_seen": cached.get("first_seen", now), "last_seen": now})

    # Fast path: valid key already activated on THIS device — no network at all.
    if cached.get("key") and cached.get("device_id") == hwid:
        payload, _ = validate_local(cached["key"], cached)
        if payload:
            cached["last_seen"] = int(time.time())
            save_cache(cached)
            return cached["key"], str(payload["kid"]), hwid

    startup_msg = "Enter key and Activate, or Buy to get one."

    # Cached key valid but not bound to this device (reinstall / new PC):
    # activate now — needs the server exactly once.
    if cached.get("key"):
        payload, _ = validate_local(cached["key"], cached)
        if payload:
            ok, msg, exp = activate(cached["key"], hwid)
            if ok:
                _store(cached["key"], str(payload["kid"]), exp)
                return cached["key"], str(payload["kid"]), hwid
            startup_msg = msg if "server" not in msg.lower() else \
                f"Device activation needed: {msg}"
        else:
            startup_msg = "Saved key is invalid — paste it again or Buy a new one."

    result: dict = {}
    win = tk.Tk()
    win.title(f"Interview Assistant — ${PLAN_PRICE} / {PLAN_DAYS} days")
    win.geometry("520x400")
    win.attributes("-topmost", True)

    ttk.Label(win, text="Interview Assistant", font=("Segoe UI", 14, "bold")).pack(pady=(12, 2))
    ttk.Label(win, text=f"${PLAN_PRICE} / {PLAN_DAYS} days · up to {DEVICE_CAP} devices").pack()
    ttk.Label(win, text=f"Device ID: {hwid}", font=("Consolas", 8)).pack(pady=6)

    ttk.Label(win, text="License key:").pack()
    key_var = tk.StringVar(value=cached.get("key", ""))
    ttk.Entry(win, textvariable=key_var, width=60).pack(pady=4)

    status = tk.StringVar(value=startup_msg)
    ttk.Label(win, textvariable=status, wraplength=480).pack(pady=6)

    def _set_status(text: str):
        try:
            win.after(0, lambda: status.set(text))
        except Exception:
            pass

    def _set_busy(busy: bool):
        def _apply():
            try:
                state = "disabled" if busy else "normal"
                buy_btn.configure(state=state)
                act_btn.configure(state=state)
            except Exception:
                pass
        try:
            win.after(0, _apply)
        except Exception:
            pass

    def _finish(key: str, payload: dict, exp: int):
        result["key"], result["kid"] = key, str(payload["kid"])
        _set_status("Active. Starting…")
        _store(key, str(payload["kid"]), exp)
        try:
            win.after(400, win.destroy)
        except Exception:
            pass

    def _try_activate(key: str):
        payload, why = validate_local(key)
        if not payload:
            _set_status(f"Not a valid key: {why}")
            _set_busy(False)
            return
        _set_status("Activating this device…")

        def work():
            def on_retry(attempt, total, exc):
                _set_status(f"Server is waking up… retry {attempt + 1}/{total} (~60s).")
            ok, msg, exp = activate(key, hwid, on_retry=on_retry)
            if ok:
                _finish(key, payload, exp)
            else:
                _set_status(msg)
                _set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def do_activate():
        key = key_var.get().strip()
        if not key:
            status.set("Paste your license key first.")
            return
        _set_busy(True)
        _try_activate(key)

    def do_buy():
        _set_busy(True)
        status.set("Creating invoice… (server may need ~60s to wake if idle)")
        win.update()
        entry_key = key_var.get().strip()
        prev = entry_key if validate_local(entry_key)[0] else None

        def work():
            def on_retry(attempt, total, exc):
                _set_status(f"Server is waking up… retry {attempt + 1}/{total}. "
                            f"Leave this window open (~60s).")
            try:
                order_id, url = create_invoice(prev, on_retry=on_retry)
            except Exception as exc:
                _set_status(f"Buy failed: {_friendly_net_error(exc)}")
                _set_busy(False)
                return
            try:
                webbrowser.open(url)
            except Exception:
                pass
            _set_status(f"Complete payment in the browser (order {order_id}). "
                        f"Waiting for confirmation…")
            # Poll until the server mints the key (IPN can lag a little).
            for _ in range(240):          # 240 × 5s = 20 min
                time.sleep(5)
                try:
                    st, key = order_status(order_id)
                except Exception:
                    continue
                if st == "issued" and key:
                    try:
                        win.after(0, lambda k=key: key_var.set(k))
                    except Exception:
                        pass
                    _set_status("Payment received — activating this device…")
                    _try_activate(key)
                    return
            _set_status("Still waiting for payment — click Buy again to re-check, "
                        "or paste your key once you have it.")
            _set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    row = ttk.Frame(win)
    row.pack(pady=8)
    buy_btn = ttk.Button(row, text=f"Buy ${PLAN_PRICE}", command=do_buy)
    buy_btn.pack(side="left", padx=6)
    act_btn = ttk.Button(row, text="Activate", command=do_activate)
    act_btn.pack(side="left", padx=6)
    ttk.Button(row, text="Quit", command=win.destroy).pack(side="left", padx=6)

    ttk.Label(win, text=f"Payment via NOWPayments (crypto). Renewal extends {PLAN_DAYS} days.\n"
                        f"Key works on up to {DEVICE_CAP} devices. The key also appears\n"
                        "on the payment success page and is auto-filled here.",
              wraplength=480, font=("Segoe UI", 8)).pack(side="bottom", pady=10)
    win.mainloop()
    if "key" in result:
        return result["key"], result["kid"], hwid
    return None
