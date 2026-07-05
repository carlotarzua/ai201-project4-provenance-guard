# 🛡️ Provenance Guard

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge)
![SQLite](https://img.shields.io/badge/JSON%20Audit%20Log-4B8BBE?style=for-the-badge)

Provenance Guard is a Flask backend for creative-sharing platforms. It analyzes submitted text with **two distinct signals**, combines them into an uncertainty-aware score, returns a plain-language transparency label, logs every decision, rate-limits submissions, and gives creators an appeal path.

> Important: this system estimates writing patterns. It does **not** prove who wrote a piece of content.

## Features

- `POST /submit` text attribution endpoint
- Groq LLM semantic/style signal
- Pure-Python stylometric structural signal
- Weighted multi-signal scoring
- Explicit uncertainty band
- Three reader-facing transparency labels
- `POST /appeal` workflow with `under_review` status
- Flask-Limiter abuse protection
- Structured JSON audit log
- `GET /log` evidence endpoint
- `GET /health` service check
- Pytest coverage for core flow and rate limiting

## Architecture Overview

A submission enters `POST /submit`, where the API validates `text` and `creator_id`. The same text is analyzed independently by the Groq LLM signal and the stylometric signal. Their 0–1 AI-likelihood scores are combined using a documented 65/35 weighting. The combined score is mapped to `likely_human`, `uncertain`, or `likely_ai`, then to an exact transparency label. The full decision is stored and appended to the structured audit log before JSON is returned.

An appeal enters `POST /appeal` with a `content_id` and `creator_reasoning`. The system finds the original decision, changes the status to `under_review`, preserves the original scores, saves the reasoning, and appends a new appeal event to the audit log.

The full diagram is in [`planning.md`](planning.md) under `## Architecture`.

## Detection Signals

### 1. Groq LLM signal

**What it measures:** holistic semantic and stylistic patterns, including generic transitions, repetitive explanation structure, tone uniformity, predictable phrasing, and unusually polished organization.

**Why I chose it:** these whole-passage patterns are difficult to represent with only a few formulas. The model returns a cautious AI-likelihood estimate rather than a claim of proof.

**What it misses:** formal human prose, non-native English writing, edited human work, heavily edited AI output, and short passages can all be misclassified.

### 2. Stylometric heuristic signal

**What it measures:** directly computed structure:

- sentence-length regularity,
- vocabulary repetition/diversity,
- punctuation density and variety.

**Why I chose it:** it is genuinely different from the LLM signal. The LLM is a holistic semantic/style judge; stylometrics are transparent numerical measurements.

**What it misses:** poetry, short text, intentional repetition, formal prose, and experimental writing can produce misleading patterns.

## Confidence Scoring

Both signals return an AI-likelihood score between `0.0` and `1.0`.

```text
ai_likelihood = (groq_score × 0.65) + (stylometric_score × 0.35)
```

I give Groq 65% because it evaluates the whole passage. I give stylometrics 35% because it provides an independent structural check without letting a few simple metrics dominate the decision.

### Attribution thresholds

| AI likelihood | Result |
|---|---|
| `0.00–0.30` | `likely_human` |
| `0.31–0.79` | `uncertain` |
| `0.80–1.00` | `likely_ai` |

The wide uncertain band is deliberate. A false positive against a human creator can damage attribution, so the system requires strong combined evidence before showing the AI-likely label.

### Confidence value

The API returns a separate confidence score:

```text
confidence = abs(ai_likelihood - 0.5) × 2
```

This measures how far the combined evidence is from the uncertainty midpoint. An AI likelihood of `0.51` produces confidence `0.02`; an AI likelihood of `0.95` produces confidence `0.90`. The labels therefore change meaningfully rather than flipping at `0.50`.

### How I tested meaningful variation

I compare at least four deliberately different inputs: clearly AI-like formal text, casual human-like text, formal human writing, and lightly edited AI-like text. For every case I inspect the Groq score, stylometric score, combined AI likelihood, confidence, and label separately.

Because the Groq result is an external model estimate, exact values can vary across runs. Record your real local outputs before submission. The included helper script does this automatically against the running API:

```bash
python scripts/capture_confidence_examples.py
```

It saves the real scores to `evidence/confidence_examples.json`. Then copy those values into the table below:

| Test case | Groq | Stylometric | AI likelihood | Confidence | Result |
|---|---:|---:|---:|---:|---|
| Clearly AI-like | _run locally_ | _run locally_ | _run locally_ | _run locally_ | _run locally_ |
| Casual human-like | _run locally_ | _run locally_ | _run locally_ | _run locally_ | _run locally_ |

This avoids presenting fabricated model scores as evidence.

## Transparency Labels

The exact text of all three variants is written here, as required.

| Variant | Exact label text |
|---|---|
| High-confidence AI | **"AI attribution likely: This content shows strong signals associated with AI-generated writing. This is an estimate, not proof, and the creator may appeal."** |
| High-confidence human | **"Human attribution likely: This content shows strong signals associated with human-written work. This is an estimate, not proof."** |
| Uncertain | **"Attribution uncertain: The available signals do not clearly indicate whether this content was written by a human or generated by AI. No definitive attribution should be assumed."** |

## Appeals Workflow

A creator submits:

```json
{
  "content_id": "original-content-id",
  "creator_reasoning": "I wrote this myself from personal experience."
}
```

The system then:

1. finds the original decision,
2. changes status to `under_review`,
3. stores the creator reasoning and timestamp,
4. preserves original attribution and signal scores,
5. appends a structured `appeal` event to the audit log,
6. returns confirmation.

Automated reclassification is intentionally not performed. A future human reviewer would see the original text, decision, scores, label, creator reasoning, timestamps, and current status.

## Rate Limiting

`POST /submit` is limited to:

```text
10 requests per minute; 100 requests per day
```

**Reasoning:** ten per minute lets a real creator submit several pieces during an active session without immediate friction, while slowing a simple flooding script. One hundred per day supports normal usage and demonstrations while limiting abuse and unnecessary external Groq API consumption.

Local development uses:

```text
memory://
```

A production deployment would use shared persistent rate-limit storage such as Redis.

### Test command

With the Flask server running:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text":"This is a test submission for rate limit testing purposes only.","creator_id":"ratelimit-test"}'
done
```

Expected behavior is ten accepted requests followed by HTTP `429` responses. The automated test suite verifies this behavior. A captured local test run is stored in `evidence/rate_limit_output.txt` and produced:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

## Audit Log

Runtime audit data is stored in:

```text
data/audit_log.json
```

Every classification records:

- timestamp
- content ID
- creator ID
- attribution
- AI likelihood
- confidence
- Groq score
- stylometric score
- signals used
- status
- transparency label

Appeals additionally record the creator's reasoning and original decision information.

### Three visible structured sample entries

These are **format examples**, not claims about real Groq outputs:

```json
[
  {
    "event_type": "classification",
    "timestamp": "2026-07-04T15:10:00Z",
    "content_id": "demo-1",
    "creator_id": "creator-a",
    "attribution": "likely_ai",
    "ai_likelihood": 0.87,
    "confidence": 0.74,
    "groq_score": 0.91,
    "stylometric_score": 0.80,
    "signals_used": ["groq_llm", "stylometric_heuristics"],
    "status": "classified"
  },
  {
    "event_type": "classification",
    "timestamp": "2026-07-04T15:12:00Z",
    "content_id": "demo-2",
    "creator_id": "creator-b",
    "attribution": "uncertain",
    "ai_likelihood": 0.58,
    "confidence": 0.16,
    "groq_score": 0.61,
    "stylometric_score": 0.52,
    "signals_used": ["groq_llm", "stylometric_heuristics"],
    "status": "classified"
  },
  {
    "event_type": "appeal",
    "timestamp": "2026-07-04T15:20:00Z",
    "content_id": "demo-1",
    "creator_id": "creator-a",
    "original_attribution": "likely_ai",
    "original_ai_likelihood": 0.87,
    "original_confidence": 0.74,
    "groq_score": 0.91,
    "stylometric_score": 0.80,
    "appeal_reasoning": "I wrote this myself from personal experience.",
    "status": "under_review"
  }
]
```

You can inspect real runtime entries with:

```bash
curl -s http://localhost:5000/log | python -m json.tool
```

## API Endpoints

### `GET /health`

```bash
curl -s http://localhost:5000/health | python -m json.tool
```

### `POST /submit`

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The sun dipped below the horizon, painting the sky in amber and rose.",
    "creator_id": "test-user-1"
  }' | python -m json.tool
```

Example response shape:

```json
{
  "content_id": "generated-uuid",
  "attribution": "uncertain",
  "ai_likelihood": 0.63,
  "confidence": 0.26,
  "label": "Attribution uncertain: ...",
  "status": "classified",
  "signals": {
    "groq_score": 0.70,
    "stylometric_score": 0.50
  }
}
```

### `POST /appeal`

Replace the content ID with one returned by `/submit`:

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "PASTE-CONTENT-ID-HERE",
    "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."
  }' | python -m json.tool
```

### `GET /log`

```bash
curl -s http://localhost:5000/log | python -m json.tool
```

## Setup

### 1. Clone and enter the repository

```bash
git clone YOUR_REPOSITORY_URL
cd ai201-project4-provenance-guard
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env`

```bash
cp .env.example .env
```

Then edit `.env`:

```text
GROQ_API_KEY=your_real_key_here
FLASK_DEBUG=1
```

Never commit `.env`.

### 5. Run the server

```bash
python app.py
```

Server:

```text
http://127.0.0.1:5000
```

## Tests

Run:

```bash
pytest -q
```

The tests mock the external Groq call so they do not consume API quota. They cover scoring, submission logging, appeal status updates, and rate limiting.

## Known Limitations

### Formal human writing may look AI-like

Academic or professional human writing can have uniform sentence structure, neutral tone, and polished transitions. The Groq signal may treat this as AI-like, while the stylometric signal may also increase its score because of structural regularity. This is why the AI threshold is conservative and why appeals exist.

### Short poems are structurally unstable

A poem with only a few lines does not provide enough sentences or words for stable sentence variation and vocabulary metrics. The stylometric implementation therefore pulls short-text results toward `0.5`, but the overall result can still be unreliable.

### Edited AI text may evade both signals

A human can rewrite AI-generated content to vary sentence length, punctuation, and vocabulary. That can lower both the structural and holistic AI-likelihood signals.

## Spec Reflection

**How the spec helped:** writing the exact thresholds and label text first prevented the implementation from silently turning into a binary detector. The scoring and label functions now directly reflect documented decisions.

**Where implementation diverged:** the original idea treated the combined number as both AI likelihood and confidence. During implementation I separated them. `ai_likelihood` indicates direction toward human-like or AI-like patterns, while `confidence` measures distance from the `0.5` uncertainty midpoint. This makes a human-like score such as `0.10` correctly appear high-confidence instead of low-confidence.

## AI Usage

### Instance 1 — Flask and Groq skeleton

I directed an AI tool to generate a minimal Flask structure and a standalone Groq signal based on my detection-signal specification and architecture. The initial output was revised so the model had to return strict JSON, scores were clamped to `0.0–1.0`, malformed fenced output could be parsed safely, and external failures became controlled `503` API responses instead of crashes.

### Instance 2 — Stylometric scoring review

I directed an AI tool to help translate the planned sentence variation, vocabulary diversity, and punctuation metrics into pure Python. I revised the result to reduce short-text overconfidence by pulling low-evidence stylometric scores toward `0.5`, and I kept the exact 65/35 combination from the written specification.

### Instance 3 — Appeals and audit logging

I directed an AI tool to draft the appeal flow. I revised it so the original signal scores remain preserved, duplicate under-review appeals return a conflict response, the status update is persisted, and the appeal is stored as a separate structured audit event.

## Portfolio Walkthrough Checklist

In a 2–3 minute video, show:

1. `planning.md` architecture diagram
2. server starting
3. one `/submit` request
4. returned content ID, signal scores, confidence, and label
5. `GET /log`
6. `/appeal` using the content ID
7. `GET /log` showing `under_review`
8. rate-limit test reaching `429`
9. one design decision: conservative AI threshold because false positives harm creators

## Project Structure

```text
ai201-project4-provenance-guard/
├── app.py
├── audit.py
├── detection.py
├── scoring.py
├── planning.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── audit_log.json
│   └── content_store.json
├── scripts/
│   ├── demo_requests.sh
│   └── capture_confidence_examples.py
├── evidence/
│   ├── audit_log_sample.json
│   ├── rate_limit_output.txt
│   └── test_results.txt
├── pytest.ini
└── tests/
    ├── test_api.py
    └── test_scoring.py
```
