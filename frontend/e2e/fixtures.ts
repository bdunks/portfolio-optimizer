import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test as base } from '@playwright/test';
import {
  assertTempDatabasePath,
  availableLoopbackPort,
  startIsolatedBackend,
  type IsolatedBackendProcess,
} from '../src/test-utils/isolated-backend';

type ManagedProcess = {
  child: ChildProcess;
  closed: Promise<void>;
  logs: () => string;
  spawnError: () => Error | null;
};

export type BrowserDemoApp = {
  baseUrl: string;
  apiBaseUrl: string;
};

type AppFixtures = {
  emptyApp: BrowserDemoApp;
  seededApp: BrowserDemoApp;
};

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

function startFrontend(port: number, apiBaseUrl: string): ManagedProcess {
  const child = spawn(
    'npm',
    ['run', 'dev', '--', '--port', String(port), '--hostname', '127.0.0.1'],
    {
      cwd: frontendDirectory,
      detached: process.platform !== 'win32',
      env: {
        PATH: process.env.PATH ?? '',
        HOME: process.env.HOME ?? tmpdir(),
        PORTFOLIO_API_TARGET: apiBaseUrl,
        PORTFOLIO_E2E: '1',
        NO_COLOR: '1',
        npm_config_update_notifier: 'false',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  let output = '';
  let startError: Error | null = null;
  const capture = (chunk: Buffer): void => {
    output = `${output}${chunk.toString()}`.slice(-16000);
  };
  child.stdout?.on('data', capture);
  child.stderr?.on('data', capture);
  child.on('error', (error) => {
    startError = error;
  });
  const closed = new Promise<void>((resolveClosed) => {
    child.once('close', () => resolveClosed());
  });
  return {
    child,
    closed,
    logs: () => output,
    spawnError: () => startError,
  };
}

async function waitForProcessExit(processHandle: ManagedProcess, timeoutMilliseconds: number) {
  if (processHandle.child.exitCode !== null || processHandle.child.signalCode !== null) {
    return true;
  }
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const exited = await Promise.race([
    processHandle.closed.then(() => true),
    new Promise<boolean>((resolveTimeout) => {
      timeout = setTimeout(() => resolveTimeout(false), timeoutMilliseconds);
    }),
  ]);
  if (timeout) clearTimeout(timeout);
  return exited;
}

async function stopFrontend(processHandle: ManagedProcess): Promise<void> {
  const { child } = processHandle;
  if (child.exitCode === null && child.signalCode === null && child.pid !== undefined) {
    try {
      process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGTERM');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ESRCH') child.kill('SIGTERM');
    }
    if (!(await waitForProcessExit(processHandle, 8000))) {
      try {
        process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGKILL');
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') child.kill('SIGKILL');
      }
      await waitForProcessExit(processHandle, 5000);
    }
  }
  if (child.pid !== undefined && child.exitCode === null && child.signalCode === null) {
    throw new Error(`Quasar dev process ${child.pid} was not reaped`);
  }
}

async function waitForFrontend(baseUrl: string, processHandle: ManagedProcess): Promise<void> {
  const readyBy = Date.now() + 90_000;
  while (Date.now() < readyBy) {
    if (processHandle.spawnError() || processHandle.child.exitCode !== null) break;
    try {
      const response = await fetch(baseUrl, { signal: AbortSignal.timeout(1500) });
      if (response.ok && (await response.text()).includes('<html')) return;
    } catch {
      // Retry only the isolated loopback request while Quasar starts.
    }
    await delay(200);
  }
  await stopFrontend(processHandle);
  const startupError = processHandle.spawnError();
  const errorDetail = startupError ? `: ${startupError.message}` : '';
  throw new Error(
    `Isolated Quasar dev server did not become ready${errorDetail}.\n${processHandle.logs()}`,
  );
}

async function withDemoApp(
  seedDemoData: boolean,
  use: (app: BrowserDemoApp) => Promise<void>,
): Promise<void> {
  const tempDirectory = mkdtempSync(join(tmpdir(), 'portfolio-optimizer-e2e-'));
  const databasePath = join(tempDirectory, 'isolated.sqlite3');
  assertTempDatabasePath(databasePath);
  let backend: IsolatedBackendProcess | null = null;
  let frontend: ManagedProcess | null = null;
  let teardownError: unknown;

  try {
    const backendPort = await availableLoopbackPort();
    let frontendPort = await availableLoopbackPort();
    while (frontendPort === backendPort) frontendPort = await availableLoopbackPort();

    backend = await startIsolatedBackend(databasePath, backendPort, seedDemoData);
    frontend = startFrontend(frontendPort, backend.baseUrl);
    const baseUrl = `http://127.0.0.1:${frontendPort}`;
    await waitForFrontend(baseUrl, frontend);
    await use({ baseUrl, apiBaseUrl: backend.baseUrl });
  } finally {
    if (frontend) {
      try {
        await stopFrontend(frontend);
      } catch (error) {
        teardownError = error;
      }
    }
    if (backend) {
      try {
        await backend.stop();
      } catch (error) {
        teardownError ??= error;
      }
    }
    if (!teardownError) {
      rmSync(tempDirectory, { recursive: true, force: true });
      if (existsSync(tempDirectory)) {
        teardownError = new Error(`Isolated E2E directory ${tempDirectory} was not removed`);
      }
    }
    if (teardownError) throw teardownError;
  }
}

export const test = base.extend<AppFixtures>({
  emptyApp: async ({}, use) => withDemoApp(false, use),
  seededApp: async ({}, use) => withDemoApp(true, use),
});

export { expect };
