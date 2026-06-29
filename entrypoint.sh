#!/bin/sh
set -e

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
MODEL_PATH="swear_persian/models/model.pkl"
DATASET_PATH="swear_persian/dataset/dataset.json"

# ── Wait for Redis ────────────────────────────────────────────────────────────
echo "Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
until python -c "
import redis, sys
try:
    r = redis.StrictRedis(host='${REDIS_HOST}', port=${REDIS_PORT}, socket_connect_timeout=2)
    r.ping()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "Redis is ready."

# ── Train model on first run ──────────────────────────────────────────────────
if [ ! -f "$MODEL_PATH" ]; then
    echo "First run: training model (takes ~3 minutes)..."
    python -c "
import os
from swear_persian.swear_detector import PersianSwearDetector
os.makedirs('swear_persian/models', exist_ok=True)
d = PersianSwearDetector()
d.train_model('${DATASET_PATH}')
d.save_model('${MODEL_PATH}')
print('Model trained and saved.')
"
else
    echo "Model already exists, skipping training."
fi

# ── Database migrations ───────────────────────────────────────────────────────
echo "Running migrations..."
python manage.py migrate --noinput

# ── Start server ──────────────────────────────────────────────────────────────
echo "Starting server on 0.0.0.0:8000..."
exec gunicorn FlyTodayCommentReview.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --log-level info \
    --access-logfile -
