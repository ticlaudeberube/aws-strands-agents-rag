// In-memory JWT token store (Requirement 7.4).
//
// The Cognito JWT access token is held ONLY in module-scoped JavaScript memory
// here. It is deliberately NEVER written to localStorage or sessionStorage so a
// successful XSS payload cannot read a persisted token out of web storage.
//
// Because the value lives in a plain module variable it is cleared on page
// reload — which is acceptable: Amplify can silently re-derive a fresh access
// token from the Cognito refresh token (see auth/cognito.js).

/** @type {string | null} */
let accessToken = null;

/**
 * Store the current access token in memory.
 * @param {string | null} token
 */
export function setAccessToken(token) {
  accessToken = token || null;
}

/**
 * Read the current in-memory access token.
 * @returns {string | null}
 */
export function getAccessToken() {
  return accessToken;
}

/** Clear the in-memory access token (e.g. on sign-out or failed refresh). */
export function clearAccessToken() {
  accessToken = null;
}
