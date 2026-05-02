from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import random
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- MAIL CONFIG ----------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'pasyanthisanagavaram@gmail.com'
app.config['MAIL_PASSWORD'] = 'wphyokmsyoirkfpt'

mail = Mail(app)

# ---------------- FILE UPLOAD ----------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- DATABASE ----------------
db = sqlite3.connect("database.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT,
    title TEXT,
    status TEXT,
    severity TEXT,
    created_at TEXT,
    image TEXT,
    user_email TEXT,
    priority INTEGER,
    category TEXT           
)
""")

db.commit()

# ---------------- HELPER ----------------
def generate_id():
    return "CMP" + str(random.randint(10000,99999))

from datetime import datetime

def calculate_priority(severity, created_at):
    score = 0

    # Severity weight
    if severity == "High":
        score += 3
    elif severity == "Medium":
        score += 2
    else:
        score += 1

    # Time factor
    days_old = (datetime.now() - created_at).days
    score += days_old

    return score

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():

    import re

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"].lower()

        pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(pattern, email):
            return render_template("register.html", error="Invalid email format")

        password = generate_password_hash(request.form["password"])
        role = "user"

        cursor.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,))
        if cursor.fetchone():
            return render_template("register.html", error="Email already exists!")

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (name, email, password, role))

        db.commit()

        return redirect("/login")

    return render_template("register.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].lower()
        password = request.form["password"]

        cursor.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):

            session["user"] = user[1]
            session["email"] = user[2]
            session["role"] = user[4]

            return redirect("/category")

        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():

    if not session.get("user"):
        return redirect("/login")
    
    

    role = session.get("role", "").strip().lower()
    email = session.get("email")

    search = request.args.get("search")
    status_filter = request.args.get("status")

    # ---------------- ADMIN ----------------
    if role == "admin":

        if search and status_filter:
            cursor.execute("""
                SELECT * FROM complaints
                WHERE (title LIKE ? OR status LIKE ?)
                AND status=?
               ORDER BY priority DESC
            """, ('%' + search + '%', '%' + search + '%', status_filter))

        elif search:
            cursor.execute("""
                SELECT * FROM complaints
                WHERE title LIKE ? OR status LIKE ?
                ORDER BY priority DESC
            """, ('%' + search + '%', '%' + search + '%'))

        elif status_filter:
            cursor.execute("""
                SELECT * FROM complaints
                WHERE status=?
                ORDER BY priority DESC
            """, (status_filter,))

        else:
            category = session.get("category")

            if category:
                cursor.execute(
                    "SELECT * FROM complaints WHERE category=? ORDER BY priority DESC",
                    (category,)
                )
            else:
                cursor.execute("SELECT * FROM complaints ORDER BY priority DESC")

    # ---------------- USER ----------------
    else:

        if search and status_filter:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=? AND category=?
                AND (title LIKE ? OR status LIKE ?)
                AND status=?
                ORDER BY priority DESC
            """, (email, category, '%' + search + '%', '%' + search + '%', status_filter))

        elif search:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=? AND category=?
                AND (title LIKE ? OR status LIKE ?)
                ORDER BY priority DESC
            """, (email, '%' + search + '%', '%' + search + '%'))

        elif status_filter:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=? AND status=?
                ORDER BY priority DESC
            """, (email, status_filter))

        else:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=?
                ORDER BY priority DESC
            """, (email,))

    complaints = cursor.fetchall()

    # ---------- COUNTS ----------
    if role == "admin":
        cursor.execute("SELECT COUNT(*) as total FROM complaints")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE status='Pending'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) as resolved FROM complaints WHERE status='Resolved'")
        resolved = cursor.fetchone()[0]

    else:
        cursor.execute("SELECT COUNT(*) as total FROM complaints WHERE user_email=?", (email,))
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE user_email=? AND status='Pending'", (email,))
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) as resolved FROM complaints WHERE user_email=? AND status='Resolved'", (email,))
        resolved = cursor.fetchone()[0]

    return render_template("dashboard.html",
                           complaints=complaints,
                           total=total,
                           pending=pending,
                           resolved=resolved)

# ---------------- COMPLAINT ----------------
@app.route("/complaint", methods=["GET","POST"])
def complaint():

    if not session.get("user"):
        return redirect("/login")

    if request.method == "POST":

        cid = generate_id()

        user_email = session["email"]
        user_name = session["user"]

        location = request.form.get("location")
        title = request.form.get("title")
        description = request.form.get("description")
        severity = request.form.get("severity")
        image = request.files.get("image")

        if not location or not title or not description or not severity:
            return "All fields are required!"

        if not image or image.filename == "":
            return "Please upload an image!"

        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        category = session.get("category")

        from datetime import datetime

        created_time = datetime.now()
        priority = calculate_priority(severity, created_time)

        cursor.execute("""
        INSERT INTO complaints 
        (title, status, severity, created_at, image, user_email, priority, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
        title,
        "Pending",
        severity,
        created_time,
        filename,
        session["email"],
        priority,
        session.get("category")   # 🔥 THIS IS KEY
))

        db.commit()

        msg = Message(
            "Complaint Submitted",
            sender=app.config['MAIL_USERNAME'],
            recipients=[user_email]
        )

        msg.body = f"""
Complaint ID: {cid}
Title: {title}
Status: Pending
"""

        mail.send(msg)

        flash("Complaint submitted successfully!")

        return redirect("/dashboard")

    return render_template("complaint.html")

# ---------------- UPDATE STATUS ----------------
@app.route("/update_status", methods=["POST"])
def update_status():

    if session.get("role", "").strip().lower() != "admin":
        return "Unauthorized"

    id = request.form["id"]
    status = request.form["status"]

    cursor.execute("UPDATE complaints SET status=? WHERE id=?", (status, id))
    db.commit()

    cursor.execute("SELECT * FROM complaints WHERE id=?", (id,))
    complaint = cursor.fetchone()

    if complaint and status == "Resolved":
        complaint_id = complaint[1]
        title = complaint[2]
        user_email = complaint[7]
        status_val = complaint[3]

        msg = Message(
    subject=f"Complaint {complaint_id} Resolved",
    sender=app.config['MAIL_USERNAME'],
    recipients=[user_email]
)

    msg.body = f"""
    Complaint ID: {complaint_id}
    Title: {title}
    Status: {status_val}
    """

    try:
            mail.send(msg)
    except Exception as e:
            print("Mail Error:", e)

    return redirect("/dashboard")

# ---------------- CATEGORY ----------------
@app.route("/category")
def category():
    return render_template("category.html")

@app.route("/set_category/<cat>")
def set_category(cat):
    session["category"] = cat
    return redirect("/role")

# ---------------- ROLE ----------------
@app.route("/role")
def role():
    return redirect("/dashboard")

@app.route("/set_role/<role>")
def set_role(role):
    return redirect("/complaint")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/make_admin/<email>", methods=["POST"])
def make_admin(email):

    if not session.get("user") or session.get("role") != "admin":
        return "Unauthorized", 403

    if email == session.get("email"):
        return redirect("/dashboard")

    cursor.execute(
        "UPDATE users SET role='admin' WHERE email=?",
        (email,)
    )
    db.commit()

    return redirect("/dashboard")

@app.route("/users")
def users():

    if session.get("role") != "admin":
        return "Unauthorized"

    cursor.execute("SELECT name, email, role FROM users")
    users = cursor.fetchall()

    return render_template("users.html", users=users)


@app.route("/remove_admin/<email>", methods=["POST"])
def remove_admin(email):

    if session.get("role") != "admin":
        return "Unauthorized"

    if email == session.get("email"):
        return redirect("/users")

    cursor.execute(
        "UPDATE users SET role='user' WHERE email=?",
        (email,)
    )
    db.commit()

    return redirect("/users")

# ---------------- RUN ----------------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)