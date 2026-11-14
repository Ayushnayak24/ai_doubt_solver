
import re
from functools import wraps

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

from backend.database import get_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/register", methods=["POST"])
def register():

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "All fields are required."}), 400

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters."
        }), 400

    db = get_db()

    try:
        hashed_password = generate_password_hash(password)

        cursor = db.execute(
            """INSERT INTO users (name, email, password)
               VALUES (?, ?, ?)""",
            (name, email, hashed_password)
        )

        db.commit()

        session.clear()
        session["user_id"] = cursor.lastrowid
        session["user_name"] = name

        return jsonify({
            "message": "Registration successful.",
            "redirect": "/dashboard"
        }), 201

    except Exception as error:
        db.rollback()

        if "UNIQUE constraint failed" in str(error):
            return jsonify({
                "error": "Email already registered."
            }), 409

        return jsonify({
            "error": "Registration failed."
        }), 500

    finally:
        db.close()


@auth_bp.route("/api/login", methods=["POST"])
def login():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "error": "Email and password are required."
        }), 400

    db = get_db()

    try:
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user or not check_password_hash(
            user["password"], password
        ):
            return jsonify({
                "error": "Invalid email or password."
            }), 401

        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]

        return jsonify({
            "message": "Login successful.",
            "redirect": "/dashboard"
        })

    finally:
        db.close()


@auth_bp.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "message": "Logged out successfully.",
        "redirect": "/login"
    })


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("user_id"):
            return jsonify({
                "error": "Please login first."
            }), 401

        return view(*args, **kwargs)

    return wrapped

@auth_bp.route("/api/reset-password", methods=["POST"])
def reset_password():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not email or not new_password or not confirm_password:
        return jsonify({
            "success": False,
            "error": "Please fill all fields."
        }), 400

    if new_password != confirm_password:
        return jsonify({
            "success": False,
            "error": "Passwords do not match."
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "success": False,
            "error": "Password must be at least 8 characters."
        }), 400

    db = get_db()

    try:
        user = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            return jsonify({
                "success": False,
                "error": "No account found with this email address."
            }), 404

        hashed_password = generate_password_hash(new_password)

        db.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (hashed_password, email)
        )

        db.commit()

        return jsonify({
            "success": True,
            "message": "Password reset successfully! You can now login."
        }), 200

    except Exception as error:
        db.rollback()
        print("PASSWORD RESET ERROR:", error)

        return jsonify({
            "success": False,
            "error": "Something went wrong. Please try again."
        }), 500

    finally:
        db.close()

