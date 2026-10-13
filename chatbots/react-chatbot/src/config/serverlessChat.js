// Serverless-mode chat adapter.
//
// The local API (api_server.py) exposes an OpenAI-style, Server-Sent-Events
// `POST /v1/chat/completions` endpoint. The DEPLOYED serverless backend is a
// Lambda behind API Gateway at `POST /chat` that returns a SINGLE JSON body:
//
//   { answer, sources, tier_used, session_id, latency_ms,
//     confidence_score, web_search_unavailable }
//
// This module bridges that gap so the React app can talk to the serverless
// backend without changing the rest of the UI. It is used ONLY when
// isServerlessMode() is true; local-dev streaming is untouched.

/**
 * Call the serverless `POST /chat` endpoint and normalize the response into the
 * shape App.js already works with.
 *
 * @param {object} params
 * @param {string} params.baseUrl        Resolved API base URL (no trailing slash).
 * @param {string} params.question       The current user question text.
 * @param {string} [params.sessionId]    Session id for multi-turn history.
 * @param {boolean} [params.forceWebSearch]
 * @param {number} [params.topK]
 * @param {number} [params.temperature]
 * @param {function} params.doFetch      fetch-like fn (authFetch) that attaches auth.
 * @returns {Promise<{answer: string, sources: Array, responseType: string, sessionId: string}>}
 */
export async function serverlessChat({
  baseUrl,
  question,
  sessionId,
  forceWebSearch = false,
  topK,
  temperature = 0.1,
  doFetch,
}) {
  const body = {
    question,
    force_web_search: forceWebSearch,
  };
  if (sessionId) body.session_id = sessionId;
  if (typeof topK === 'number') body.top_k = topK;
  if (typeof temperature === 'number') body.temperature = temperature;

  const response = await doFetch(new URL(`${baseUrl}/chat`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    // The serverless error envelope is { error_code, message }.
    let detail = `API error: ${response.status}`;
    try {
      const err = await response.json();
      if (err && err.message) detail = err.message;
    } catch (_e) {
      /* non-JSON error body; keep the status-based message */
    }
    throw new Error(detail);
  }

  const data = await response.json();

  // Map the serverless tier to the UI's response_type vocabulary.
  const tier = data.tier_used || 'kb';
  const responseType = tier === 'cache' ? 'cached' : tier === 'websearch' ? 'web_search' : 'rag';

  return {
    answer: typeof data.answer === 'string' ? data.answer : String(data.answer || ''),
    sources: Array.isArray(data.sources) ? data.sources : [],
    responseType,
    sessionId: data.session_id || sessionId || '',
  };
}
