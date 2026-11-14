
import os
from datetime import datetime, timedelta

import razorpay
from flask import Blueprint, request, jsonify, session

from backend.database import get_db
from backend.auth import login_required

payment_bp = Blueprint("payment", __name__)

PLANS = {
    "monthly": {
        "amount": 19900,
        "days": 30,
        "name": "Monthly Premium"
    },
    "yearly": {
        "amount": 149900,
        "days": 365,
        "name": "Yearly Premium"
    }
}


def get_razorpay_client():
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        raise ValueError("Razorpay keys are not configured.")

    return razorpay.Client(auth=(key_id, key_secret))


@payment_bp.route("/api/payment/create-order", methods=["POST"])
@login_required
def create_order():
    data = request.get_json(silent=True) or {}
    plan_name = data.get("plan")

    if plan_name not in PLANS:
        return jsonify({"error": "Invalid subscription plan."}), 400

    plan = PLANS[plan_name]

    try:
        client = get_razorpay_client()

        order = client.order.create(data={
            "amount": plan["amount"],
            "currency": "INR",
            "receipt": f"ms_{session['user_id']}_{int(datetime.now().timestamp())}"
        })

        db = get_db()

        try:
            db.execute(
                """INSERT INTO payments
                   (user_id, order_id, plan, amount, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (
                    session["user_id"],
                    order["id"],
                    plan_name,
                    plan["amount"]
                )
            )
            db.commit()

        finally:
            db.close()

        return jsonify({
            "order_id": order["id"],
            "amount": plan["amount"],
            "currency": "INR",
            "key_id": os.getenv("RAZORPAY_KEY_ID"),
            "plan_name": plan["name"]
        })

    except Exception:
        return jsonify({"error": "Unable to create payment order."}), 500


@payment_bp.route("/api/payment/verify", methods=["POST"])
@login_required
def verify_payment():
    data = request.get_json(silent=True) or {}

    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not all([order_id, payment_id, signature]):
        return jsonify({"error": "Payment details are incomplete."}), 400

    db = get_db()

    try:
        payment_record = db.execute(
            """SELECT * FROM payments
               WHERE order_id = ? AND user_id = ? AND status = 'pending'""",
            (order_id, session["user_id"])
        ).fetchone()

        if not payment_record:
            return jsonify({"error": "Invalid or already processed order."}), 400

        client = get_razorpay_client()

        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })

        payment_details = client.payment.fetch(payment_id)

        if (
            payment_details.get("order_id") != order_id
            or payment_details.get("status") != "captured"
            or payment_details.get("amount") != payment_record["amount"]
        ):
            return jsonify({
                "error": "Payment is not successfully captured."
            }), 400

        plan = PLANS[payment_record["plan"]]

        user = db.execute(
            """SELECT subscription_expiry FROM users WHERE id = ?""",
            (session["user_id"],)
        ).fetchone()

        now = datetime.utcnow()
        expiry = None

        if user and user["subscription_expiry"]:
            try:
                previous_expiry = datetime.fromisoformat(
                    user["subscription_expiry"]
                )
                if previous_expiry > now:
                    expiry = previous_expiry
            except ValueError:
                pass

        if expiry is None:
            expiry = now

        expiry += timedelta(days=plan["days"])

        db.execute(
            """UPDATE payments
               SET payment_id = ?, status = 'success'
               WHERE order_id = ? AND user_id = ?""",
            (payment_id, order_id, session["user_id"])
        )

        db.execute(
            """UPDATE users
               SET subscription = 'premium',
                   subscription_expiry = ?
               WHERE id = ?""",
            (expiry.isoformat(), session["user_id"])
        )

        db.commit()

        return jsonify({
            "message": "Premium subscription activated!",
            "subscription": "premium",
            "expiry": expiry.isoformat(),
            "redirect": "/payment-success"
        })

    except Exception:
        db.rollback()
        return jsonify({
            "error": "Payment verification failed. Contact support if money was deducted."
        }), 400

    finally:
        db.close()
