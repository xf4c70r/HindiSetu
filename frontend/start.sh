#!/usr/bin/env bash
# exit on error
set -o errexit

# Increase Node.js memory limit
export NODE_OPTIONS="--max-old-space-size=4096"

# Set environment variables
export NODE_ENV="${NODE_ENV:-production}"
export PORT="${PORT:-3000}"

# If REACT_APP_API_URL is not set and we're in production, set a default
if [ "$NODE_ENV" = "production" ] && [ -z "$REACT_APP_API_URL" ]; then
  export REACT_APP_API_URL="https://hindisetu-api.onrender.com"
fi

# Install dependencies
npm install

# Install serve globally
npm install -g serve

# Copy serve.json to build directory
cp serve.json build/

if [ "$NODE_ENV" = "production" ]; then
  # Build and serve for production
  npm run build
  serve -s build
else
  # Start development server
  npm run start
fi 