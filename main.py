from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import ollama
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from flask_cors import CORS
import sqlite3
import secrets
import re

app = Flask(__name__)
lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"
app.secret_key = "132123213213"  # Change to a more secure key in production
CORS(app, supports_credentials=True)

# SQLite setup
conn = sqlite3.connect("database.db", check_same_thread=False)
with conn:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS USERS(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            email TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS MEMORY(
            id TEXT,
            user_id INTEGER,
            message TEXT,
            reply TEXT,
            FOREIGN KEY(user_id) REFERENCES USERS(id)
        )
    """)
    conn.commit()

# User class for login
class User(UserMixin):
    def __init__(self, id, username, password, email):
        self.id = id
        self.username = username
        self.password = password
        self.email = email

    @staticmethod
    def get(user_id):
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM USERS WHERE id=?", (user_id,))
        user = cur.fetchone()
        return User(user[0], user[1], user[2], user[3]) if user else None

@lm.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route("/")
def index():
    return "🟢 Server is running! Login at /login"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        match_against = "email" if "@" in username else "username"
        with conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM USERS WHERE {match_against}=? AND password=?",
                (username, password),
            )
            user = cur.fetchone()
            if user:
                login_user(User(user[0], user[1], user[2], user[3]))
                return redirect(url_for("index"))
            flash("Invalid username or password", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/process_message", methods=["POST"])
@login_required
def process_message():
    data = request.get_json()
    message = data.get("message", "")
    chat_id = data.get("chat_id") or secrets.token_urlsafe(16)

    contenxt = ""
    with conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT message, reply FROM MEMORY WHERE id=? AND user_id=?",
            (chat_id, current_user.id),
        )
        chats = cur.fetchall()
        if chats:
            contenxt = "Here is your previous chat history, answer accordingly:\n"
            for msg, reply in chats:
                contenxt += f"User: {msg}\nYou: {reply}\n"
        else:
            contenxt = "This is a new chat, please answer accordingly:\n"

        contenxt += f"User: {message}\n"

    response = ollama.chat(
        model="llama3", messages=[{"role": "user", "content": contenxt}]
    )

    with conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO MEMORY (id, user_id, message, reply) VALUES (?, ?, ?, ?)",
            (chat_id, current_user.id, message, response["message"]["content"]),
        )
        conn.commit()

    return jsonify({
        "status": "success",
        "message": response["message"]["content"],
        "chat_id": chat_id
    })

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=80)
