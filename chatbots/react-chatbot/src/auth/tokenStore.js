// In-memory JWT token store (Requirement 7.4).
//
// The app's Cognito JWT access token is held only in module-scoped memory here.
// Amplify's token provider also uses in-memory storage, so a reload clears the
// refresh token and requires the user to sign in again.

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
