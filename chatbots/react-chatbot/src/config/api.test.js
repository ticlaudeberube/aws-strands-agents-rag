// Unit tests for the centralized API/auth config resolution.
// These lock down the behavior that keeps local mode working and keeps
// serverless builds free of hardcoded localhost (Requirements 8.4, 7.4, 7.5).

describe('config/api', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    // Start each test from a clean env slate.
    process.env = { ...ORIGINAL_ENV };
    delete process.env.REACT_APP_API_URL;
    delete process.env.REACT_APP_API_HOST;
    delete process.env.REACT_APP_API_PORT;
    delete process.env.REACT_APP_AUTH_ENABLED;
    delete process.env.REACT_APP_USER_POOL_ID;
    delete process.env.REACT_APP_USER_POOL_CLIENT_ID;
    delete process.env.REACT_APP_AWS_REGION;
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  test('falls back to localhost:8000 when no env vars are set (local default)', () => {
    const { getApiBaseUrl } = require('./api');
    expect(getApiBaseUrl()).toBe('http://localhost:8000');
  });

  test('uses REACT_APP_API_HOST/PORT for local dev', () => {
    process.env.REACT_APP_API_HOST = '127.0.0.1';
    process.env.REACT_APP_API_PORT = '9999';
    const { getApiBaseUrl } = require('./api');
    expect(getApiBaseUrl()).toBe('http://127.0.0.1:9999');
  });

  test('uses REACT_APP_API_URL verbatim when set (serverless)', () => {
    process.env.REACT_APP_API_URL = 'https://abc.execute-api.us-east-1.amazonaws.com/prod';
    const { getApiBaseUrl } = require('./api');
    expect(getApiBaseUrl()).toBe('https://abc.execute-api.us-east-1.amazonaws.com/prod');
  });

  test('serverless API URL has a trailing slash trimmed and no localhost', () => {
    process.env.REACT_APP_API_URL = 'https://abc.execute-api.us-east-1.amazonaws.com/prod/';
    const { getApiBaseUrl } = require('./api');
    const url = getApiBaseUrl();
    expect(url).toBe('https://abc.execute-api.us-east-1.amazonaws.com/prod');
    expect(url).not.toContain('localhost');
  });

  test('REACT_APP_API_URL takes precedence over host/port', () => {
    process.env.REACT_APP_API_HOST = 'localhost';
    process.env.REACT_APP_API_PORT = '8000';
    process.env.REACT_APP_API_URL = 'https://api.example.com';
    const { getApiBaseUrl } = require('./api');
    expect(getApiBaseUrl()).toBe('https://api.example.com');
  });

  test('auth is disabled by default (local mode)', () => {
    const { isAuthEnabled } = require('./api');
    expect(isAuthEnabled()).toBe(false);
  });

  test('auth is enabled via explicit REACT_APP_AUTH_ENABLED=true', () => {
    process.env.REACT_APP_AUTH_ENABLED = 'true';
    const { isAuthEnabled } = require('./api');
    expect(isAuthEnabled()).toBe(true);
  });

  test('auth is inferred from presence of user pool id + client id', () => {
    process.env.REACT_APP_USER_POOL_ID = 'us-east-1_abc123';
    process.env.REACT_APP_USER_POOL_CLIENT_ID = 'client123';
    const { isAuthEnabled } = require('./api');
    expect(isAuthEnabled()).toBe(true);
  });

  test('a lone user pool id (no client id) does not enable auth', () => {
    process.env.REACT_APP_USER_POOL_ID = 'us-east-1_abc123';
    const { isAuthEnabled } = require('./api');
    expect(isAuthEnabled()).toBe(false);
  });
});
