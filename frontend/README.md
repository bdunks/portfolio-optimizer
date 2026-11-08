# Portfolio Optimizer (frontend)

## Install the dependencies

```bash
pnpm install
# or: yarn/npm/bun install
```

### Start the app in development mode (HMR, error reporting, etc.)

```bash
quasar dev
```

### Format & Lint the files

```bash
pnpm run lint
# or: yarn/npm/bun run lint
```

...or just check formatting & linting:

```bash
pnpm run lint:check
# or: yarn/npm/bun run lint:check
```

### Build the app for production

```bash
quasar build
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

### Customize the configuration

See [Configuring quasar.config.js](https://v2.quasar.dev/quasar-cli-vite/quasar-config-file).
