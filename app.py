from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
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
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root123",
    database="swacchagrahi_db"
)

cursor = db.cursor(dictionary=True)

# DEBUG (put AFTER cursor creation)
cursor.execute("SELECT DATABASE()")
print("APP DB:", cursor.fetchone())

# ---------------- HELPER ----------------
def generate_id():
    return "CMP" + str(random.randint(10000,99999))

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

        cursor.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
        if cursor.fetchone():
            return render_template("register.html", error="Email already exists!")

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (%s, %s, %s, %s)
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

        cursor.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(%s)", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user["password"], password):

            session["user"] = user["name"]
            session["email"] = user["email"]
            session["role"] = user["role"]

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
                WHERE (title LIKE %s OR status LIKE %s)
                AND status=%s
                ORDER BY id DESC
            """, ('%' + search + '%', '%' + search + '%', status_filter))

        elif search:
            cursor.execute("""
                SELECT * FROM complaints
                WHERE title LIKE %s OR status LIKE %s
                ORDER BY id DESC
            """, ('%' + search + '%', '%' + search + '%'))

        elif status_filter:
            cursor.execute("""
                SELECT * FROM complaints
                WHERE status=%s
                ORDER BY id DESC
            """, (status_filter,))

        else:
            category = session.get("category")
            if category:
                cursor.execute(
                    "SELECT * FROM complaints WHERE category=%s ORDER BY id DESC",
                    (category,)
                )
            else:
                cursor.execute("SELECT * FROM complaints ORDER BY id DESC")

    # ---------------- USER ----------------
    else:

        if search and status_filter:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=%s 
                AND (title LIKE %s OR status LIKE %s)
                AND status=%s 
                ORDER BY id DESC
            """, (email, '%' + search + '%', '%' + search + '%', status_filter))

        elif search:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=%s 
                AND (title LIKE %s OR status LIKE %s)
                ORDER BY id DESC
            """, (email, '%' + search + '%', '%' + search + '%'))

        elif status_filter:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=%s AND status=%s 
                ORDER BY id DESC
            """, (email, status_filter))

        else:
            cursor.execute("""
                SELECT * FROM complaints 
                WHERE user_email=%s 
                ORDER BY id DESC
            """, (email,))

    complaints = cursor.fetchall()

    # ---------- COUNTS ----------
    if role == "admin":
        cursor.execute("SELECT COUNT(*) as total FROM complaints")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE status='Pending'")
        pending = cursor.fetchone()["pending"]

        cursor.execute("SELECT COUNT(*) as resolved FROM complaints WHERE status='Resolved'")
        resolved = cursor.fetchone()["resolved"]

    else:
        cursor.execute("SELECT COUNT(*) as total FROM complaints WHERE user_email=%s", (email,))
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE user_email=%s AND status='Pending'", (email,))
        pending = cursor.fetchone()["pending"]

        cursor.execute("SELECT COUNT(*) as resolved FROM complaints WHERE user_email=%s AND status='Resolved'", (email,))
        resolved = cursor.fetchone()["resolved"]

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

        cursor.execute("""
            INSERT INTO complaints
            (complaint_id, user_name, user_email, location, title, description, image, status, severity, category)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
            cid,
            user_name,        # name
            user_email,       # email ✅
            location,
            title,
            description,
            filename,
            "Pending",
            severity,
            category
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

    cursor.execute("UPDATE complaints SET status=%s WHERE id=%s", (status, id))
    db.commit()

    cursor.execute("SELECT * FROM complaints WHERE id=%s", (id,))
    complaint = cursor.fetchone()

    if complaint and status == "Resolved":

        msg = Message(
            subject=f"Complaint {complaint['complaint_id']} Resolved",
            sender=app.config['MAIL_USERNAME'],
            recipients=[complaint["user_email"]]
        )

        msg.body = f"""
Complaint ID: {complaint['complaint_id']}
Title: {complaint['title']}
Status: {complaint['status']}
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
        "UPDATE users SET role='admin' WHERE email=%s",
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

@app.route("/promote/<email>")
def promote(email):

    if session.get("role") != "admin":
        return "Unauthorized"

    cursor.execute("UPDATE users SET role='admin' WHERE email=%s", (email,))
    db.commit()

    return redirect("/users")

@app.route("/remove_admin/<email>", methods=["POST"])
def remove_admin(email):

    if session.get("role") != "admin":
        return "Unauthorized"

    if email == session.get("email"):
        return redirect("/users")

    cursor.execute(
        "UPDATE users SET role='user' WHERE email=%s",
        (email,)
    )
    db.commit()

    return redirect("/users")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)