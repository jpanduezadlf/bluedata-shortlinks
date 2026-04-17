"""
Bluedata Short Links
"""
import os, string, secrets
import psycopg2
from flask import Flask, request, jsonify, redirect, abort, send_from_directory

app = Flask(__name__, static_folder="static")

DATABASE_URL = os.environ["DATABASE_URL"]
ALLOWED_CHARS = string.ascii_letters + string.digits
CODE_LENGTH = 5

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    code       TEXT PRIMARY KEY,
                    original   TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    clicks     INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_original ON links(original)")
    finally:
        conn.close()
    print("[OK] DB inicializada en Neon PostgreSQL")

def generate_code(length=CODE_LENGTH):
    return ''.join(secrets.choice(ALLOWED_CHARS) for _ in range(length))

def is_valid_url(url):
    if not url or not isinstance(url, str):
        return False
    return url.strip().startswith("http://") or url.strip().startswith("https://")

def is_valid_code(code):
    if not code or not isinstance(code, str) or len(code) > 30:
        return False
    return all(c in set(ALLOWED_CHARS + "-_") for c in code)

# ─── API ─────────────────────────────────────────────────────────

@app.route("/api/shorten", methods=["POST"])
def shorten():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    custom_code = (data.get("code") or "").strip()

    if not url:
        return jsonify({"error": "Falta el campo 'url'"}), 400
    if not is_valid_url(url):
        return jsonify({"error": "URL invalida. Debe comenzar con http:// o https://"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM links WHERE original = %s", (url,))
            existing = cur.fetchone()
            if existing:
                return jsonify({"short": existing[0], "url": url, "exists": True})

            if custom_code:
                if not is_valid_code(custom_code):
                    return jsonify({"error": "Codigo invalido. Solo letras, numeros, - y _ (max 30)"}), 400
                cur.execute("SELECT 1 FROM links WHERE code = %s", (custom_code,))
                if cur.fetchone():
                    return jsonify({"error": "El codigo '" + custom_code + "' ya esta en uso"}), 409
                code = custom_code
            else:
                for _ in range(20):
                    code = generate_code()
                    cur.execute("SELECT 1 FROM links WHERE code = %s", (code,))
                    if not cur.fetchone():
                        break
                else:
                    return jsonify({"error": "No se pudo generar codigo. Intenta de nuevo."}), 500

            cur.execute("INSERT INTO links (code, original) VALUES (%s, %s)", (code, url))
    finally:
        conn.close()

    return jsonify({"short": code, "url": url, "exists": False}), 201

@app.route("/api/links", methods=["GET"])
def list_links():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code, original, created_at, clicks FROM links ORDER BY created_at DESC")
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return jsonify(rows)

@app.route("/api/links/<link_code>", methods=["DELETE"])
def delete_link(link_code):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE code = %s", (link_code,))
            if cur.rowcount == 0:
                return jsonify({"error": "Link no encontrado"}), 404
    finally:
        conn.close()
    return jsonify({"deleted": link_code})

# ─── Admin panel ─────────────────────────────────────────────────

@app.route("/admin")
def admin_panel():
    return send_from_directory("static", "admin.html")

# ─── Redirect ────────────────────────────────────────────────────

@app.route("/<short_code>")
def redirect_short(short_code):
    if short_code in ("admin", "favicon.ico", "static") or short_code.startswith("api"):
        abort(404)
    if not is_valid_code(short_code):
        abort(404)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT original FROM links WHERE code = %s", (short_code,))
            row = cur.fetchone()
            if not row:
                abort(404)
            cur.execute("UPDATE links SET clicks = clicks + 1 WHERE code = %s", (short_code,))
    finally:
        conn.close()
    return redirect(row[0], code=301)

# ─── 404 ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Recurso no encontrado"}), 404
    return '<html><body style="font-family:system-ui;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#0c0e13;color:#e8eaed"><div style="text-align:center"><h1 style="font-size:72px;opacity:.3;margin:0">404</h1><p style="font-size:18px;color:#8b92a5">Este link corto no existe.</p></div></body></html>', 404

# ─── Init ────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[OK] Servidor en http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
