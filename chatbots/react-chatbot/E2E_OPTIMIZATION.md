# E2E test setup

This describes how the Playwright suite in `e2e/` starts its servers and runs.
The configuration is in `playwright.config.ts`.

## Servers

Playwright starts both servers through `webServer` entries:

- React dev server: `npm start` at `http://127.0.0.1:3000`.
- API server: `uv run python api_server.py` from the project root, health-checked at
  `http://127.0.0.1:8000/health`.

Each server has a 180-second start-up timeout. Existing servers are reused outside
CI (`reuseExistingServer: !process.env.CI`).

## Execution

- `fullyParallel: true`: tests run in parallel.
- `workers`: unset locally (Playwright chooses), 1 in CI.
- `retries`: 2 in CI, 0 locally.
- Per-test timeout: 120 seconds. Assertions wait up to 10 seconds.

## Commands

```bash
npm run test:e2e            # all tests
npm run test:e2e:ui         # interactive UI mode
npm run test:e2e:debug      # step through with the Playwright inspector
npm run test:e2e:report     # open the last HTML report
```

## Troubleshooting

1. Check the ports are free: `lsof -i :3000 -i :8000`.
2. Stop stale servers that are holding the ports, then re-run.
3. Check the API health: `curl http://localhost:8000/health`.
