-- License schema (v2: signed keys + device activations).
-- The server creates these automatically (init_db); this file is the reference.

-- One row per purchase intent, created by POST /invoice.
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,          -- ORD-<random>, also the NowPayments order_id
    prev_key TEXT DEFAULT '',           -- renewal: previous key extends from its expiry
    created  BIGINT DEFAULT 0
);

-- One row per minted license key (signed Ed25519, format 3L3-<payload>.<sig>).
CREATE TABLE IF NOT EXISTS issued_keys (
    kid      TEXT PRIMARY KEY,          --8 hex chars, embedded in the key payload
    key_str  TEXT NOT NULL,
    order_id TEXT DEFAULT '',           -- empty for admin-minted keys
    note     TEXT DEFAULT '',
    iat      BIGINT DEFAULT 0,
    exp      BIGINT DEFAULT 0,
    revoked  INTEGER DEFAULT 0          -- soft revocation, checked by /recheck
);

-- Device activations: max DEVICE_CAP (2) distinct device_ids per key.
CREATE TABLE IF NOT EXISTS activations (
    kid          TEXT NOT NULL,
    device_id    TEXT NOT NULL,
    activated_at BIGINT DEFAULT 0,
    PRIMARY KEY (kid, device_id)
);

-- Raw NowPayments IPN audit log; payment_id PK makes double-fire IPNs harmless.
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id   TEXT DEFAULT '',
    status     TEXT DEFAULT '',
    raw        TEXT DEFAULT '',
    ts         BIGINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_issued_order ON issued_keys(order_id);
