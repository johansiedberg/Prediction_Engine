#!/usr/bin/env bash
# ==============================================================================
# Prediction Engine - Production Deployment Script
# Target Server: johansiedberg@192.168.86.35
# Path: /home/johansiedberg/Projects/Prediction_Engine
# ==============================================================================

set -e

echo "🚀 [1/4] Pulling latest changes from origin/main..."
git pull origin main

echo "📦 [2/4] Applying database migrations..."
./venv/bin/python manage.py migrate

echo "📁 [3/4] Collecting static assets..."
./venv/bin/python manage.py collectstatic --noinput

echo "🔄 [4/4] Restarting Prediction Engine services (Player :2028 & Engine Admin :2029)..."
pkill -f "runserver.*2028" || true
pkill -f "runserver.*2029" || true
pkill -f "runserver_admin" || true
sleep 1
nohup ./venv/bin/python manage.py runserver 127.0.0.1:2028 > runserver_player.log 2>&1 &
nohup ./venv/bin/python manage.py runserver_admin > runserver_admin.log 2>&1 &

echo "✅ Deployment complete! Prediction Engine is running on ports 2028 (Player) & 2029 (Engine Admin)."
