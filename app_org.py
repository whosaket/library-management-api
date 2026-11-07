from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector

from db import get_connection

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Table definitions: primary key + the columns a client is allowed to set.
# Table and column names come from this dict only, never from user input.
# ---------------------------------------------------------------------------
TABLES = {
    "category": {"pk": "cat_id", "cols": ["cname"]},
    "publisher": {"pk": "pub_id", "cols": ["pname"]},
    "members": {
        "pk": "member_id",
        "cols": ["member_name", "email", "phone_no", "doj", "status"],
    },
    "books": {
        "pk": "book_id",
        "cols": ["title", "author", "category_id", "publisher_id", "publication_year"],
    },
    "issue": {
        "pk": "transaction_id",
        "cols": ["book_id", "member_id", "issue_date", "due_date", "return_date", "status"],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_json_safe(rows):
    """Convert date/datetime values so jsonify can handle them."""
    out = []
    for row in rows:
        out.append(
            {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in row.items()}
        )
    return out


def run_query(sql, params=(), one=False):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    rows = to_json_safe(rows)
    return (rows[0] if rows else None) if one else rows


def run_write(sql, params=()):
    """Run an INSERT/UPDATE/DELETE. Returns (rowcount, lastrowid)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        result = (cur.rowcount, cur.lastrowid)
        cur.close()
    finally:
        conn.close()
    return result


def next_id(table):
    pk = TABLES[table]["pk"]
    row = run_query(f"SELECT COALESCE(MAX({pk}), 0) + 1 AS n FROM {table}", one=True)
    return row["n"]


@app.errorhandler(mysql.connector.Error)
def handle_db_error(err):
    # 1451/1452 = foreign key violations, 1062 = duplicate key
    code = getattr(err, "errno", None)
    if code in (1451, 1452):
        return jsonify({"error": "Foreign key constraint failed", "detail": str(err)}), 409
    if code == 1062:
        return jsonify({"error": "Duplicate entry", "detail": str(err)}), 409
    return jsonify({"error": "Database error", "detail": str(err)}), 500


# ---------------------------------------------------------------------------
# Generic CRUD routes for all 5 tables
# ---------------------------------------------------------------------------
def register_crud(table):
    pk = TABLES[table]["pk"]
    cols = TABLES[table]["cols"]

    def list_all():
        return jsonify(run_query(f"SELECT * FROM {table}"))

    def get_one(item_id):
        row = run_query(f"SELECT * FROM {table} WHERE {pk} = %s", (item_id,), one=True)
        if row is None:
            return jsonify({"error": f"{table} id {item_id} not found"}), 404
        return jsonify(row)

    def create():
        data = request.get_json(silent=True) or {}
        new_id = data.get(pk) or next_id(table)
        fields = [pk] + [c for c in cols if c in data]
        values = [new_id] + [data[c] for c in cols if c in data]
        sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})"
        run_write(sql, values)
        return jsonify({pk: new_id}), 201

    def update(item_id):
        data = request.get_json(silent=True) or {}
        fields = [c for c in cols if c in data]
        if not fields:
            return jsonify({"error": "No valid fields to update", "allowed": cols}), 400
        sql = f"UPDATE {table} SET {', '.join(f + ' = %s' for f in fields)} WHERE {pk} = %s"
        run_write(sql, [data[f] for f in fields] + [item_id])
        row = run_query(f"SELECT * FROM {table} WHERE {pk} = %s", (item_id,), one=True)
        if row is None:
            return jsonify({"error": f"{table} id {item_id} not found"}), 404
        return jsonify(row)

    def delete(item_id):
        count, _ = run_write(f"DELETE FROM {table} WHERE {pk} = %s", (item_id,))
        if count == 0:
            return jsonify({"error": f"{table} id {item_id} not found"}), 404
        return jsonify({"deleted": item_id})

    base = f"/{table}"
    app.add_url_rule(base, f"{table}_list", list_all, methods=["GET"])
    app.add_url_rule(f"{base}/<int:item_id>", f"{table}_get", get_one, methods=["GET"])
    app.add_url_rule(base, f"{table}_create", create, methods=["POST"])
    app.add_url_rule(f"{base}/<int:item_id>", f"{table}_update", update, methods=["PUT"])
    app.add_url_rule(f"{base}/<int:item_id>", f"{table}_delete", delete, methods=["DELETE"])


for _table in TABLES:
    register_crud(_table)


# ---------------------------------------------------------------------------
# Library-specific routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Serve the web page (index.html must be in the same folder as app.py)."""
    return send_from_directory(app.root_path, "index.html")


@app.route("/api")
def home():
    return jsonify(
        {
            "message": "Library Management API",
            "tables": list(TABLES.keys()),
            "extra_routes": [
                "GET /books/details",
                "GET /books/search?q=<text>",
                "GET /members/<id>/issues",
                "GET /issue/overdue",
                "POST /issue/borrow",
                "POST /issue/<transaction_id>/return",
            ],
        }
    )


@app.route("/books/details", methods=["GET"])
def books_with_details():
    """Books joined with category and publisher names."""
    sql = """
        SELECT b.book_id, b.title, b.author, b.publication_year,
               c.cname AS category, p.pname AS publisher
        FROM books b
        LEFT JOIN category c ON b.category_id = c.cat_id
        LEFT JOIN publisher p ON b.publisher_id = p.pub_id
        ORDER BY b.book_id
    """
    return jsonify(run_query(sql))


@app.route("/books/search", methods=["GET"])
def search_books():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Provide a search term, e.g. /books/search?q=python"}), 400
    like = f"%{q}%"
    rows = run_query(
        "SELECT * FROM books WHERE title LIKE %s OR author LIKE %s", (like, like)
    )
    return jsonify(rows)


@app.route("/members/<int:member_id>/issues", methods=["GET"])
def member_issues(member_id):
    sql = """
        SELECT i.transaction_id, b.title, i.issue_date, i.due_date,
               i.return_date, i.status
        FROM issue i
        JOIN books b ON i.book_id = b.book_id
        WHERE i.member_id = %s
        ORDER BY i.issue_date DESC
    """
    return jsonify(run_query(sql, (member_id,)))


@app.route("/issue/overdue", methods=["GET"])
def overdue():
    """Books not yet returned and past their due date."""
    sql = """
        SELECT i.transaction_id, b.title, m.member_name, i.issue_date, i.due_date
        FROM issue i
        JOIN books b ON i.book_id = b.book_id
        JOIN members m ON i.member_id = m.member_id
        WHERE i.return_date IS NULL AND i.due_date < CURDATE()
        ORDER BY i.due_date
    """
    return jsonify(run_query(sql))


@app.route("/issue/borrow", methods=["POST"])
def borrow_book():
    """Body: {"book_id": 1, "member_id": 2, "days": 14}  (days is optional)."""
    data = request.get_json(silent=True) or {}
    if "book_id" not in data or "member_id" not in data:
        return jsonify({"error": "book_id and member_id are required"}), 400

    book_id, member_id = data["book_id"], data["member_id"]
    days = int(data.get("days", 14))

    if run_query("SELECT 1 FROM books WHERE book_id = %s", (book_id,), one=True) is None:
        return jsonify({"error": "Book not found"}), 404
    if run_query("SELECT 1 FROM members WHERE member_id = %s", (member_id,), one=True) is None:
        return jsonify({"error": "Member not found"}), 404

    already = run_query(
        "SELECT transaction_id FROM issue WHERE book_id = %s AND return_date IS NULL",
        (book_id,),
        one=True,
    )
    if already:
        return jsonify({"error": "Book is already issued", "transaction_id": already["transaction_id"]}), 409

    today = date.today()
    due = today + timedelta(days=days)
    tid = next_id("issue")
    run_write(
        "INSERT INTO issue (transaction_id, book_id, member_id, issue_date, due_date, return_date, status) "
        "VALUES (%s, %s, %s, %s, %s, NULL, %s)",
        (tid, book_id, member_id, today, due, "Issued"),
    )
    return jsonify({"transaction_id": tid, "issue_date": today.isoformat(), "due_date": due.isoformat()}), 201


@app.route("/issue/<int:transaction_id>/return", methods=["POST"])
def return_book(transaction_id):
    row = run_query(
        "SELECT return_date FROM issue WHERE transaction_id = %s", (transaction_id,), one=True
    )
    if row is None:
        return jsonify({"error": "Transaction not found"}), 404
    if row["return_date"] is not None:
        return jsonify({"error": "Book already returned"}), 409

    today = date.today()
    run_write(
        "UPDATE issue SET return_date = %s, status = %s WHERE transaction_id = %s",
        (today, "Returned", transaction_id),
    )
    return jsonify({"transaction_id": transaction_id, "return_date": today.isoformat()})


if __name__ == "__main__":
    app.run(debug=True)
