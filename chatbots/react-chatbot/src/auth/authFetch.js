// Authenticated fetch wrapper (Requirements 7.4, 7.5).
//
// Behavior:
//   * Local mode (auth disabled): a transparent passthrough to `window.fetch`.
//     No Authorization header is added, so existing local-dev flows are
//     completely unchanged.
//   * Serverless mode (auth enabled):
//       1. Attach the in-memory JWT as `Authorization: Bearer <token>`.
//       2. If the request comes back 401 (expired/invalid token), attempt a
//          single forced refresh via the Cognito refresh token, then retry once.
//       3. If the refresh fails (refresh token invalid/absent), redirect the
//          user to the Cognito sign-in page.

import { isAuthEnabled } from '../config/api';
import { getAccessToken } from './tokenStore';
import { refreshAccessToken, redirectToSignIn } from './cognito';

/**
 * Merge an Authorization: Bearer header into a RequestInit without mutating the
 * caller's object or clobbering existing headers.
 * @param {RequestInit} init
 * @param {string} token
 * @returns {RequestInit}
 */
function withBearer(init, token) {
  const headers = new Headers(init.headers || {});
  headers.set('Authorization', `Bearer ${token}`);
  return { ...init, headers };
}

/**
 * fetch() wrapper that handles Cognito auth for serverless mode and is a plain
 * passthrough in local mode.
 *
 * @param {RequestInfo | URL} input
 * @param {RequestInit} [init]
 * @returns {Promise<Response>}
 */
export async function authFetch(input, init = {}) {
  if (!isAuthEnabled()) {
    // Local mode: no auth, behave exactly like the native fetch.
    return fetch(input, init);
  }

  // Ensure we have a token up front; refresh non-forced if the store is empty.
  let token = getAccessToken();
  if (!token) {
    token = await refreshAccessToken({ forceRefresh: false });
  }
  if (!token) {
    // No session at all -> go sign in.
    await redirectToSignIn();
    throw new Error('Not authenticated');
  }

  let response = await fetch(input, withBearer(init, token));

  // 401 => token likely expired/invalid. Try one forced refresh + retry.
  if (response.status === 401) {
    const refreshed = await refreshAccessToken({ forceRefresh: true });
    if (!refreshed) {
      await redirectToSignIn();
      return response;
    }
    response = await fetch(input, withBearer(init, refreshed));
  }

  return response;
}
