# Milvus RAG Chatbot (React)

A self-contained React chatbot interface for the Milvus RAG system with real-time response streaming.

## Features

✨ **Modern UI**
- Beautiful gradient design with smooth animations
- Responsive layout (works on desktop and tablet)
- Dark/light message bubbles for clarity

🚀 **Performance**
- Lightweight React app
- Efficient message rendering
- API status indicator

💬 **Real-time Features**
- Instant message feedback
- Typing indicator while waiting for response
- Auto-scroll to latest message
- Clear chat history button

🔌 **Integration**
- Connects to existing `http://localhost:8000/v1/chat/completions` API
- OpenAI-compatible API requests
- Automatic API health check

## Setup

### Prerequisites
- Node.js 14+ installed
- API server running on `http://localhost:8000`

### Installation

```bash
cd react-chatbot
npm install
```

### Running

```bash
npm start
```

The app will open at `http://localhost:3000`

**Make sure the API server is running:**
```bash
# From the project root
python api_server.py
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
