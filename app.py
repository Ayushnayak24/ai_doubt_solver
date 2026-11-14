
import os
from datetime import datetime

from flask import Flask, render_template, session, redirect, jsonify
from dotenv import load_dotenv

from backend.database import init_db, get_db
from backend.auth import auth_bp
from backend.ai import ai_bp
from backend.payment import payment_bp

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Secure Flask secret key
secret_key = os.getenv("FLASK_SECRET_KEY")

if not secret_key or secret_key == "replace_this_with_a_long_random_secret":
    raise RuntimeError(
        "Please set a real FLASK_SECRET_KEY in your .env file."
    )

app.config["SECRET_KEY"] = secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # Local development only


# Register backend blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(payment_bp)


# Initialize database
init_db()


# ---------------- HOME & AUTH PAGES ----------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/register")
def register_page():
    if session.get("user_id"):
        return redirect("/dashboard")
    return render_template("register.html")


@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")


# ---------------- LOGOUT ----------------

@app.route("/logout", methods=["GET", "POST"])
def logout_page():
    session.clear()
    return redirect("/login")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect("/login")

    db = get_db()

    try:
        user = db.execute(
            """
            SELECT id, name, email, subscription,
                   subscription_expiry
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],)
        ).fetchone()

        if not user:
            session.clear()
            return redirect("/login")

        user = dict(user)

        if user.get("subscription") == "premium":
            expiry = user.get("subscription_expiry")

            if expiry:
                try:
                    expiry_date = datetime.fromisoformat(expiry)

                    if expiry_date <= datetime.utcnow():
                        db.execute(
                            """
                            UPDATE users
                            SET subscription = 'free'
                            WHERE id = ?
                            """,
                            (user["id"],)
                        )
                        db.commit()
                        user["subscription"] = "free"

                except ValueError:
                    pass

        return render_template("dashboard.html", user=user)

    finally:
        db.close()


# ---------------- STUDENT PAGES ----------------

@app.route("/doubt-solver")
def doubt_solver():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("doubt_solver.html")


@app.route("/image-solver")
def image_solver():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("image_solver.html")


@app.route("/subjects")
def subjects():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("subjects.html")


@app.route("/history")
def history():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("history.html")


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("profile.html")


@app.route("/settings")
def settings():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings.html")


# ---------------- PRICING & PAYMENT PAGES ----------------

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")


@app.route("/checkout")
def checkout():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("checkout.html")


@app.route("/payment-success")
def payment_success():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("payment_success.html")


# ---------------- HEALTH CHECK ----------------

@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "application": "MindSolve AI"
    })


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=True)
