# Chatbot GUI Features

This document captures the user-facing features of the React chatbot and the current UI behaviors that are still relevant to the project.

## Overview

The React chat UI is a frontend for the Strands RAG API. It supports:

- chat input and message rendering
- streamed assistant responses
- source display and source links
- cache toggling behavior
- web search triggering
- API health/status handling

## Core chat behavior

### Message sending

- Users can send messages through the input and send button.
- The app supports multi-line input and chat history.
- The send button is disabled when the input is empty or the app is busy.
- User messages are displayed in the chat and include timestamps.

### Message receiving

- Assistant responses stream in real time.
- Loading states are shown during generation.
- Auto-scroll keeps newer messages visible.
- Error responses are displayed with visible error markers.

### Chat history

- The app displays a welcome message on first load.
- Multiple exchanges are supported in the same conversation.
- Chat reset is available through the clear action.

## Response indicators

### Response types

The UI reflects the response source type:

- `cached` — response came from the cache
- `web_search` — response used web search results
- `rag` — response came from the knowledge base flow

### UI metadata

- Timing information is shown in the response area.
- Source counts appear for each answer.
- Web and KB results are visually distinguished.

## Source management

- The UI shows sources used for the answer.
- Source links remain clickable.
- KB documents and web links are displayed separately.
- Source relevance information is surfaced when available.

## Cache behavior

The frontend supports toggling cache behavior and responding to cache states, including:

- cache on/off behavior
- bypass-cache requests
- cached question handling
- no-cache override flows

These behaviors are still useful for testing and for developer understanding of the app UI layer.

## Web search behavior

The UI supports optional web search features, including:

- showing web-search availability based on the health check
- enabling a web-search request when configured
- surfacing time-sensitive or fallback web search results

This is a valid project feature and belongs in the active docs set when it reflects the current UI implementation.

## API status and health

The frontend checks backend health and exposes runtime status in the UI. This includes:

- API connected/offline state
- health-check status updates
- A visible warning when the API is reachable but the local vector DB is unavailable;
  knowledge-base search and persistent cached questions will not be available
- The answered-questions drawer and its toggle are hidden when no cached
  questions are available
- web-search capability state from the backend

## Useful validation note

This document remains useful because it reflects the current frontend contract and UI expectations. It should be kept as a feature reference, while older historical architecture docs are the ones that should be removed or condensed.
