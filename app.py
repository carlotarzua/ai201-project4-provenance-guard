"""Flask API for Provenance Guard."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address

from audit import (
    append_audit_event,
    get_content_record,
    get_recent_log,
    save_content_record,
    update_content_record,
    utc_now,
)
from detection import SignalError, groq_signal, stylometric_signal
from scoring import combine_scores, decide

load_dotenv()

MAX_TEXT_CHARS = 20_000


def create_app() -> Flask:
    app = Flask(__name__)
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "Provenance Guard"})

    @app.post("/submit")
    @limiter.limit("10 per minute;100 per day")
    def submit():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be valid JSON."}), 400

        text = data.get("text")
        creator_id = data.get("creator_id")

        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "A non-empty text field is required."}), 400
        if len(text) > MAX_TEXT_CHARS:
            return jsonify({"error": f"Text exceeds the {MAX_TEXT_CHARS}-character limit."}), 413
        if not isinstance(creator_id, str) or not creator_id.strip():
            return jsonify({"error": "A non-empty creator_id field is required."}), 400

        text = text.strip()
        creator_id = creator_id.strip()
        content_id = str(uuid.uuid4())

        try:
            groq_result = groq_signal(text)
            stylo_result = stylometric_signal(text)
        except SignalError as exc:
            return jsonify({"error": "Detection signal failed.", "details": str(exc)}), 503

        ai_likelihood = combine_scores(groq_result["score"], stylo_result["score"])
        decision = decide(ai_likelihood)
        timestamp = utc_now()

        record = {
            "content_id": content_id,
            "creator_id": creator_id,
            "text": text,
            "created_at": timestamp,
            "attribution": decision.attribution,
            "ai_likelihood": decision.ai_likelihood,
            "confidence": decision.confidence,
            "label": decision.label,
            "status": "classified",
            "signals": {
                "groq": groq_result,
                "stylometric": stylo_result,
            },
            "appeal": None,
        }
        save_content_record(record)

        audit_event = {
            "event_type": "classification",
            "timestamp": timestamp,
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": decision.attribution,
            "ai_likelihood": decision.ai_likelihood,
            "confidence": decision.confidence,
            "groq_score": groq_result["score"],
            "stylometric_score": stylo_result["score"],
            "signals_used": ["groq_llm", "stylometric_heuristics"],
            "status": "classified",
            "label": decision.label,
        }
        append_audit_event(audit_event)

        return jsonify(
            {
                "content_id": content_id,
                "attribution": decision.attribution,
                "ai_likelihood": decision.ai_likelihood,
                "confidence": decision.confidence,
                "label": decision.label,
                "status": "classified",
                "signals": {
                    "groq_score": groq_result["score"],
                    "stylometric_score": stylo_result["score"],
                },
            }
        ), 200

    @app.post("/appeal")
    def appeal():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be valid JSON."}), 400

        content_id = data.get("content_id")
        creator_reasoning = data.get("creator_reasoning")

        if not isinstance(content_id, str) or not content_id.strip():
            return jsonify({"error": "A non-empty content_id field is required."}), 400
        if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
            return jsonify({"error": "A non-empty creator_reasoning field is required."}), 400

        content_id = content_id.strip()
        creator_reasoning = creator_reasoning.strip()
        original = get_content_record(content_id)
        if original is None:
            return jsonify({"error": "Unknown content_id."}), 404
        if original.get("status") == "under_review":
            return jsonify({"error": "An appeal is already under review for this content."}), 409

        appeal_timestamp = utc_now()
        appeal_data = {
            "creator_reasoning": creator_reasoning,
            "submitted_at": appeal_timestamp,
        }
        updated = update_content_record(
            content_id,
            {"status": "under_review", "appeal": appeal_data},
        )

        signals = original.get("signals", {})
        append_audit_event(
            {
                "event_type": "appeal",
                "timestamp": appeal_timestamp,
                "content_id": content_id,
                "creator_id": original.get("creator_id"),
                "original_attribution": original.get("attribution"),
                "original_ai_likelihood": original.get("ai_likelihood"),
                "original_confidence": original.get("confidence"),
                "groq_score": signals.get("groq", {}).get("score"),
                "stylometric_score": signals.get("stylometric", {}).get("score"),
                "appeal_reasoning": creator_reasoning,
                "status": "under_review",
            }
        )

        return jsonify(
            {
                "content_id": content_id,
                "status": updated["status"] if updated else "under_review",
                "message": "Appeal received successfully.",
            }
        ), 200

    @app.get("/log")
    def log():
        raw_limit = request.args.get("limit", "50")
        try:
            limit = max(1, min(200, int(raw_limit)))
        except ValueError:
            return jsonify({"error": "limit must be an integer."}), 400
        return jsonify({"entries": get_recent_log(limit=limit)})

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(exc: RateLimitExceeded):
        return jsonify({"error": "Rate limit exceeded.", "details": str(exc.description)}), 429

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
