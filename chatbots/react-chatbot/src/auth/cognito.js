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

let configurationPromise;

export function createAuthConfiguration(redirectUrl = window.location.origin) {
  const missing = [
    ['user pool id', authConfig.userPoolId],
    ['user pool client id', authConfig.userPoolClientId],
    ['Cognito domain', authConfig.cognitoDomain],
  ]
    .filter(([, value]) => !value)
    .map(([name]) => name);

  if (missing.length) {
    throw new Error(`Missing Cognito configuration: ${missing.join(', ')}`);
  }

  return {
    Auth: {
      Cognito: {
        userPoolId: authConfig.userPoolId,
        userPoolClientId: authConfig.userPoolClientId,
        loginWith: {
          oauth: {
            domain: authConfig.cognitoDomain
              .replace(/^https?:\/\//, '')
              .replace(/\/+$/, ''),
            scopes: ['openid', 'email'],
            redirectSignIn: [redirectUrl],
            redirectSignOut: [redirectUrl],
            responseType: 'code',
          },
        },
      },
    },
  };
}

/**
 * Configure Amplify Auth from build-time Cognito settings. Tokens stay in
 * memory; the short-lived OAuth transaction state is managed by Amplify.
 */
export async function configureAuth() {
  if (!isAuthEnabled()) return;

  if (!configurationPromise) {
    configurationPromise = (async () => {
      const [{ Amplify }, { cognitoUserPoolsTokenProvider }, { sharedInMemoryStorage }] =
        await Promise.all([
          import('aws-amplify'),
          import('aws-amplify/auth/cognito'),
          import('aws-amplify/utils'),
        ]);
      Amplify.configure(createAuthConfiguration());
      cognitoUserPoolsTokenProvider.setKeyValueStorage(sharedInMemoryStorage);
    })().catch((error) => {
      configurationPromise = undefined;
      throw error;
    });
  }

  await configurationPromise;
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

  try {
    await configureAuth();
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
 */
export async function redirectToSignIn() {
  if (!isAuthEnabled()) return;
  clearAccessToken();
  await configureAuth();
  const { signInWithRedirect } = await import('aws-amplify/auth');
  await signInWithRedirect();
}

/** Sign the user out and clear the in-memory token. */
export async function signOut() {
  try {
    if (!isAuthEnabled()) return;
    await configureAuth();
    const { signOut: amplifySignOut } = await import('aws-amplify/auth');
    await amplifySignOut();
  } finally {
    clearAccessToken();
  }
}
