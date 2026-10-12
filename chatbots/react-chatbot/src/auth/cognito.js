// Cognito auth integration via AWS Amplify (Requirements 7.4, 7.5).
//
// This module is only ever imported/exercised when `isAuthEnabled()` is true
// (serverless mode). In local-dev mode nothing here runs, so Amplify never
// configures itself and the app behaves exactly as before.
//
// Amplify is loaded dynamically (`await import('aws-amplify/...')`) so that the
// dependency is tree-shakeable and does not get pulled into the local-mode
// code path / initial bundle unless auth is actually enabled.

import { authConfig, isAuthEnabled } from '../config/api';
import { setAccessToken, clearAccessToken } from './tokenStore';

let configured = false;

/**
 * Configure Amplify Auth from the build-time Cognito env vars.
 * Idempotent and a no-op when auth is disabled.
 */
export async function configureAuth() {
  if (!isAuthEnabled() || configured) return;

  const { Amplify } = await import('aws-amplify');
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: authConfig.userPoolId,
        userPoolClientId: authConfig.userPoolClientId,
      },
    },
  });
  configured = true;
}

/**
 * Fetch the current session and refresh the in-memory access token.
 *
 * Implements Requirement 7.5: if the current token is expired/invalid Amplify
 * transparently uses the Cognito refresh token. We pass `forceRefresh` so an
 * expired access token is actively exchanged. If no valid session can be
 * produced (refresh token also invalid/absent) the in-memory token is cleared
 * and `null` is returned so the caller can redirect to sign-in.
 *
 * @param {{ forceRefresh?: boolean }} [opts]
 * @returns {Promise<string | null>} the fresh access token, or null if unavailable
 */
export async function refreshAccessToken(opts = {}) {
  if (!isAuthEnabled()) return null;
  await configureAuth();

  try {
    const { fetchAuthSession } = await import('aws-amplify/auth');
    const session = await fetchAuthSession({ forceRefresh: Boolean(opts.forceRefresh) });
    const token = session?.tokens?.accessToken?.toString();
    if (token) {
      setAccessToken(token);
      return token;
    }
  } catch (err) {
    // No valid session / refresh token invalid or absent.
    console.warn('[auth] Unable to refresh Cognito session:', err?.message || err);
  }

  clearAccessToken();
  return null;
}

/**
 * Ensure we have a usable access token, performing an initial (non-forced)
 * session fetch if the in-memory store is empty. Used on app start.
 * @returns {Promise<string | null>}
 */
export async function ensureSignedIn() {
  if (!isAuthEnabled()) return null;
  return refreshAccessToken({ forceRefresh: false });
}

/**
 * Redirect the user to the Cognito Hosted UI sign-in page (Requirement 7.5).
 * Falls back to a hard reload if Amplify's redirect is unavailable so the user
 * is never left on a dead, unauthenticated screen.
 */
export async function redirectToSignIn() {
  if (!isAuthEnabled()) return;
  clearAccessToken();
  try {
    await configureAuth();
    const { signInWithRedirect } = await import('aws-amplify/auth');
    await signInWithRedirect();
  } catch (err) {
    console.warn('[auth] Hosted UI redirect failed, reloading:', err?.message || err);
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  }
}

/** Sign the user out and clear the in-memory token. */
export async function signOut() {
  clearAccessToken();
  if (!isAuthEnabled()) return;
  try {
    await configureAuth();
    const { signOut: amplifySignOut } = await import('aws-amplify/auth');
    await amplifySignOut();
  } catch (err) {
    console.warn('[auth] Sign-out failed:', err?.message || err);
  }
}
