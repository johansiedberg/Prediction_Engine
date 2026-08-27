#!/usr/bin/env bash
# ==============================================================================
# Prediction Engine - Production Deployment Script
# Target Server: johansiedberg@192.168.86.35
# Path: /home/johansiedberg/Projects/Prediction_Engine
# ==============================================================================

set -e

echo "🚀 [1/5] Pulling latest changes from origin/main..."
git pull origin main

echo "📦 [2/5] Applying database migrations..."
./venv/bin/python manage.py migrate

echo "📁 [3/5] Collecting static assets..."
./venv/bin/python manage.py collectstatic --noinput

echo "🔄 [4/5] Terminating stale Prediction Engine instances..."
pkill -9 -f "runserver.*8028" || true
pkill -9 -f "runserver.*8029" || true
pkill -9 -f "runserver_admin" || true
pkill -9 -f "manage.py runserver" || true
sleep 2

echo "⚡ [5/5] Starting background services (Player: 8028, Engine Admin: 8029)..."
nohup ./venv/bin/python manage.py runserver 127.0.0.1:8028 > runserver_player.log 2>&1 &
nohup ./venv/bin/python manage.py runserver_admin > runserver_admin.log 2>&1 &
sleep 2

# Post-Deployment Health Checks
echo "----------------------------------------------------------------"
echo "🩺 Running Service Health Checks..."
PLAYER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8028/ || echo "ERR")
ADMIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8029/ || echo "ERR")

if [[ "$PLAYER_STATUS" =~ ^(200|301|302)$ ]]; then
    echo "  ✅ Player Service (Port 8028 / Proxy 2028): Healthy (HTTP $PLAYER_STATUS)"
else
    echo "  ⚠️ Player Service (Port 8028): Warning! HTTP status $PLAYER_STATUS. Check runserver_player.log"
fi

if [[ "$ADMIN_STATUS" =~ ^(200|301|302)$ ]]; then
    echo "  ✅ Engine Admin Service (Port 8029 / Proxy 2029): Healthy (HTTP $ADMIN_STATUS)"
else
    echo "  ⚠️ Engine Admin Service (Port 8029): Warning! HTTP status $ADMIN_STATUS. Check runserver_admin.log"
fi

echo "----------------------------------------------------------------"
echo "✅ Deployment complete! Prediction Engine is active (Ports 2028 / 2029 via Caddy)."

