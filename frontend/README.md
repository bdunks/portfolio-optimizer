# Portfolio Optimizer (frontend)

## Install the dependencies

```bash
npm install
```

### Dependency compatibility

Dependencies were checked against npm on 2026-11-12. TypeScript stays on `6.0.3`: the latest `vue-tsc`/Volar and TypeScript ESLint packages do not support TypeScript 7 yet; `7.0.2` fails both type checking and Vue compilation. Upgrade when those tools support it.

`npm audit --omit=dev` reports no vulnerabilities. The full audit still reports 14 moderate development-tool findings through `glob`/`minimatch`; npm's proposed fixes downgrade ESLint and Vue Test Utils. No forced downgrades or incompatible transitive overrides are applied.

### Start the app in development mode (HMR, error reporting, etc.)

```bash
npm run dev
```

### Format & Lint the files

```bash
npm run lint
```

...or just check formatting & linting:

```bash
npm run lint:check
```

### Build the app for production

```bash
npm run build
```

### Tests and type checks

```bash
npm test
npm run test:integration
npm run typecheck
npm run lint:check
npm run build
```

`npm run test:integration` mounts the frontend against an isolated local FastAPI demo process and temporary SQLite database. It requires the existing backend `uv` environment and does not use E*TRADE credentials or the default database.

### Real-browser workflow checks

Install the Playwright-managed Chromium build once, then run the bounded browser suite:

```bash
npm run test:e2e:install
npm run test:e2e
```

The browser tests start the real standalone Vite development server with the normal app CSS and a separate loopback FastAPI/FakeBroker process backed by a newly created temporary SQLite file. Each process uses its own allocated loopback port; teardown stops and reaps the owned process groups and removes the temporary directory. No credentials, default database, or broker traffic are used. A focused test rejects database paths outside the temp-directory boundary.

The suite runs headless Chromium at desktop `1440×1000` and tablet `768×1024` viewports. It checks rendered route navigation, keyboard focus, API empty/loading/failure states, policy revision flows, recommendation mutation rollback/remount, note clearing, and confirmed lot intent. The jsdom unit suite, real-backend API integration test, and browser suite are separate evidence; browser assertions do not claim screenshot approval, exhaustive accessibility, or broker/trading acceptance.

### Customize the configuration

See [`vite.config.ts`](./vite.config.ts) for the local development/preview server, API proxies, and build settings.
