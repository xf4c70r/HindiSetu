# #!/usr/bin/env bash
# # exit on error
# set -o errexit

# # Set development environment
# export NODE_ENV=development

# # Increase Node.js memory limit
# export NODE_OPTIONS="--max-old-space-size=4096"

# # Install dependencies
# npm install

# # Start development server
# npm run start 

#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
npm install

# Install serve globally
npm install -g serve

# Ensure PORT is set
export PORT="${PORT:-3000}"

# Copy serve.json to build directory
cp serve.json build/

# Serve the built application using serve with config
cd build && serve -s . --listen $PORT 