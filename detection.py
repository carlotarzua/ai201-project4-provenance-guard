"""Detection signals for Provenance Guard.

Signal 1: Groq LLM assessment (semantic / holistic).
Signal 2: Pure-Python stylometric heuristics (structural / statistical).
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
from collections import Counter
from typing import Any



class SignalError(RuntimeError):
    """Raised when a detection signal cannot produce a valid result."""


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating fenced model output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise SignalError("Groq response did not contain valid JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise SignalError("Groq response contained malformed JSON.") from exc

    if not isinstance(parsed, dict):
        raise SignalError("Groq response JSON must be an object.")
    return parsed


def groq_signal(text: str) -> dict[str, Any]:
    """Return an AI-likelihood score from Groq in the range 0..1.

    The model is asked for a probabilistic style assessment, not a claim of proof.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SignalError(
            "GROQ_API_KEY is missing. Copy .env.example to .env and add your key."
        )

    try:
        from groq import Groq
    except ImportError as exc:
        raise SignalError("The groq package is not installed. Run pip install -r requirements.txt.") from exc

    client = Groq(api_key=api_key)
    system_prompt = (
        "You are one signal in a content provenance system. Assess whether the "
        "submitted text exhibits patterns associated with AI-generated writing. "
        "Do not claim certainty or authorship proof. Return ONLY valid JSON with "
        "two keys: ai_score (number 0.0 to 1.0) and reasoning (brief string). "
        "Use 0.0 for strongly human-like style, 0.5 for genuinely mixed/uncertain, "
        "and 1.0 for strongly AI-like style. Consider semantic organization, "
        "generic transitions, repetitiveness, tone uniformity, and phrasing, while "
        "remaining cautious about formal human and non-native writing."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=220,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this text:\n\n{text}"},
            ],
        )
    except Exception as exc:  # network/client errors are surfaced as a controlled API error
        raise SignalError(f"Groq request failed: {exc}") from exc

    content = response.choices[0].message.content or ""
    parsed = _extract_json_object(content)

    try:
        score = _clamp(float(parsed["ai_score"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise SignalError("Groq response is missing a numeric ai_score.") from exc

    reasoning = str(parsed.get("reasoning", "No reasoning returned.")).strip()
    return {"score": round(score, 4), "reasoning": reasoning}


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", text.lower())


def stylometric_signal(text: str) -> dict[str, Any]:
    """Return a structural AI-likelihood score and transparent metrics.

    This is intentionally a lightweight heuristic, not an authorship detector.
    It measures properties different from the LLM signal.
    """
    words = _words(text)
    sentences = _split_sentences(text)

    if not words:
        raise SignalError("Text does not contain analyzable words.")

    sentence_lengths = [len(_words(sentence)) for sentence in sentences]
    sentence_lengths = [n for n in sentence_lengths if n > 0]

    # Metric 1: sentence regularity. Low coefficient of variation => more regular.
    if len(sentence_lengths) >= 2 and statistics.mean(sentence_lengths) > 0:
        mean_len = statistics.mean(sentence_lengths)
        stdev_len = statistics.pstdev(sentence_lengths)
        coefficient_of_variation = stdev_len / mean_len
        sentence_regularity = 1.0 - _clamp(coefficient_of_variation / 0.85)
    else:
        coefficient_of_variation = 0.0
        sentence_regularity = 0.5  # too little evidence

    # Metric 2: vocabulary repetition. Adjust TTR to reduce short-text instability.
    unique_words = len(set(words))
    raw_ttr = unique_words / len(words)
    length_factor = min(1.0, len(words) / 120.0)
    adjusted_ttr = (raw_ttr * length_factor) + (0.65 * (1.0 - length_factor))
    vocabulary_repetition = _clamp((0.72 - adjusted_ttr) / 0.32)

    # Metric 3: punctuation regularity. Low variety and moderate density lean AI-like.
    punct = re.findall(r"[,.!?;:—\-]", text)
    punct_density = len(punct) / max(1, len(words))
    punct_counts = Counter(punct)
    punctuation_variety = len(punct_counts) / 8.0
    density_target = 0.14
    density_closeness = 1.0 - _clamp(abs(punct_density - density_target) / 0.20)
    punctuation_regularity = _clamp(0.65 * density_closeness + 0.35 * (1.0 - punctuation_variety))

    # Short texts are inherently uncertain; pull score toward 0.5.
    raw_score = (
        0.45 * sentence_regularity
        + 0.35 * vocabulary_repetition
        + 0.20 * punctuation_regularity
    )
    evidence_strength = min(1.0, len(words) / 80.0)
    score = 0.5 + (raw_score - 0.5) * evidence_strength
    score = _clamp(score)

    return {
        "score": round(score, 4),
        "metrics": {
            "word_count": len(words),
            "sentence_count": len(sentence_lengths),
            "sentence_length_cv": round(coefficient_of_variation, 4),
            "sentence_regularity": round(sentence_regularity, 4),
            "raw_type_token_ratio": round(raw_ttr, 4),
            "adjusted_type_token_ratio": round(adjusted_ttr, 4),
            "vocabulary_repetition": round(vocabulary_repetition, 4),
            "punctuation_density": round(punct_density, 4),
            "punctuation_regularity": round(punctuation_regularity, 4),
        },
    }
