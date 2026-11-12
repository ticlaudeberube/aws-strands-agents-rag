describe('Cognito Auth configuration', () => {
  const ORIGINAL_ENV = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...ORIGINAL_ENV };
    process.env.REACT_APP_USER_POOL_ID = 'us-east-1_pool';
    process.env.REACT_APP_USER_POOL_CLIENT_ID = 'client-id';
    process.env.REACT_APP_COGNITO_DOMAIN = 'https://login.example.auth.us-east-1.amazoncognito.com/';
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  test('configures Cognito Hosted UI with the authorization code flow and app origin', () => {
    const { createAuthConfiguration } = require('./cognito');

    expect(createAuthConfiguration('https://chat.example.com')).toEqual({
      Auth: {
        Cognito: {
          userPoolId: 'us-east-1_pool',
          userPoolClientId: 'client-id',
          loginWith: {
            oauth: {
              domain: 'login.example.auth.us-east-1.amazoncognito.com',
              scopes: ['openid', 'email'],
              redirectSignIn: ['https://chat.example.com'],
              redirectSignOut: ['https://chat.example.com'],
              responseType: 'code',
            },
          },
        },
      },
    });
  });

  test('reports missing Hosted UI settings instead of silently enabling broken auth', () => {
    delete process.env.REACT_APP_COGNITO_DOMAIN;
    const { createAuthConfiguration } = require('./cognito');

    expect(() => createAuthConfiguration('https://chat.example.com')).toThrow(
      'Missing Cognito configuration: Cognito domain'
    );
  });
});
