# HANDOFF — Telegram payment handler (read first in the new session)

## Goal
Wire the working signed-key licensing gate into the jarvis clone in THIS directory,
with purchases initialized through the **Telegram bot** (NowPayments invoice links
only — no Telegram Stars).

## Locked decisions (do not re-litigate)
1. **Rail: ONLY NowPayments invoices.** Bot sends the invoice link in chat; IPN confirms.
2. **Bot token: reuse the existing one** — `config/api_keys.json` → `telegram_bot_token`
   (chat id `<chat-id>`). Swappable later via `TELEGRAM_BOT_TOKEN` env (dedicated
   product bot recommended before real launch — jarvis UI also polls getUpdates in
   its settings dialog → 409 conflicts while both poll).
3. **Purchase = activation:** `/invoice` stores the device id → key is minted already
   bound (device cap 2 still enforced server-side; `/activate` stays idempotent).
4. **Delivery:** bot messages the key to the paying chat + `myapp://license?key=...`
   link; `/mykeys` lists keys tied to a chat (recovery without accounts).
5. **Work ONLY in this directory.** Original `../shipping` (working v2 licensing) and
   original `../jarvis` are frozen reference trees — do not modify them.

## Directory layout (this dir = jarvis clone at ROOT + shipping pieces merged in)
- `main.py`, `ui.py`, `actions/`, `core/`, `dashboard/`, `config/`, `memory/` …
  — jarvis clone (tkinter app; entry `main()` at main.py:3160, `JarvisUI` then
  `ui.root.mainloop()`)
- `client/` — shipping client incl. **`licensing.py`** (working gate: Ed25519 offline
  verify, device activation, buy+poll auto-fill, Tk paywall `ensure_licensed()`)
- `server/` — **working v2 license server** (invoice/ipn/success/activate/recheck/
  admin, SQLite fallback, mock payments, `.env` with `SIGNING_PRIVATE_KEY`)
- `3lit3/` — earlier distribution build (reference only)
- `tests/license_e2e.py` — portable E2E (18/18 against pre-telegram server; ROOT is
  derived from file location)
- `run_local_test.bat` — starts server (mock) + client paywall end-to-end
- `.gitignore` = shipping + jarvis rules merged (secrets verified via `git check-ignore`)

## DONE so far
- Full licensing v2 (server + client) built and tested **18/18** in original shipping:
  invoice → mock-pay → key on success page → activate cap 2 → revoke → renewal →
  offline client validation. Already copied here.
- jarvis clone copied here (66/66 files, hash-verified).
- Client already detects the OLD Render server and errors clearly (prod Render still
  runs the old code — deploy needed later).

## NOT STARTED (the actual task)
Server schema is still missing `orders.device_id`, `orders.chat_id`,
`issued_keys.chat_id` (add CREATE + tolerant `ALTER TABLE` migration in `init_db`).

Build list:
1. `server/tgpay.py` — raw stdlib bot (no new deps): daemon thread long-polling
   `getUpdates`; handlers: `/start buy_<order_id>` (lookup order → send NowPayments
   invoice link w/ URL button; record `orders.chat_id`), `/mykeys` (keys by chat),
   help. Expose `send_message(chat_id, text)` callable from the IPN thread.
2. `server/app.py`:
   - `/invoice` accepts `device_id` (+ returns `bot_start`/`t.me` deep link when
     `TELEGRAM_BOT_TOKEN` set)
   - on mint (in `_mint`): insert activation row if order has `device_id`;
     stamp `issued_keys.chat_id` from `orders.chat_id`; then `tgpay.send_message`
     (key + success-page link) to that chat
   - startup: launch bot thread when `TELEGRAM_BOT_TOKEN` set
3. `server/.env` += `TELEGRAM_BOT_TOKEN` (copy value from `config/api_keys.json`);
   mirror (commented) in `.env.example` + `render.yaml`.
4. `client/licensing.py`: `/invoice` payload += `device_id` (get_hwid()); Buy prefers
   bot deep link (`t.me/...?...start=buy_<order_id>`) over opening invoice_url directly;
   keep web fallback + existing 5s order polling (auto-fill unchanged).
5. Gate in root `main.py` `main()`: before `JarvisUI(...)` — sys.path add `./client`,
   `from licensing import ensure_licensed, recheck, RECHECK_MINUTES`; honor
   `--no-license`; store key/kid/device; soft watchdog thread (recheck → False =
   revoke → messagebox + exit; None = keep running).
6. Tests: update `tests/license_e2e.py` for device-bound-at-mint (activation exists
   after payment WITHOUT calling `/activate`) + chat_id stamping (fake chat id in
   `/start`-less path or direct DB); real bot smoke = send `/start buy_<order>` to the
   bot yourself.

## Key facts
- Jarvis = **tkinter** (not Qt) → reuse Tk paywall as-is.
- Public key (embedded in client/licensing.py): `c336325513196d7971034fc8fb329458c5ae0f98e81f47c66bde27b9380a5e72`
  — private seed lives ONLY in `server/.env` (`SIGNING_PRIVATE_KEY`). Never copy private
  key into the client. Rotation = `server/mint_key.py --genkey`.
- **No `.venv` in this dir** (excluded from copy) → run `setup.bat` first. Test file and
  bat files assume `<root>\.venv\Scripts\python.exe`.
- Local money-free flow: `MOCK_NOWPAYMENTS=1` (in server/.env) → invoice_url is the
  local `/mock-pay/<order>` page → clicking it = instant paid. The bot will send this
  same link in mock mode, so the whole telegram flow is testable with zero crypto.
- Server .env: `PUBLIC_BASE_URL=http://127.0.0.1:8000`, `ADMIN_TOKEN=local-dev-admin-token`,
  `DEVICE_CAP=2`, `PRICE_USD=14.99`, `PERIOD_DAYS=30`.
- Prod Render (https://interview-assistant-okvy.onrender.com) still runs the OLD server;
  deploying the new one is a later step (needs dashboard env: SIGNING_PRIVATE_KEY,
  PUBLIC_BASE_URL, drop LLM_API_KEY/KEY_ISSUANCE_SECRET, TELEGRAM_BOT_TOKEN).

## Local test procedure (after build)
1. `setup.bat` (creates .venv)
2. `run_local_test.bat` → paywall → Buy → (with telegram work: bot chat gets the
   invoice link; without it yet: browser mock invoice) → auto-fill → Activate →
   jarvis clone boots.
3. `tests\license_e2e.py` via `.venv\Scripts\python.exe` → expect 0 failures.
