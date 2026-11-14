
import os
import logging

from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, session
from google import genai
from google.genai import types

from backend.database import get_db

load_dotenv()

ai_bp = Blueprint("ai", __name__)

logging.basicConfig(level=logging.INFO)


# ---------------- ASK AI ----------------

@ai_bp.route("/api/ask", methods=["POST"])
def ask_ai():

    if not session.get("user_id"):
        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401

    data = request.get_json(silent=True) or {}

    question = data.get("question", "")
    subject = data.get("subject", "General")

    if not isinstance(question, str) or not question.strip():
        return jsonify({
            "success": False,
            "error": "Please enter your question."
        }), 400

    question = question.strip()

    if len(question) > 10000:
        return jsonify({
            "success": False,
            "error": "Question must be under 10,000 characters."
        }), 400

    if not isinstance(subject, str):
        subject = "General"

    subject = subject.strip()[:50] or "General"

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = "gemini-3.8-flash"

    if not api_key:
        return jsonify({
            "success": False,
            "error": "GEMINI_API_KEY is missing. Check your .env file."
        }), 500

    
    # Generate answer using Gemini with automatic fallback

    client = genai.Client(api_key=api_key)

    models = [
        "gemini-3.5-flash-lite"
    ]

    answer = None
    last_error = None

    for model in models:
        try:
            logging.info("Trying Gemini model: %s", model)

            response = client.models.generate_content(
                model=model,
                contents=(
                    f"Subject: {subject}\n"
                    f"Student's question: {question}"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are MindSolve AI, a friendly student tutor. "
                        "Explain answers in simple English. "
                        "Give detailed step-by-step explanations "
                        "and examples where useful."
                    ),
                    max_output_tokens=2048
                )
            )

            if response.text and response.text.strip():
                answer = response.text.strip()
                logging.info("Answer generated using %s", model)
                break

        except Exception as error:
            last_error = error
            logging.exception("Model %s failed", model)

    if not answer:
        return jsonify({
            "success": False,
            "error": (
                "Both Gemini models are currently unavailable. "
                "Please try again shortly."
            )
        }), 503


    # Save answer in database
    db = None

    try:
        db = get_db()

        cursor = db.execute(
            """
            INSERT INTO chats (user_id, question, answer, subject)
            VALUES (?, ?, ?, ?)
            """,
            (
                session["user_id"],
                question,
                answer,
                subject
            )
        )

        db.commit()
        chat_id = cursor.lastrowid

        return jsonify({
            "success": True,
            "chat_id": chat_id,
            "question": question,
            "answer": answer,
            "subject": subject
        }), 200

    except Exception:
        logging.exception("DATABASE SAVE ERROR")

        return jsonify({
            "success": False,
            "error": "AI generated an answer, but saving it to history failed."
        }), 500

    finally:
        if db:
            db.close()


# ---------------- CHAT HISTORY ----------------

@ai_bp.route("/api/history", methods=["GET"])
def get_chat_history():

    if not session.get("user_id"):
        return jsonify({
            "success": False,
            "error": "Please login first."
        }), 401

    db = get_db()

    try:
        chats = db.execute(
            """
            SELECT id, question, answer, subject, created_at
            FROM chats
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 100
            """,
            (session["user_id"],)
        ).fetchall()

        return jsonify({
            "success": True,
            "history": [dict(chat) for chat in chats]
        })

    except Exception:
        logging.exception("HISTORY DATABASE ERROR")

        return jsonify({
            "success": False,
            "error": "Unable to load chat history."
        }), 500

    finally:
        db.close()
