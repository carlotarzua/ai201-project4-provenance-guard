#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"

echo "1) Health"
curl -s "$BASE_URL/health" | python -m json.tool

echo
echo "2) Submit"
SUBMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/submit" \
  -H "Content-Type: application/json" \
  -d '{"text":"The sun dipped below the horizon, painting the sky in amber and rose. I sat on the porch with cold coffee and watched the street go quiet.","creator_id":"demo-user-1"}')

echo "$SUBMIT_RESPONSE" | python -m json.tool
CONTENT_ID=$(python -c 'import json,sys; print(json.load(sys.stdin)["content_id"])' <<< "$SUBMIT_RESPONSE")

echo
echo "3) Appeal"
curl -s -X POST "$BASE_URL/appeal" \
  -H "Content-Type: application/json" \
  -d "{\"content_id\":\"$CONTENT_ID\",\"creator_reasoning\":\"I wrote this myself from personal experience and can provide drafts.\"}" \
  | python -m json.tool

echo
echo "4) Audit log"
curl -s "$BASE_URL/log" | python -m json.tool
