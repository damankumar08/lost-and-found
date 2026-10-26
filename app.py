from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
app = Flask(__name__)

app.secret_key = "lost_found_secret_key"

# Folder for uploaded images
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():

    conn = get_db()

    # Users table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0
    )
""")
    

    # Items table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            date TEXT NOT NULL,
            image TEXT,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
        # Claims table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            claimant_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (claimant_id) REFERENCES users(id)
        )
    """)
    # Create admin account if it doesn't exist

    admin = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        ("admin@college.com",)
    ).fetchone()

    if admin is None:

        hashed_password = generate_password_hash("admin123")

        conn.execute(
            """
            INSERT INTO users
            (name, email, password, is_admin)
            VALUES (?, ?, ?, ?)
            """,
            (
                "Administrator",
                "admin@college.com",
                hashed_password,
                1
            )
        )
    conn.commit()
    conn.close()
# ---------------- CLAIM ITEM ----------------

@app.route("/item/<int:item_id>/claim", methods=["GET", "POST"])
def claim_item(item_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    # Get the item
    item = conn.execute(
        "SELECT * FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        return "Item not found!"

    # Don't allow someone to claim their own report
    if item["user_id"] == session["user_id"]:
        conn.close()
        return "You cannot claim your own item."

    if request.method == "POST":

        message = request.form["message"].strip()

        if not message:
            conn.close()
            return "Please enter a message."

        conn.execute(
            """
            INSERT INTO claims
            (item_id, claimant_id, message)
            VALUES (?, ?, ?)
            """,
            (
                item_id,
                session["user_id"],
                message
            )
        )

        conn.commit()
        conn.close()

        flash("Your claim has been submitted successfully!", "success")

        return redirect(
            url_for(
                "item_details",
                item_id=item_id
            )
        )

    conn.close()

    return render_template(
        "claim.html",
        item=item
    )
# ---------------- CLAIMS DASHBOARD ----------------

@app.route("/claims")
def claims_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    # Get claims for items owned by the logged-in user
    claims = conn.execute(
        """
        SELECT
            claims.id,
            claims.item_id,
            claims.message,
            claims.status,
            claims.created_at,

            items.name AS item_name,
            items.type AS item_type,
            items.status AS item_status,

            users.name AS claimant_name,
            users.email AS claimant_email

        FROM claims

        JOIN items
            ON claims.item_id = items.id

        JOIN users
            ON claims.claimant_id = users.id

        WHERE items.user_id = ?

        ORDER BY claims.id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "claims.html",
        claims=claims
    )
# ---------------- HANDLE CLAIM ----------------

@app.route("/claims/<int:claim_id>/<action>")
def handle_claim(claim_id, action):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if action not in ["approve", "reject"]:
        return "Invalid action."

    conn = get_db()

    # Get claim and make sure the logged-in user owns the item
    claim = conn.execute(
        """
        SELECT
            claims.*,
            items.user_id AS owner_id,
            items.id AS item_id

        FROM claims

        JOIN items
            ON claims.item_id = items.id

        WHERE claims.id = ?
        """,
        (claim_id,)
    ).fetchone()

    if claim is None:
        conn.close()
        return "Claim not found."

    # Only the item owner can handle the claim
    if claim["owner_id"] != session["user_id"]:
        conn.close()
        return "Access denied."

    if action == "approve":

        # Approve this claim
        conn.execute(
            """
            UPDATE claims
            SET status = 'approved'
            WHERE id = ?
            """,
            (claim_id,)
        )

        # Mark the item as recovered
        conn.execute(
            """
            UPDATE items
            SET status = 'recovered'
            WHERE id = ?
            """,
            (claim["item_id"],)
        )

        # Reject other pending claims for this item
        conn.execute(
            """
            UPDATE claims
            SET status = 'rejected'
            WHERE item_id = ?
            AND id != ?
            AND status = 'pending'
            """,
            (
                claim["item_id"],
                claim_id
            )
        )

    else:

        # Reject claim
        conn.execute(
            """
            UPDATE claims
            SET status = 'rejected'
            WHERE id = ?
            """,
            (claim_id,)
        )

    conn.commit()
    conn.close()
    if action == "approve":
        flash("Claim approved! The item has been marked as recovered.", "success")
    else:
        flash("Claim rejected.", "error")
    return redirect(url_for("claims_dashboard"))

# ---------------- SMART MATCHING ----------------

def find_matches(item):

    conn = get_db()

    # We only compare against active found items
    # when the current item is lost.
    if item["type"] == "lost":

        opposite_type = "found"

    else:

        opposite_type = "lost"

    matches = conn.execute(
        """
        SELECT *
        FROM items
        WHERE type = ?
        AND status = 'active'
        AND id != ?
        """,
        (
            opposite_type,
            item["id"]
        )
    ).fetchall()

    conn.close()

    if not matches:
        return []

    # Text from the current item
    current_text = (
        str(item["name"]) + " " +
        str(item["category"]) + " " +
        str(item["description"] or "") + " " +
        str(item["location"])
    )

    # Text from other reports
    other_texts = []

    for match in matches:

        text = (
            str(match["name"]) + " " +
            str(match["category"]) + " " +
            str(match["description"] or "") + " " +
            str(match["location"])
        )

        other_texts.append(text)

    # TF-IDF converts text into numerical vectors
    vectorizer = TfidfVectorizer(
        stop_words="english"
    )

    vectors = vectorizer.fit_transform(
        [current_text] + other_texts
    )

    # Compare current item with all other items
    similarities = cosine_similarity(
        vectors[0:1],
        vectors[1:]
    )[0]

    results = []

    for index, score in enumerate(similarities):

        # Only show reasonably similar results
        if score >= 0.15:

            results.append({
                "item": matches[index],
                "score": round(score * 100, 1)
            })

    # Highest match first
    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:5]
# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
                """,
                (name, email, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Email already registered!"

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["is_admin"] = user["is_admin"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        return "Invalid email or password!"

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        name=session["user_name"]
    )


# ---------------- REPORT ITEM ----------------

@app.route("/report/<item_type>", methods=["GET", "POST"])
def report_item(item_type):

    # Make sure user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only allow lost or found
    if item_type not in ["lost", "found"]:
        return "Invalid item type!"

    if request.method == "POST":

        name = request.form["name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        date = request.form["date"]

        # Get uploaded image
        image = request.files.get("image")

        filename = None

        if image and image.filename:

            filename = secure_filename(image.filename)

            # Make filename unique
            filename = str(session["user_id"]) + "_" + filename

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

        conn = get_db()

        conn.execute(
            """
            INSERT INTO items
            (user_id, name, category, description,
             location, date, image, type)

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,

            (
                session["user_id"],
                name,
                category,
                description,
                location,
                date,
                filename,
                item_type
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("items"))

    return render_template(
        "report_item.html",
        item_type=item_type
    )


# ---------------- VIEW ITEMS ----------------

@app.route("/items")
def items():

    search = request.args.get("search", "")
    category = request.args.get("category", "")
    item_type = request.args.get("type", "")
    location = request.args.get("location", "")

    conn = get_db()

    query = """
        SELECT items.*, users.name AS username
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.status = 'active'
    """

    parameters = []

    # Search by item name
    if search:
        query += " AND items.name LIKE ?"
        parameters.append("%" + search + "%")

    # Filter by category
    if category:
        query += " AND items.category = ?"
        parameters.append(category)

    # Filter by lost/found
    if item_type:
        query += " AND items.type = ?"
        parameters.append(item_type)

    # Search by location
    if location:
        query += " AND items.location LIKE ?"
        parameters.append("%" + location + "%")

    query += " ORDER BY items.id DESC"

    items = conn.execute(
        query,
        parameters
    ).fetchall()

    conn.close()

    return render_template(
        "items.html",
        items=items,
        search=search,
        category=category,
        item_type=item_type,
        location=location
    )

# ---------------- ITEM DETAILS ----------------

@app.route("/item/<int:item_id>")
def item_details(item_id):

    conn = get_db()

    item = conn.execute(
        """
        SELECT items.*, users.name AS username,
               users.email AS user_email
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = ?
        """,
        (item_id,)
    ).fetchone()

    conn.close()

    if item is None:
        return "Item not found!"

    matches = find_matches(item)

    return render_template(
        "item_details.html",
        item=item,
        matches=matches
    )

# ---------------- MARK AS RECOVERED ----------------

@app.route("/item/<int:item_id>/recovered")
def mark_recovered(item_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    item = conn.execute(
        """
        SELECT * FROM items
        WHERE id = ?
        """,
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        return "Item not found!"

    # Only the person who posted the item
    # can mark it as recovered.

    if item["user_id"] != session["user_id"]:

        conn.close()

        return "You are not allowed to modify this item!"

    conn.execute(
        """
        UPDATE items
        SET status = 'recovered'
        WHERE id = ?
        """,
        (item_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("items"))

# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
def admin_dashboard():

    # Check if user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    # Get current user
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    # Check admin permission
    if user is None or user["is_admin"] != 1:
        conn.close()
        return "Access denied! Admins only."

    # Count total users
    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    # Count active lost items
    total_lost = conn.execute(
        """
        SELECT COUNT(*)
        FROM items
        WHERE type = 'lost'
        AND status = 'active'
        """
    ).fetchone()[0]

    # Count active found items
    total_found = conn.execute(
        """
        SELECT COUNT(*)
        FROM items
        WHERE type = 'found'
        AND status = 'active'
        """
    ).fetchone()[0]

    # Count recovered items
    total_recovered = conn.execute(
        """
        SELECT COUNT(*)
        FROM items
        WHERE status = 'recovered'
        """
    ).fetchone()[0]

    # Get recent reports
    recent_items = conn.execute(
        """
        SELECT items.*, users.name AS username
        FROM items
        JOIN users ON items.user_id = users.id
        ORDER BY items.id DESC
        LIMIT 10
        """
    ).fetchall()

    # Get all users
    users = conn.execute(
        """
        SELECT id, name, email, is_admin
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_lost=total_lost,
        total_found=total_found,
        total_recovered=total_recovered,
        recent_items=recent_items,
        users=users
    )
# ---------------- ADMIN DELETE ITEM ----------------

@app.route("/admin/delete-item/<int:item_id>")
def delete_item(item_id):

    # Only logged-in users can access this
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    # Check current user
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    # Only admin can delete
    if user is None or user["is_admin"] != 1:
        conn.close()
        return "Access denied! Admins only."

    # Delete item
    conn.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ---------------- START ----------------

if __name__ == "__main__":

    create_tables()

    app.run(debug=True)