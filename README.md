# 🛡️ Provenance Guard

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge)
![Audit Log](https://img.shields.io/badge/Audit%20Log-JSON-4B8BBE?style=for-the-badge)

Provenance Guard is a Flask backend for creative-sharing platforms. It analyzes submitted text with **two distinct detection signals**, combines them into an uncertainty-aware score, returns a plain-language transparency label, logs every decision, rate-limits submissions, and gives creators a way to appeal a classification.

> **Important:** this system estimates writing patterns. It does **not** prove who wrote a piece of content.

---

## Features

- `POST /submit` text attribution endpoint
- Groq LLM semantic and style signal
- Pure-Python stylometric structural signal
- Weighted multi-signal scoring
- Explicit uncertainty band
- Separate AI-likelihood and confidence values
- Three reader-facing transparency labels
- `POST /appeal` workflow with `under_review` status
- Flask-Limiter abuse protection
- Structured JSON audit log
- `GET /log` evidence endpoint
- `GET /health` service check
- Pytest coverage for scoring, submission flow, appeals, logging, and rate limiting

---

## Architecture Overview

A submission enters `POST /submit`, where the API validates `text` and `creator_id`. The same text is analyzed independently by the Groq LLM signal and the stylometric signal. Their `0.0–1.0` AI-likelihood scores are combined using a documented `65/35` weighting. The combined score is mapped to `likely_human`, `uncertain`, or `likely_ai`, then converted into the exact transparency label shown to the user. The complete decision is saved and appended to the structured audit log before JSON is returned.

An appeal enters `POST /appeal` with a `content_id` and `creator_reasoning`. The system finds the original decision, changes the content status to `under_review`, preserves the original scores, stores the creator reasoning, and appends a separate appeal event to the audit log.

The full architecture diagram is in [`planning.md`](planning.md) under `## Architecture`.

## Detection Signals

### 1. Groq LLM Signal

**What it measures:** holistic semantic and stylistic patterns, including generic transitions, repetitive explanation structure, tone uniformity, predictable phrasing, and unusually polished organization.

**Why I chose it:** these whole-passage patterns are difficult to represent with only a few formulas. The model returns a cautious AI-likelihood estimate rather than a claim of proof.

**What it misses:** formal human prose, non-native English writing, heavily edited human work, heavily edited AI output, and short passages can all be misclassified.

### 2. Stylometric Heuristic Signal

**What it measures:** directly computed structural properties of the text:

- sentence-length regularity
- vocabulary repetition and diversity
- punctuation density and variety

**Why I chose it:** it is genuinely different from the LLM signal. The LLM acts as a holistic semantic and style judge, while stylometrics use transparent numerical measurements.

**What it misses:** poetry, very short text, intentional repetition, formal prose, and experimental writing can produce misleading patterns.

## Confidence Scoring

Both signals return an AI-likelihood score between `0.0` and `1.0`.

```text
ai_likelihood = (groq_score × 0.65) + (stylometric_score × 0.35)
```

I give Groq `65%` because it evaluates the whole passage. I give stylometrics `35%` because it provides an independent structural check without allowing a few simple metrics to dominate the decision.

### Attribution Thresholds

| AI likelihood | Result |
|---|---|
| `0.00–0.30` | `likely_human` |
| `0.31–0.79` | `uncertain` |
| `0.80–1.00` | `likely_ai` |

The wide uncertain band is deliberate. A false positive against a human creator can damage attribution, so the system requires strong combined evidence before showing the AI-likely label.

### Separate Confidence Value

The API returns a separate confidence score:

```text
confidence = abs(ai_likelihood - 0.5) × 2
```

This measures how far the combined evidence is from the uncertainty midpoint.

Examples:

- AI likelihood `0.51` → confidence `0.02`
- AI likelihood `0.95` → confidence `0.90`
- AI likelihood `0.10` → confidence `0.80`

This separation is important because a low AI-likelihood score can still be a high-confidence human-like result.

### How I Tested Meaningful Variation

I tested deliberately different writing styles and inspected the Groq score, stylometric score, combined AI likelihood, confidence, and final attribution separately.

| Test case | Groq | Stylometric | AI likelihood | Confidence | Result |
|---|---:|---:|---:|---:|---|
| Strong repetitive AI-like text | `1.0000` | `0.9894` | `0.9963` | `0.9926` | `likely_ai` |
| Casual human-like text | `0.2000` | `0.3386` | `0.2485` | `0.5030` | `likely_human` |
| Formal borderline text | `0.8000` | `0.4550` | `0.6793` | `0.3586` | `uncertain` |

These results show meaningful variation across different writing styles.

The strong repetitive AI-like example caused both signals to agree strongly, producing an AI likelihood of `0.9963` and the `likely_ai` label.

The casual human-like example produced much lower scores from both signals, resulting in an AI likelihood of `0.2485` and the `likely_human` label.

The formal borderline example demonstrates genuine uncertainty. Groq returned `0.8000`, while the stylometric signal returned only `0.4550`. Because the two independent signals disagreed, the combined AI likelihood was `0.6793`, which remained inside the uncertain range rather than forcing a binary classification.

This testing confirmed that the system can reach all three attribution outcomes and that disagreement between signals is represented as uncertainty.

## Transparency Labels

The exact text of all three variants is written below.

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
4. preserves the original attribution and signal scores,
5. appends a structured `appeal` event to the audit log,
6. returns confirmation.

Automated reclassification is intentionally not performed. A future human reviewer would see the original text, decision, individual scores, combined score, label, creator reasoning, timestamps, and current status.

### Real Appeal Test

A real local appeal request returned:

```json
{
  "content_id": "8510f963-3ad5-4de8-8ce8-597101f2b802",
  "message": "Appeal received successfully.",
  "status": "under_review"
}
```

The audit log then recorded the creator reasoning and the updated `under_review` status.

## Rate Limiting

`POST /submit` is limited to:

```text
10 requests per minute; 100 requests per day
```

**Reasoning:** ten requests per minute lets a real creator submit several pieces during an active session without immediate friction, while slowing a simple flooding script. One hundred requests per day supports normal usage and demonstrations while limiting abuse and unnecessary Groq API consumption.

Local development uses:

```text
memory://
```

A production deployment would use shared persistent rate-limit storage such as Redis.

### Rate-Limit Test Command

With the Flask server running:

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://127.0.0.1:5000/submit \
    -H "Content-Type: application/json" \
    -d '{
      "text": "This is a test submission for rate limit testing purposes only.",
      "creator_id": "ratelimit-test"
    }'
done
```

### Real Rate-Limit Evidence

The local test produced:

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

The first ten requests succeeded with HTTP `200`. Requests eleven and twelve were blocked with HTTP `429`, confirming that the minute limit is active.

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

Appeals additionally record:

- creator reasoning
- original attribution
- original AI likelihood
- original confidence
- original signal scores
- `under_review` status

### Real Structured Audit Log Entries

The following entries were generated by the running system during local end-to-end testing:

```json
[
  {
    "ai_likelihood": 0.6793,
    "attribution": "uncertain",
    "confidence": 0.3586,
    "content_id": "8510f963-3ad5-4de8-8ce8-597101f2b802",
    "creator_id": "test-user-1",
    "event_type": "classification",
    "groq_score": 0.8,
    "label": "Attribution uncertain: The available signals do not clearly indicate whether this content was written by a human or generated by AI. No definitive attribution should be assumed.",
    "signals_used": [
      "groq_llm",
      "stylometric_heuristics"
    ],
    "status": "classified",
    "stylometric_score": 0.455,
    "timestamp": "2026-07-05T16:59:19.873592Z"
  },
  {
    "appeal_reasoning": "I wrote this myself and believe the classification is incorrect.",
    "content_id": "8510f963-3ad5-4de8-8ce8-597101f2b802",
    "creator_id": "test-user-1",
    "event_type": "appeal",
    "groq_score": 0.8,
    "original_ai_likelihood": 0.6793,
    "original_attribution": "uncertain",
    "original_confidence": 0.3586,
    "status": "under_review",
    "stylometric_score": 0.455,
    "timestamp": "2026-07-05T17:01:37.738117Z"
  },
  {
    "ai_likelihood": 0.2485,
    "attribution": "likely_human",
    "confidence": 0.503,
    "content_id": "b8b6bfb5-e929-4fb8-9a4a-a59135e9f98d",
    "creator_id": "test-user-2",
    "event_type": "classification",
    "groq_score": 0.2,
    "label": "Human attribution likely: This content shows strong signals associated with human-written work. This is an estimate, not proof.",
    "signals_used": [
      "groq_llm",
      "stylometric_heuristics"
    ],
    "status": "classified",
    "stylometric_score": 0.3386,
    "timestamp": "2026-07-05T17:17:28.719818Z"
  },
  {
    "ai_likelihood": 0.9963,
    "attribution": "likely_ai",
    "confidence": 0.9926,
    "content_id": "57904050-b124-4ba1-b248-14d0329cd508",
    "creator_id": "test-user-4",
    "event_type": "classification",
    "groq_score": 1.0,
    "label": "AI attribution likely: This content shows strong signals associated with AI-generated writing. This is an estimate, not proof, and the creator may appeal.",
    "signals_used": [
      "groq_llm",
      "stylometric_heuristics"
    ],
    "status": "classified",
    "stylometric_score": 0.9894,
    "timestamp": "2026-07-05T17:23:20.923392Z"
  }
]
```

These entries demonstrate:

- an `uncertain` classification
- a creator appeal with status changed to `under_review`
- a `likely_human` classification
- a `likely_ai` classification
- both individual signal scores recorded for every classification

You can inspect runtime entries with:

```bash
curl -s http://127.0.0.1:5000/log | python3 -m json.tool
```

## API Endpoints

### `GET /health`

Checks whether the service is running.

```bash
curl -s http://127.0.0.1:5000/health | python3 -m json.tool
```

Example response:

```json
{
  "service": "Provenance Guard",
  "status": "ok"
}
```

### `POST /submit`

Submits text for attribution analysis.

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The sun dipped below the horizon, painting the sky in amber and rose.",
    "creator_id": "test-user-1"
  }' | python3 -m json.tool
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
curl -s -X POST http://127.0.0.1:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "PASTE-CONTENT-ID-HERE",
    "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."
  }' | python3 -m json.tool
```

Example response:

```json
{
  "content_id": "PASTE-CONTENT-ID-HERE",
  "message": "Appeal received successfully.",
  "status": "under_review"
}
```

### `GET /log`

Returns recent structured audit-log entries:

```bash
curl -s http://127.0.0.1:5000/log | python3 -m json.tool
```

An optional `limit` query parameter is supported:

```bash
curl -s "http://127.0.0.1:5000/log?limit=10" | python3 -m json.tool
```

## Setup

### 1. Clone and Enter the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd ai201-project4-provenance-guard
```

### 2. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

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

### 5. Run the Server

```bash
python3 app.py
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

Real local test result:

```text
.......                                                                  [100%]
7 passed in 0.12s
```

The tests mock the external Groq call so they do not consume API quota. They cover core scoring behavior, submission flow, audit logging, appeal status updates, all three label variants, and rate limiting.

## Known Limitations

### Formal Human Writing May Look AI-Like

Academic or professional human writing can have uniform sentence structure, neutral tone, and polished transitions. The Groq signal may treat this as AI-like, while the stylometric signal may also increase its score because of structural regularity. This is why the AI threshold is conservative and why appeals exist.

### Short Poems Are Structurally Unstable

A poem with only a few lines does not provide enough sentences or words for stable sentence variation and vocabulary metrics. The stylometric implementation pulls short-text results toward `0.5`, but the overall result can still be unreliable.

### Edited AI Text May Evade Both Signals

A human can rewrite AI-generated content to vary sentence length, punctuation, vocabulary, and tone. That can lower both the structural and holistic AI-likelihood signals.

### Non-Native English Writing May Be Misclassified

A non-native English speaker may intentionally use formal vocabulary, repeated sentence patterns, or textbook-style transitions. Both signals may interpret those features as AI-like even when the work is original.

## Spec Reflection

**How the spec helped:** writing the exact thresholds and label text before implementation prevented the system from silently turning into a binary detector. The scoring and label functions directly reflect documented decisions from `planning.md`.

**Where implementation diverged:** the original idea treated the combined number as both AI likelihood and confidence. During implementation, I separated them. `ai_likelihood` indicates direction toward human-like or AI-like patterns, while `confidence` measures distance from the `0.5` uncertainty midpoint. This makes a human-like score such as `0.10` correctly appear high-confidence instead of low-confidence.

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

## Final Notes

Provenance Guard is designed to communicate uncertainty rather than claim perfect AI detection. The system combines two independent signals, uses conservative thresholds, presents plain-language labels, records decisions for auditability, limits abuse, and gives creators a clear appeal path.
