#!/bin/bash
set -e
cd ~/Downloads/urr-stats

echo "=== Initialising git ==="
git init
git add .
git commit -m "feat: URR citation stats server v0.1.0" 2>/dev/null || git commit --allow-empty -m "feat: URR citation stats server v0.1.0"

echo ""
if command -v gh &>/dev/null; then
  echo "=== Creating GitHub repo via gh CLI ==="
  gh repo create urr-stats --public --source=. --remote=origin --push
  echo ""
  echo "✓ Pushed to https://github.com/ssingh11/urr-stats"
else
  echo "gh CLI not found — installing via Homebrew..."
  brew install gh
  gh auth login
  gh repo create urr-stats --public --source=. --remote=origin --push
  echo "✓ Pushed to https://github.com/ssingh11/urr-stats"
fi

echo ""
echo "=== Next: Deploy to Render ==="
echo "1. Go to https://render.com → New → Web Service"
echo "2. Connect GitHub → pick 'urr-stats' repo"
echo "3. Render reads render.yaml automatically → click Deploy"
echo "4. Free URL: https://urr-stats.onrender.com"
echo ""
echo "Done!"
