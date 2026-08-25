#!/usr/bin/env bash
# ==============================================================================
# Push to PRD - Prediction Engine
# Pushes local commits to GitHub and triggers automatic remote deployment
# ==============================================================================

set -e

SERVER_USER="johansiedberg"
SERVER_IP="192.168.86.35"
REMOTE_PATH="/home/johansiedberg/Projects/Prediction_Engine"

echo "----------------------------------------------------------------"
echo "⚽ Push to PRD: Prediction Engine"
echo "----------------------------------------------------------------"

# 1. Check for uncommitted local changes
if [[ -n $(git status --porcelain) ]]; then
    echo "⚠️  You have uncommitted local changes in Prediction_Engine:"
    git status -s
    read -p "Do you want to commit all changes now? (y/N): " -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        read -p "Enter commit message: " -r msg
        if [[ -z "$msg" ]]; then
            msg="chore: update Prediction Engine for production release"
        fi
        git add .
        git commit -m "$msg"
    else
        echo "❌ Aborting Push to PRD to avoid losing uncommitted changes."
        exit 1
    fi
fi

# 2. Push to GitHub
echo "🚀 Pushing latest commits to GitHub (origin/main)..."
git push origin main

# 3. Trigger remote deployment over SSH
echo "🌐 Connecting to server ($SERVER_IP) to execute deployment..."
ssh -t "${SERVER_USER}@${SERVER_IP}" "cd ${REMOTE_PATH} && ./deploy.sh"

echo "----------------------------------------------------------------"
echo "✅ Push to PRD Complete! Prediction Engine is live on $SERVER_IP."
echo "----------------------------------------------------------------"
