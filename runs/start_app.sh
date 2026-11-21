#!/bin/bash
# Live app: distilled 9B assistant + independent checker Qwen3.8-27B (self-hosted, OpenAI-compatible endpoints from runs/.student_env and runs/.verify_env)
cd /Users/harsh223/Desktop/gdg; pkill -f "uvicorn app.main:app --port 8080"; sleep 1
[ -f runs/.admin_token ] || (umask 077; python3 -c "import secrets;print(secrets.token_hex(16))" > runs/.admin_token)
export ADMIN_TOKEN=$(cat runs/.admin_token)
set -a; . runs/.student_env; [ -f runs/.verify_env ] && . runs/.verify_env; set +a
nohup .venv/bin/uvicorn app.main:app --port 8080 > runs/logs/app.log 2>&1 &
for i in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8080/login && break; sleep 2; done; echo "app up on :8080"
