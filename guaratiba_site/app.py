from __future__ import annotations

import os
import random
import sqlite3
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "guaratiba.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # set True behind HTTPS in production
)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "h.d.hoficial3658@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "@Ww365888")
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)
CODE_TTL_MINUTES = 10

DEFAULT_CATEGORIES = [
    ("casas", "Casas"),
    ("farmacias", "Farmácias"),
    ("restaurantes", "Restaurantes"),
]

DEFAULT_ITEMS = [
    {
        "category_slug": "casas",
        "name": "Casa Brisa do Mar",
        "photo": "https://images.unsplash.com/photo-1499793983690-e29da59ef1c2?auto=format&fit=crop&w=1200&q=80",
        "contact": "73988887777",
        "extra": "R$ 450/dia",
        "description": "Frente mar com 3 suítes e piscina privativa.",
    },
    {
        "category_slug": "restaurantes",
        "name": "Cabana do Peixe",
        "photo": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&w=1200&q=80",
        "contact": "73988885544",
        "extra": "Frutos do mar",
        "description": "A melhor moqueca da região com vista para o pôr do sol.",
    },
    {
        "category_slug": "farmacias",
        "name": "Farmácia Central",
        "photo": "https://images.unsplash.com/photo-1586015555751-63bb77f4322a?auto=format&fit=crop&w=1200&q=80",
        "contact": "7332981010",
        "extra": "08h às 22h",
        "description": "Medicamentos e perfumaria no centro de Guaratiba.",
    },
]


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            photo TEXT,
            contact TEXT,
            extra TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) AS total FROM categories")
    if cur.fetchone()["total"] == 0:
        for slug, name in DEFAULT_CATEGORIES:
            cur.execute("INSERT INTO categories (slug, name) VALUES (?, ?)", (slug, name))
        conn.commit()

    cur.execute("SELECT COUNT(*) AS total FROM items")
    if cur.fetchone()["total"] == 0:
        for item in DEFAULT_ITEMS:
            cur.execute("SELECT id FROM categories WHERE slug = ?", (item["category_slug"],))
            category = cur.fetchone()
            if category:
                cur.execute(
                    """
                    INSERT INTO items (category_id, name, photo, contact, extra, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (category["id"], item["name"], item["photo"], item["contact"], item["extra"], item["description"]),
                )
        conn.commit()

    cur.execute("SELECT id FROM admin_users WHERE email = ?", (ADMIN_EMAIL,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO admin_users (email, password_hash) VALUES (?, ?)",
            (ADMIN_EMAIL, ADMIN_PASSWORD_HASH),
        )
        conn.commit()
    conn.close()


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return json_error("Acesso não autorizado.", 401)
        return fn(*args, **kwargs)
    return wrapper


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def send_code_email(email: str, code: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    use_tls = os.environ.get("SMTP_USE_TLS", "1") == "1"

    if not all([host, username, password]):
        print(f"[LOGIN CODE] {email} -> {code}")
        return True

    msg = MIMEText(f"Seu código de acesso é: {code}

Ele expira em {CODE_TTL_MINUTES} minutos.")
    msg["Subject"] = "Código de acesso administrativo"
    msg["From"] = username
    msg["To"] = email

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"Falha ao enviar email: {exc}")
        print(f"[LOGIN CODE] {email} -> {code}")
        return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/adm")
def admin_page():
    return render_template("adm.html")


@app.route("/api/site-data")
def site_data():
    conn = db()
    categories = [dict(row) for row in conn.execute("SELECT * FROM categories ORDER BY name").fetchall()]
    items = [dict(row) for row in conn.execute(
        """
        SELECT items.*, categories.slug AS category_slug, categories.name AS category_name
        FROM items
        JOIN categories ON categories.id = items.category_id
        ORDER BY items.id DESC
        """
    ).fetchall()]
    conn.close()
    return jsonify({"ok": True, "categories": categories, "items": items})


@app.route("/api/admin/login/start", methods=["POST"])
def admin_login_start():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = db()
    user = conn.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return json_error("E-mail ou senha inválidos.", 401)

    code = f"{random.randint(0, 999999):06d}"
    expires_at = now_utc() + timedelta(minutes=CODE_TTL_MINUTES)

    conn = db()
    conn.execute("DELETE FROM login_codes WHERE email = ?", (email,))
    conn.execute(
        "INSERT INTO login_codes (email, code, expires_at, used) VALUES (?, ?, ?, 0)",
        (email, code, expires_at.isoformat()),
    )
    conn.commit()
    conn.close()

    send_code_email(email, code)
    session["pending_admin_email"] = email
    return jsonify({"ok": True, "message": "Código enviado para o e-mail cadastrado."})


@app.route("/api/admin/login/verify", methods=["POST"])
def admin_login_verify():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    pending_email = session.get("pending_admin_email")
    if not pending_email or pending_email != email:
        return json_error("Solicitação de login expirada. Gere um novo código.", 401)

    conn = db()
    row = conn.execute(
        """
        SELECT * FROM login_codes
        WHERE email = ? AND code = ? AND used = 0
        ORDER BY id DESC LIMIT 1
        """,
        (email, code),
    ).fetchone()
    if not row:
        conn.close()
        return json_error("Código inválido.", 401)

    expires_at = datetime.fromisoformat(row["expires_at"])
    if now_utc() > expires_at:
        conn.close()
        return json_error("Código expirado. Gere um novo código.", 401)

    conn.execute("UPDATE login_codes SET used = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()

    session.pop("pending_admin_email", None)
    session["admin_authenticated"] = True
    session["admin_email"] = email
    return jsonify({"ok": True})


@app.route("/api/admin/logout", methods=["POST"])
@require_admin
def admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/admin/me")
def admin_me():
    return jsonify({"ok": bool(session.get("admin_authenticated")), "email": session.get("admin_email")})


@app.route("/api/categories", methods=["GET"])
def get_categories():
    conn = db()
    rows = [dict(row) for row in conn.execute("SELECT * FROM categories ORDER BY name").fetchall()]
    conn.close()
    return jsonify({"ok": True, "categories": rows})


@app.route("/api/categories", methods=["POST"])
@require_admin
def create_category():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower()
    if not name:
        return json_error("Nome da categoria é obrigatório.")
    if not slug:
        slug = "-".join(name.lower().split())

    conn = db()
    try:
        conn.execute("INSERT INTO categories (slug, name) VALUES (?, ?)", (slug, name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return json_error("Já existe uma categoria com esse nome/slug.", 409)
    row = conn.execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return jsonify({"ok": True, "category": dict(row)})


@app.route("/api/categories/<int:category_id>", methods=["PATCH"])
@require_admin
def update_category(category_id: int):
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower()
    if not name:
        return json_error("Nome da categoria é obrigatório.")
    if not slug:
        slug = "-".join(name.lower().split())

    conn = db()
    try:
        conn.execute("UPDATE categories SET name = ?, slug = ? WHERE id = ?", (name, slug, category_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return json_error("Slug já está em uso.", 409)
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    conn.close()
    if not row:
        return json_error("Categoria não encontrada.", 404)
    return jsonify({"ok": True, "category": dict(row)})


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
@require_admin
def delete_category(category_id: int):
    conn = db()
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/items", methods=["GET"])
def get_items():
    conn = db()
    rows = [dict(row) for row in conn.execute(
        """
        SELECT items.*, categories.slug AS category_slug, categories.name AS category_name
        FROM items
        JOIN categories ON categories.id = items.category_id
        ORDER BY items.id DESC
        """
    ).fetchall()]
    conn.close()
    return jsonify({"ok": True, "items": rows})


@app.route("/api/items", methods=["POST"])
@require_admin
def create_item():
    data = request.get_json(force=True, silent=True) or {}
    category_id = data.get("category_id")
    name = (data.get("name") or "").strip()
    photo = (data.get("photo") or "").strip()
    contact = (data.get("contact") or "").strip()
    extra = (data.get("extra") or "").strip()
    description = (data.get("description") or "").strip()

    if not category_id or not name:
        return json_error("Categoria e nome são obrigatórios.")

    conn = db()
    conn.execute(
        """
        INSERT INTO items (category_id, name, photo, contact, extra, description, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (category_id, name, photo, contact, extra, description, now_utc().isoformat()),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT items.*, categories.slug AS category_slug, categories.name AS category_name
        FROM items
        JOIN categories ON categories.id = items.category_id
        WHERE items.id = last_insert_rowid()
        """
    ).fetchone()
    conn.close()
    return jsonify({"ok": True, "item": dict(row)})


@app.route("/api/items/<int:item_id>", methods=["PATCH"])
@require_admin
def update_item(item_id: int):
    data = request.get_json(force=True, silent=True) or {}
    category_id = data.get("category_id")
    name = (data.get("name") or "").strip()
    photo = (data.get("photo") or "").strip()
    contact = (data.get("contact") or "").strip()
    extra = (data.get("extra") or "").strip()
    description = (data.get("description") or "").strip()

    if not category_id or not name:
        return json_error("Categoria e nome são obrigatórios.")

    conn = db()
    conn.execute(
        """
        UPDATE items
        SET category_id = ?, name = ?, photo = ?, contact = ?, extra = ?, description = ?, updated_at = ?
        WHERE id = ?
        """,
        (category_id, name, photo, contact, extra, description, now_utc().isoformat(), item_id),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT items.*, categories.slug AS category_slug, categories.name AS category_name
        FROM items
        JOIN categories ON categories.id = items.category_id
        WHERE items.id = ?
        """,
        (item_id,),
    ).fetchone()
    conn.close()
    if not row:
        return json_error("Item não encontrado.", 404)
    return jsonify({"ok": True, "item": dict(row)})


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@require_admin
def delete_item(item_id: int):
    conn = db()
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.errorhandler(404)
def not_found(_):
    return render_template("index.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
