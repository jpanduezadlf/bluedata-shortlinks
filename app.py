"""
Bluedata Short Links — App completa
====================================
Un solo archivo. Un solo deploy en Render.

- GET  /admin           → Panel visual para crear y gestionar links
- GET  /<code>          → Redirige al destino original
- POST /api/shorten     → API: crea link  { "url": "...", "code": "..." }
- GET  /api/links       → API: lista links
- DELETE /api/links/<c> → API: elimina link
"""

import os
import string
import secrets
import sqlite3
from flask import Flask, request, jsonify, redirect, abort

app = Flask(__name__)

DB_PATH = os.environ.get("SHORTLINKS_DB", "shortlinks.db")
DOMAIN = os.environ.get("SHORT_DOMAIN", "bluedata.review")
ALLOWED_CHARS = string.ascii_letters + string.digits
CODE_LENGTH = 5


# ─── Base de datos ───────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS links (
                code       TEXT PRIMARY KEY,
                original   TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                clicks     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_original ON links(original)")
    print(f"[OK] DB inicializada en {DB_PATH}")


# ─── Helpers ─────────────────────────────────────────────────────

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
        return jsonify({"error": "URL inválida. Debe comenzar con http:// o https://"}), 400

    with get_db() as conn:
        existing = conn.execute("SELECT code FROM links WHERE original = ?", (url,)).fetchone()
        if existing:
            return jsonify({"short": existing["code"], "url": url, "exists": True})

        if custom_code:
            if not is_valid_code(custom_code):
                return jsonify({"error": "Código inválido. Solo letras, números, - y _ (máx 30)"}), 400
            if conn.execute("SELECT 1 FROM links WHERE code = ?", (custom_code,)).fetchone():
                return jsonify({"error": f"El código '{custom_code}' ya está en uso"}), 409
            code = custom_code
        else:
            for _ in range(20):
                code = generate_code()
                if not conn.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone():
                    break
            else:
                return jsonify({"error": "No se pudo generar código. Intenta de nuevo."}), 500

        conn.execute("INSERT INTO links (code, original) VALUES (?, ?)", (code, url))

    return jsonify({"short": code, "url": url, "exists": False}), 201


@app.route("/api/links", methods=["GET"])
def list_links():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, original, created_at, clicks FROM links ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/links/<code>", methods=["DELETE"])
def delete_link(code):
    with get_db() as conn:
        result = conn.execute("DELETE FROM links WHERE code = ?", (code,))
        if result.rowcount == 0:
            return jsonify({"error": "Link no encontrado"}), 404
    return jsonify({"deleted": code})


# ─── Redirect ────────────────────────────────────────────────────

@app.route("/<code>")
def redirect_short(code):
    if code in ("admin", "favicon.ico") or code.startswith("api"):
        abort(404)
    if not is_valid_code(code):
        abort(404)
    with get_db() as conn:
        row = conn.execute("SELECT original FROM links WHERE code = ?", (code,)).fetchone()
        if not row:
            abort(404)
        conn.execute("UPDATE links SET clicks = clicks + 1 WHERE code = ?", (code,))
    return redirect(row["original"], code=301)


# ─── Panel Admin ─────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bluedata Short Links</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
    --bg: #0c0e13; --surface: #14171e; --surface-raised: #1a1e28;
    --border: #252a36; --accent: #3b82f6; --accent-soft: rgba(59,130,246,.12);
    --accent-hover: #2563eb; --text-primary: #e8eaed; --text-secondary: #8b92a5;
    --text-tertiary: #555d73; --row-hover: rgba(255,255,255,.03);
    --error: #ef4444; --danger-soft: rgba(239,68,68,.08); --success: #10b981;
}
@media (prefers-color-scheme: light) {
    :root {
        --bg: #f4f5f7; --surface: #ffffff; --surface-raised: #f9fafb;
        --border: #e2e5ea; --accent: #2563eb; --accent-soft: rgba(37,99,235,.08);
        --accent-hover: #1d4ed8; --text-primary: #1a1d23; --text-secondary: #6b7280;
        --text-tertiary: #9ca3af; --row-hover: rgba(0,0,0,.02);
        --error: #dc2626; --danger-soft: rgba(220,38,38,.06);
    }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Outfit', sans-serif; background: var(--bg); color: var(--text-primary); -webkit-font-smoothing: antialiased; }
input { font-family: inherit; }
input::placeholder { color: var(--text-tertiary); }
input:focus { outline: none; }

.wrap { max-width: 640px; margin: 0 auto; padding: 40px 20px 80px; }
.header { text-align: center; margin-bottom: 36px; }
.header h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; display: inline; vertical-align: middle; }
.header p { font-size: 14px; color: var(--text-secondary); margin-top: 8px; }
.domain { color: var(--accent); font-weight: 600; }
.logo { width: 36px; height: 36px; border-radius: 10px; display: inline-flex; align-items: center;
         justify-content: center; font-size: 18px; vertical-align: middle; margin-right: 10px;
         background: linear-gradient(135deg, #3b82f6, #8b5cf6); }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 20px; margin-bottom: 12px; }
.url-input { width: 100%; padding: 14px 16px; font-size: 15px; font-family: 'JetBrains Mono', monospace;
             background: var(--surface-raised); border: 1px solid var(--border); border-radius: 12px;
             color: var(--text-primary); transition: border-color .2s, box-shadow .2s; margin-bottom: 10px; }
.url-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.row { display: flex; gap: 10px; }
.code-box { flex: 1; display: flex; align-items: center; background: var(--surface-raised);
            border: 1px solid var(--border); border-radius: 12px; padding: 0 12px; gap: 4px; }
.code-prefix { font-size: 13px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
.code-input { flex: 1; padding: 12px 0; font-size: 13px; font-family: 'JetBrains Mono', monospace;
              background: transparent; border: none; color: var(--text-primary); }
.btn-shorten { padding: 12px 28px; font-size: 14px; font-weight: 600; background: var(--accent);
               color: #fff; border: none; border-radius: 12px; cursor: pointer; transition: background .15s; white-space: nowrap; }
.btn-shorten:hover { background: var(--accent-hover); }
.btn-shorten:disabled { opacity: .5; cursor: not-allowed; }
.error { margin-top: 10px; padding: 8px 14px; font-size: 13px; color: var(--error);
         background: var(--danger-soft); border-radius: 10px; font-weight: 500; display: none; }

.stats { display: flex; align-items: center; justify-content: space-between; padding: 12px 4px; margin-bottom: 4px; }
.stats-count { font-size: 13px; color: var(--text-secondary); font-weight: 500; }
.search { padding: 6px 12px; font-size: 12px; background: var(--surface); border: 1px solid var(--border);
          border-radius: 8px; color: var(--text-primary); width: 160px; }

.list { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; overflow: hidden; }
.list-empty { border: none; text-align: center; padding: 48px 20px; background: transparent; }
.list-empty .icon { font-size: 48px; margin-bottom: 12px; opacity: .5; }
.list-empty p { font-size: 15px; color: var(--text-secondary); opacity: .5; }

.link-row { display: flex; align-items: center; gap: 12px; padding: 14px 18px; transition: background .2s;
            animation: slideIn .25s ease-out; }
.link-row:hover { background: var(--row-hover); }
.link-sep { height: 1px; background: var(--border); margin: 0 18px; }
.link-icon { width: 38px; height: 38px; border-radius: 10px; background: var(--accent-soft);
             display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 16px; }
.link-content { flex: 1; min-width: 0; }
.link-short { font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700;
              color: var(--accent); cursor: pointer; margin-bottom: 3px; word-break: break-all; }
.link-short:hover { text-decoration: underline; }
.link-original { font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.link-meta { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; margin-right: 8px; text-align: right; }
.link-clicks { font-size: 10px; color: var(--text-tertiary); }
.btn-icon { background: rgba(255,255,255,.04); border: 1px solid var(--border); border-radius: 8px;
            padding: 6px 10px; cursor: pointer; font-size: 13px; color: var(--text-primary); transition: background .15s; }
.btn-icon:hover { background: var(--accent-soft); }
.btn-del { background: transparent; border: none; border-radius: 8px; padding: 6px 8px;
           cursor: pointer; font-size: 13px; opacity: .25; transition: opacity .2s; color: var(--text-primary); }
.link-row:hover .btn-del { opacity: .7; }

.toast { position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%) translateY(20px);
         opacity: 0; transition: all .3s cubic-bezier(.4,0,.2,1); background: var(--success);
         color: #fff; padding: 10px 24px; border-radius: 40px; font-size: 14px; font-weight: 600;
         pointer-events: none; z-index: 999; box-shadow: 0 8px 30px rgba(16,185,129,.35); }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

.footer { text-align: center; margin-top: 24px; font-size: 12px; color: var(--text-tertiary); line-height: 1.6; }
@keyframes slideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.3);
           border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; margin-right: 8px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
    <div class="header">
        <div><span class="logo">⚡</span><h1>Bluedata Short Links</h1></div>
        <p>Acorta URLs largas en links memorables bajo <span class="domain" id="domainDisplay"></span></p>
    </div>

    <div class="card">
        <input class="url-input" id="urlInput" type="text" placeholder="Pega tu URL larga aquí..." autofocus>
        <div class="row">
            <div class="code-box">
                <span class="code-prefix" id="codePrefix"></span>
                <input class="code-input" id="codeInput" type="text" placeholder="código (opcional)" maxlength="30">
            </div>
            <button class="btn-shorten" id="btnShorten">Acortar</button>
        </div>
        <div class="error" id="error"></div>
    </div>

    <div class="stats" id="statsBar" style="display:none">
        <span class="stats-count" id="statsCount"></span>
        <input class="search" id="searchInput" type="text" placeholder="Buscar...">
    </div>

    <div id="linksList"></div>

    <div class="footer">Los links se guardan en el servidor y funcionan para cualquier persona.</div>
</div>

<div class="toast" id="toast">✓ Copiado al portapapeles</div>

<script>
let DOMAIN = "";
let allLinks = [];

document.addEventListener("DOMContentLoaded", async () => {
    // Descubrir el dominio automáticamente
    DOMAIN = location.host;
    document.getElementById("domainDisplay").textContent = DOMAIN;
    document.getElementById("codePrefix").textContent = DOMAIN + "/";

    document.getElementById("urlInput").addEventListener("keydown", e => { if (e.key === "Enter") shortenLink(); });
    document.getElementById("codeInput").addEventListener("keydown", e => { if (e.key === "Enter") shortenLink(); });
    document.getElementById("codeInput").addEventListener("input", e => {
        e.target.value = e.target.value.replace(/[^a-zA-Z0-9_\\-]/g, "").slice(0, 30);
    });
    document.getElementById("btnShorten").addEventListener("click", shortenLink);
    document.getElementById("searchInput").addEventListener("input", renderLinks);

    await loadLinks();
});

async function loadLinks() {
    try {
        const res = await fetch("/api/links");
        allLinks = await res.json();
    } catch (err) {
        allLinks = [];
    }
    renderLinks();
}

async function shortenLink() {
    const urlInput = document.getElementById("urlInput");
    const codeInput = document.getElementById("codeInput");
    const btn = document.getElementById("btnShorten");
    const errorEl = document.getElementById("error");
    errorEl.style.display = "none";

    const url = urlInput.value.trim();
    const code = codeInput.value.trim();

    if (!url) { showError("Ingresa una URL"); return; }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Creando...';

    try {
        const res = await fetch("/api/shorten", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, code: code || undefined })
        });
        const data = await res.json();

        if (!res.ok) {
            showError(data.error || "Error al acortar");
            return;
        }

        copyToClipboard(location.protocol + "//" + DOMAIN + "/" + data.short);
        urlInput.value = "";
        codeInput.value = "";
        await loadLinks();
    } catch (err) {
        showError("Error de conexión con el servidor");
    } finally {
        btn.disabled = false;
        btn.textContent = "Acortar";
    }
}

async function deleteLink(code) {
    if (!confirm("¿Eliminar este link?")) return;
    try {
        await fetch("/api/links/" + code, { method: "DELETE" });
        await loadLinks();
    } catch (err) {
        showError("Error al eliminar");
    }
}

function renderLinks() {
    const search = (document.getElementById("searchInput").value || "").toLowerCase();
    const filtered = search
        ? allLinks.filter(l => l.original.toLowerCase().includes(search) || l.code.toLowerCase().includes(search))
        : allLinks;

    const statsBar = document.getElementById("statsBar");
    const container = document.getElementById("linksList");

    if (allLinks.length === 0) {
        statsBar.style.display = "none";
        container.innerHTML = '<div class="list-empty"><div class="icon">🔗</div><p>Aún no hay links acortados</p></div>';
        return;
    }

    statsBar.style.display = "flex";
    document.getElementById("statsCount").textContent =
        allLinks.length + " link" + (allLinks.length !== 1 ? "s" : "") +
        " creado" + (allLinks.length !== 1 ? "s" : "");

    if (filtered.length === 0) {
        container.innerHTML = '<div class="list-empty"><p>Sin resultados para "' + escapeHtml(search) + '"</p></div>';
        return;
    }

    let html = '<div class="list">';
    filtered.forEach((link, i) => {
        const shortDisplay = DOMAIN + "/" + link.code;
        const shortFull = location.protocol + "//" + DOMAIN + "/" + link.code;
        const original = link.original.length > 55 ? link.original.slice(0, 55) + "…" : link.original;
        const clicks = link.clicks || 0;

        html += '<div class="link-row">' +
            '<div class="link-icon">🔗</div>' +
            '<div class="link-content">' +
            '<div class="link-short" onclick="copyToClipboard(\'' + shortFull.replace(/'/g, "\\'") + '\')" title="Click para copiar">' + escapeHtml(shortDisplay) + '</div>' +
            '<div class="link-original" title="' + escapeHtml(link.original) + '">' + escapeHtml(original) + '</div>' +
            '</div>' +
            '<div class="link-meta">' + timeAgo(link.created_at) + '<br><span class="link-clicks">' + clicks + ' click' + (clicks !== 1 ? 's' : '') + '</span></div>' +
            '<button class="btn-icon" onclick="copyToClipboard(\'' + shortFull.replace(/'/g, "\\'") + '\')" title="Copiar">📋</button>' +
            '<button class="btn-del" onclick="deleteLink(\'' + link.code + '\')" title="Eliminar">🗑</button>' +
            '</div>';
        if (i < filtered.length - 1) html += '<div class="link-sep"></div>';
    });
    html += '</div>';
    container.innerHTML = html;
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const t = document.getElementById("toast");
        t.classList.add("show");
        setTimeout(() => t.classList.remove("show"), 1800);
    });
}

function showError(msg) {
    const el = document.getElementById("error");
    el.textContent = msg;
    el.style.display = "block";
}

function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}

function timeAgo(dateStr) {
    const diff = Date.now() - new Date(dateStr + "Z").getTime();
    if (isNaN(diff) || diff < 0) return "justo ahora";
    if (diff < 60000) return "justo ahora";
    if (diff < 3600000) return "hace " + Math.floor(diff / 60000) + " min";
    if (diff < 86400000) return "hace " + Math.floor(diff / 3600000) + "h";
    return "hace " + Math.floor(diff / 86400000) + "d";
}
</script>
</body>
</html>"""


@app.route("/admin")
def admin_panel():
    return ADMIN_HTML


# ─── 404 ─────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Recurso no encontrado"}), 404
    return """<!DOCTYPE html><html><head><title>Link no encontrado</title>
    <style>body{font-family:system-ui;display:flex;justify-content:center;align-items:center;
    min-height:100vh;background:#0c0e13;color:#e8eaed}.box{text-align:center}
    h1{font-size:72px;margin:0;opacity:.3}p{font-size:18px;color:#8b92a5}</style>
    </head><body><div class="box"><h1>404</h1><p>Este link corto no existe.</p></div></body></html>""", 404


# ─── Arranque ────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[OK] Servidor en http://localhost:{port}")
    print(f"[OK] Panel admin en http://localhost:{port}/admin")
    app.run(host="0.0.0.0", port=port, debug=True)
