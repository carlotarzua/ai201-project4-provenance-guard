#!/usr/bin/env python3
"""Submit two examples to a running local server and save their real scores."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"
OUTPUT = Path("evidence/confidence_examples.json")

EXAMPLES = [
    {
        "name": "clearly_ai_like",
        "creator_id": "readme-example-ai",
        "text": (
            "Artificial intelligence represents a transformative paradigm shift in modern society. "
            "It is important to note that while the benefits of AI are numerous, it is equally "
            "essential to consider the ethical implications. Furthermore, stakeholders across "
            "various sectors must collaborate to ensure responsible deployment."
        ),
    },
    {
        "name": "casual_human_like",
        "creator_id": "readme-example-human",
        "text": (
            "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
            "the broth was fine but they put WAY too much sodium in it and i was thirsty for like "
            "three hours after. my friend got the spicy version and said it was better."
        ),
    },
]


def submit(example: dict) -> dict:
    payload = json.dumps({"text": example["text"], "creator_id": example["creator_id"]}).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/submit",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    return {
        "name": example["name"],
        "text": example["text"],
        "attribution": body["attribution"],
        "ai_likelihood": body["ai_likelihood"],
        "confidence": body["confidence"],
        "groq_score": body["signals"]["groq_score"],
        "stylometric_score": body["signals"]["stylometric_score"],
        "label": body["label"],
    }


def main() -> None:
    results = [submit(example) for example in EXAMPLES]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"\nSaved real local results to {OUTPUT}")


if __name__ == "__main__":
    main()
