#!/usr/bin/env bash
# exit on error
set -o errexit

# Set production environment
export NODE_ENV=production

# Increase Node.js memory limit for build
export NODE_OPTIONS="--max-old-space-size=4096"

# Install dependencies
npm install

# Install serve globally
npm install -g serve

# Build the application
npm run build

# Create serve.json in the build directory
cat > build/serve.json << EOL
{
  "rewrites": [
    { "source": "/healthz", "destination": "/index.html" },
    { "source": "/**", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/healthz",
      "headers": [
        { "key": "Content-Type", "value": "text/plain" }
      ]
    }
  ]
}
EOL

# Start the production server
serve -s build --listen ${PORT:-3000}

# Output build success
echo "Frontend build completed successfully!" 