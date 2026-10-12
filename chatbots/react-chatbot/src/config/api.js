// Centralized API + mode configuration.
//
// This module is the SINGLE source of truth for the API base URL and for
// deciding whether the app runs in serverless mode (Cognito auth enabled) or
// local-dev mode (no auth). Keeping all of this in one place is what lets the
// serverless build stay free of hardcoded "localhost" references
// (see Property 24: "React build artifacts never contain localhost references").
//
// Resolution rules:
//   * API base URL (Requirement 8.4):
//       - If REACT_APP_API_URL is set, use it VERBATIM (the full HTTPS API
//         Gateway URL used by serverless builds). This branch contains no
//         "localhost" string.
//       - Otherwise fall back to the legacy local-dev behavior built from
//         REACT_APP_API_HOST / REACT_APP_API_PORT (defaults localhost:8000).
//         The "localhost" literal lives ONLY in this local-dev branch.
//   * Auth (Requirements 7.4, 7.5):
//       - Serverless mode is gated behind an explicit flag OR inferred from the
//         Cognito user-pool id being present, so local mode keeps working with
//         no auth and no Cognito config.

/**
 * Full API base URL for serverless builds, if provided at build time.
 * `react-scripts` inlines `process.env.REACT_APP_*` at build time, so an unset
 * value becomes `undefined` and the local-dev fallback is used instead.
 * @type {string | undefined}
 */
const SERVERLESS_API_URL = process.env.REACT_APP_API_URL;

/**
 * Build the local-development API base URL from host/port env vars.
 * This is the ONLY place the "localhost" default is referenced, and it is only
 * reached when REACT_APP_API_URL is NOT set (i.e. never in a serverless build).
 * @returns {string}
 */
function buildLocalApiBaseUrl() {
  const host = process.env.REACT_APP_API_HOST || 'localhost';
  const port = process.env.REACT_APP_API_PORT || '8000';
  return `http://${host}:${port}`;
}

/**
 * Resolve the API base URL (no trailing slash).
 * @returns {string}
 */
export function getApiBaseUrl() {
  if (SERVERLESS_API_URL && SERVERLESS_API_URL.trim()) {
    // Use the serverless URL verbatim, only trimming a trailing slash so that
    // callers can safely concatenate `${base}/path`.
    return SERVERLESS_API_URL.trim().replace(/\/+$/, '');
  }
  return buildLocalApiBaseUrl();
}

/**
 * Cognito / auth configuration read from build-time env vars.
 * All fields are undefined in local mode.
 */
export const authConfig = {
  userPoolId: process.env.REACT_APP_USER_POOL_ID,
  userPoolClientId: process.env.REACT_APP_USER_POOL_CLIENT_ID,
  region: process.env.REACT_APP_AWS_REGION,
};

/**
 * Whether Cognito auth is enabled for this build.
 *
 * Enabled when EITHER:
 *   - REACT_APP_AUTH_ENABLED is explicitly "true", OR
 *   - a Cognito user-pool id is present (serverless deploys always set it).
 *
 * This stays `false` for local-mode development (no serverless env vars set),
 * so the existing no-auth localhost flow is completely unchanged.
 * @returns {boolean}
 */
export function isAuthEnabled() {
  const explicit = (process.env.REACT_APP_AUTH_ENABLED || '').toLowerCase() === 'true';
  const inferred = Boolean(authConfig.userPoolId && authConfig.userPoolClientId);
  return explicit || inferred;
}

// Convenience constant for modules that only need the resolved base URL once.
export const API_BASE_URL = getApiBaseUrl();
