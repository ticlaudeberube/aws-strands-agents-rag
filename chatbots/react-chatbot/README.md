# Milvus RAG Chatbot (React)

A self-contained React chatbot interface for the Milvus RAG system with real-time response streaming.

## Features

✨ **Modern UI**
- Beautiful gradient design with smooth animations
- Responsive layout (works on desktop and tablet)
- Dark/light message bubbles for clarity
- Source badges: ⚡ CACHED (default) • 🔍 KB (green) • 🌐 Web (blue)

🚀 **Performance**
- Lightweight React app
- Efficient message rendering
- API status indicator with auto-reconnect
- Real-time streaming responses (2-3s perceived latency)

💬 **Interactive Features**
- **Live response streaming** - answers appear word-by-word
- **Web search mode** - 🌐 button for web-only search (when enabled)
- **Cache bypass** - 🚫 button to force fresh KB queries
- **Source display** - Clickable links with relevance scores
- Animated streaming indicator with bouncing dots
- Response time metrics for each message
- Clear chat history button
- Auto-scroll to latest message

🔌 **Integration**
- OpenAI-compatible API (`/v1/chat/completions`)
- Server-Sent Events (SSE) for streaming
- Automatic API health checks every 5 seconds
- Connects to `http://localhost:8000` by default

## Streaming Implementation

The chatbot now uses **real-time streaming** to display responses as they are generated:

```
User: "What is Milvus?"
│
├─ [0.5s] Context retrieval
├─ [2-3s] First chunk arrives → "Milvus is an open-source..." (streaming indicator active)
├─ The message grows in real-time as chunks arrive
└─ [8-15s] Response complete (timing info displayed)
```

### How It Works

1. **User sends question** → "What is Milvus?"
2. **Server processes** → Retrieves context from Milvus (0.5s)
3. **First chunk arrives** → Client receives initial answer text (2-3s)
4. **Streaming continues** → Answer words appear progressively
5. **Response completes** → Message shows response time

### Visual Feedback

- **Streaming indicator**: Animated bouncing dots appear while response is being generated
- **Response time**: Displays "⏱️ Response time: X.XXs" after completion
- **Smooth scroll**: Auto-scrolls to keep latest message in view

## Setup

### Prerequisites
- Node.js 14+ installed
- API server running on `http://localhost:8000` (with streaming support)

### Installation

```bash
cd react-chatbot
npm install
```

### Running

```bash
npm start
```

Or use the helper script from project root:
```bash
./chatbots/build.sh dev
```

The app will open at `http://localhost:3000`

**Make sure the API server is running:**
```bash
# From the project root
python api_server.py
```

## UI Controls

### Header Buttons

| Button | Icon | Function |
|--------|------|----------|
| **API Status** | 🟢 / 🔴 | Shows connection status (auto-reconnects) |
| **Cache Toggle** | 💾 / 🚫 | Toggle response caching (🚫 = bypass cache for fresh queries) |

### Message Input Buttons

| Button | Icon | Function |
|--------|------|----------|
| **Web Search** | 🌐 | Force web-only search (requires `ENABLE_WEB_SEARCH_SUPPLEMENT=true`) |
| **Send** | ➤ | Send message (or press Enter) |

### Source Badges

Responses show badges indicating the source type:

| Badge | Color | Meaning |
|-------|-------|---------|
| ⚡ CACHED | Gray | Answer retrieved from cache (<50ms) |
| 🔍 KB | Green | Knowledge base search (1-2s) |
| 🌐 Web | Blue | Web search results (3-6s) |

### Cached Responses

- View list of popular cached questions
- Click to instantly load cached answer
- Managed by semantic similarity search

## Configuration (Local vs Serverless)

The same source serves both modes; which environment variables you set decides
the behavior. The resolution logic lives in `src/config/api.js`.

### Environment variables

| Variable | Mode | Purpose |
|----------|------|---------|
| `REACT_APP_API_HOST` | Local | API host for local dev (default `localhost`) |
| `REACT_APP_API_PORT` | Local | API port for local dev (default `8000`) |
| `REACT_APP_API_URL` | Serverless | Full HTTPS API Gateway base URL. When set, used **verbatim** and the localhost host/port fallback is ignored (Requirement 8.4) |
| `REACT_APP_AUTH_ENABLED` | Serverless | Set `true` to force Cognito auth on. Auth is also auto-enabled when a user pool id is present |
| `REACT_APP_USER_POOL_ID` | Serverless | Cognito User Pool id |
| `REACT_APP_USER_POOL_CLIENT_ID` | Serverless | Cognito User Pool app client id |
| `REACT_APP_AWS_REGION` | Serverless | AWS region of the user pool |

### Local mode (default)

Leave the serverless variables unset. The app builds `http://${REACT_APP_API_HOST}:${REACT_APP_API_PORT}`
(defaults to `http://localhost:8000`) and runs with **no authentication** —
exactly as before.

### Serverless mode

Set `REACT_APP_API_URL` and the Cognito variables (or `REACT_APP_AUTH_ENABLED=true`).
In this mode:

- Sign-in uses **AWS Amplify Auth** against the Cognito user pool.
- The JWT access token is held **in memory only** (never `localStorage` /
  `sessionStorage`) to prevent XSS token theft (Requirement 7.4). See
  `src/auth/tokenStore.js`.
- Requests to `/chat` carry `Authorization: Bearer <token>` via
  `src/auth/authFetch.js`.
- On an expired/invalid token (HTTP 401) the app silently refreshes using the
  Cognito refresh token and retries once; if the refresh token is also invalid
  or absent, the user is redirected to the Cognito sign-in page (Requirement 7.5).

Auth code is isolated under `src/auth/` and the `aws-amplify` SDK is loaded
dynamically, so it is tree-shakeable and does not run in local mode.

> **Note:** serverless builds must not contain hardcoded `localhost` references
> (Property 24). The only `localhost` default lives in the local-dev branch of
> `src/config/api.js`, which is never reached when `REACT_APP_API_URL` is set.

## Deployment

This React app can be deployed in multiple ways:
- **Local Development**: `npm start` (development server)
- **Docker**: Multi-stage build to production-ready image
- **Serverless**: AWS Lambda + CloudFront with AgentCore

For complete deployment instructions, see **[REACT_DEPLOYMENT.md](../../docs/REACT_DEPLOYMENT.md)**

Quick deployment commands:
```bash
# Production build
./chatbots/build.sh build

# Docker deployment
./chatbots/build.sh docker
./chatbots/build.sh compose  # Full stack with Docker Compose
```

## Project Structure

```
react-chatbot/
├── public/
│   └── index.html           # HTML entry point
├── src/
│   ├── components/
│   │   ├── ChatMessage.js   # Message display component
│   │   ├── ChatMessage.css  # Message styling
│   │   ├── ChatInput.js     # Input field component
│   │   └── ChatInput.css    # Input styling
│   ├── App.js              # Main app component
│   ├── App.css             # App styling
│   ├── index.js            # React entry point
│   └── index.css           # Global styles
├── package.json            # Dependencies
└── README.md              # This file
```

## API Integration

The chatbot connects to the RAG Agent API and sends requests like:

```javascript
POST http://localhost:8000/v1/chat/completions
{
  "messages": [
    {"role": "user", "content": "Your question here"}
  ],
  "model": "rag-agent",
  "temperature": 0.7,
  "top_p": 0.9
}
```

## Features Walkthrough

### Message Types
- **User messages**: Purple gradient background on the right
- **Assistant messages**: White background on the left
- **System messages**: Greeting and instructions

### Status Indicators
- 🟢 **Connected**: API is ready
- 🟡 **Checking**: Verifying API connection
- 🔴 **Error**: API is unavailable

### Input Features
- **Shift+Enter**: New line
- **Enter**: Send message
- Messages auto-scroll to bottom
- Disabled when API is offline

## Customization

### Change Colors
Edit `src/App.css` gradient colors:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Change API Endpoint
Edit `src/App.js` fetch URL:
```javascript
const response = await fetch('http://your-api:port/v1/chat/completions');
```

### Adjust Max Width
Edit `src/App.css`:
```css
.chat-container {
  max-width: 800px; /* Change this */
}
```

## Troubleshooting

### "API Offline" Error
1. Start the API server: `python api_server.py` (from project root)
2. Check it's running on `http://localhost:8000`
3. Refresh the React app

### CORS Issues
The API server already has CORS enabled. If you get CORS errors:
1. Check API server console for errors
2. Verify API is responding to `/health` endpoint

### Slow Responses
- Check API server logs for bottlenecks
- Verify you have embeddings cached (run the same question twice)
- Check if Ollama and Milvus are running

## Building for Production

```bash
npm run build
```

Creates optimized production build in `build/` folder.

Deploy to Vercel, Netlify, or any static host.

## License

Same as parent project
