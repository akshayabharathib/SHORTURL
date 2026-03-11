from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import random
import string
from datetime import datetime
import requests
import re
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey123"
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'akshayabharathib10@gmail.com'
app.config['MAIL_PASSWORD'] = 'kefq vjzw maym ngij'

mail = Mail(app)

serializer = URLSafeTimedSerializer(app.secret_key)


# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # URLs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS urls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_url TEXT,
        short_code TEXT UNIQUE,
        clicks INTEGER
    )
    """)

    # Clicks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clicks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        short_code TEXT,
        click_time TEXT,
        ip_address TEXT,
        location TEXT,
        latitude REAL,
        longitude REAL
    )
    """)

    # Check if lat/lon exist
    cursor.execute("PRAGMA table_info(clicks)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'latitude' not in columns:
        cursor.execute("ALTER TABLE clicks ADD COLUMN latitude REAL")

    if 'longitude' not in columns:
        cursor.execute("ALTER TABLE clicks ADD COLUMN longitude REAL")

    # IP cache
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ip_cache(
        ip_address TEXT PRIMARY KEY,
        location TEXT,
        latitude REAL,
        longitude REAL
    )
    """)

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# -----------------------------
# RANDOM SHORT CODE
# -----------------------------
def generate_unique_code(length=6):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    while True:
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        cursor.execute("SELECT 1 FROM urls WHERE short_code=?", (code,))
        if not cursor.fetchone():
            break

    conn.close()
    return code


# -----------------------------
# URL VALIDATION
# -----------------------------
def is_valid_url(url):
    pattern = re.compile(r'^(?:http|ftp)s?://\S+$', re.IGNORECASE)
    return re.match(pattern, url)


# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("SELECT password FROM users WHERE username=?", (email,))
        user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(user[0], password):
            session["user"] = email
            return redirect("/dashboard")

        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


# -----------------------------
# REGISTER
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            return render_template("register.html", error="Passwords do not match")

        hashed = generate_password_hash(password)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users(username,password) VALUES(?,?)",
                (email, hashed)
            )

            conn.commit()
            conn.close()

            return render_template("register.html", success="Account created successfully")

        except:
            conn.close()
            return render_template("register.html", error="Email already exists")

    return render_template("register.html")


# -----------------------------
# RESET PASSWORD PAGE
# -----------------------------
@app.route("/reset", methods=["GET","POST"])
def reset():

    if request.method == "POST":

        email = request.form["email"]

        token = serializer.dumps(email, salt="password-reset")

        reset_link = url_for("reset_token", token=token, _external=True)

        msg = Message(
            "Password Reset Request",
            sender="yourgmail@gmail.com",
            recipients=[email]
        )

        msg.body = f"Click the link to reset your password:\n{reset_link}"

        mail.send(msg)

        return "Reset link sent to your email."

    return render_template("reset_request.html")
@app.route("/reset/<token>", methods=["GET","POST"])
def reset_token(token):

    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except:
        return "Reset link expired"

    if request.method == "POST":

        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            return "Passwords do not match"

        hashed = generate_password_hash(password)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE users SET password=? WHERE username=?",
            (hashed,email)
        )

        conn.commit()
        conn.close()

        return "Password updated successfully"

    return render_template("reset_password.html")
# -----------------------------
# HOME PAGE
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():

    if "user" not in session:
        return redirect("/login")

    short_url = None
    error = None
    original_input = ""
    custom_input = ""

    if request.method == "POST":

        original_input = request.form.get("original_url", "")
        custom_input = request.form.get("custom_code", "")

        if not is_valid_url(original_input):
            error = "Invalid URL format"
            return render_template(
                "index.html",
                error=error,
                original_url=original_input,
                custom_code=custom_input
            )

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        if custom_input:

            if not re.match(r'^[a-zA-Z0-9_-]{1,20}$', custom_input):

                conn.close()
                error = "Custom code can only contain letters, numbers, _ or -"

                return render_template(
                    "index.html",
                    error=error,
                    original_url=original_input,
                    custom_code=custom_input
                )

            cursor.execute("SELECT * FROM urls WHERE short_code=?", (custom_input,))

            if cursor.fetchone():

                conn.close()
                error = "Custom code already exists"

                return render_template(
                    "index.html",
                    error=error,
                    original_url=original_input,
                    custom_code=custom_input
                )

            short_code = custom_input

        else:
            short_code = generate_unique_code()

        cursor.execute(
            "INSERT INTO urls(original_url, short_code, clicks) VALUES(?,?,?)",
            (original_input, short_code, 0)
        )

        conn.commit()
        conn.close()

        short_url = request.host_url + short_code

        return render_template("index.html", short_url=short_url)

    return render_template(
        "index.html",
        short_url=short_url,
        error=error,
        original_url=original_input,
        custom_code=custom_input
    )


# -----------------------------
# REDIRECT SHORT URL
# -----------------------------
@app.route("/<short_code>")
def redirect_url(short_code):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT original_url, clicks FROM urls WHERE short_code=?", (short_code,))
    data = cursor.fetchone()

    if not data:
        conn.close()
        return "URL not found"

    original_url, clicks = data
    clicks += 1

    cursor.execute("UPDATE urls SET clicks=? WHERE short_code=?", (clicks, short_code))

    click_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    x_forwarded = request.headers.get('X-Forwarded-For')

    if x_forwarded:
        ip_address = x_forwarded.split(",")[0].strip()
    else:
        ip_address = request.remote_addr

    if ip_address in ("127.0.0.1", "::1"):
        ip_address = "8.8.8.8"

    cursor.execute(
        "SELECT location, latitude, longitude FROM ip_cache WHERE ip_address=?",
        (ip_address,)
    )

    cached = cursor.fetchone()

    if cached:
        location, latitude, longitude = cached

    else:

        try:
            r = requests.get(f"http://ip-api.com/json/{ip_address}")
            info = r.json()

            if info.get("status") == "success":
                location = f"{info.get('city','Unknown')}, {info.get('country','Unknown')}"
                latitude = info.get('lat')
                longitude = info.get('lon')
            else:
                location = "Unknown"
                latitude = None
                longitude = None

        except:
            location = "Unknown"
            latitude = None
            longitude = None

        cursor.execute(
            "INSERT OR REPLACE INTO ip_cache(ip_address, location, latitude, longitude) VALUES(?,?,?,?)",
            (ip_address, location, latitude, longitude)
        )

    cursor.execute(
        "INSERT INTO clicks(short_code, click_time, ip_address, location, latitude, longitude) VALUES(?,?,?,?,?,?)",
        (short_code, click_time, ip_address, location, latitude, longitude)
    )

    conn.commit()
    conn.close()

    return redirect(original_url)


# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT original_url, short_code, clicks FROM urls")
    urls = cursor.fetchall()

    cursor.execute("SELECT click_time, ip_address, location, latitude, longitude FROM clicks")
    clicks_map = cursor.fetchall()

    conn.close()

    return render_template("dashboard.html", urls=urls, clicks_map=clicks_map)


# -----------------------------
# CLICK HISTORY
# -----------------------------
@app.route("/clicks/<short_code>")
def click_history(short_code):

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT click_time, ip_address, location FROM clicks WHERE short_code=?",
        (short_code,)
    )

    clicks = cursor.fetchall()

    conn.close()

    return render_template("clicks.html", clicks=clicks)


# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)