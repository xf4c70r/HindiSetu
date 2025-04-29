#!/usr/bin/env bash
# exit on error
set -o errexit

# Set development environment
export NODE_ENV=development

# Increase Node.js memory limit
export NODE_OPTIONS="--max-old-space-size=4096"

# Install dependencies
npm install

# Start development server
npm run start 