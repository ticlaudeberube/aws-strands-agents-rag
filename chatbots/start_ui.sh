#!/bin/bash
# Start the React chatbot UI

echo "==========================================="
echo "Starting React Chatbot UI"
echo "==========================================="

# Check if API server is running
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "❌ API server is not running on port 8001"
    echo "   Please start the API server first:"
    echo "   python api_server.py"
    exit 1
fi

echo "✅ API server is running"

# Navigate to React chatbot directory
cd "$(dirname "$0")/react-chatbot" ||  exit 1

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Start the development server
echo ""
echo "Starting React development server..."
echo "==========================================="
npm start
