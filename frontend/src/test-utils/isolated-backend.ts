import { spawn, type ChildProcess } from 'node:child_process';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const backendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '../../../backend');

export type IsolatedBackendProcess = {
  child: ChildProcess;
  exit: Promise<{ code: number | null; signal: NodeJS.Signals | null }>;
  baseUrl: string;
  logs: () => string;
  stop: () => Promise<void>;
};

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

async function waitForExit(
  backend: IsolatedBackendProcess,
  timeoutMilliseconds: number,
): Promise<boolean> {
  if (backend.child.exitCode !== null || backend.child.signalCode !== null) return true;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const exited = await Promise.race([
    backend.exit.then(() => true),
    new Promise<boolean>((resolveTimeout) => {
      timeout = setTimeout(() => resolveTimeout(false), timeoutMilliseconds);
    }),
  ]);
  if (timeout) clearTimeout(timeout);
  return exited;
}

export async function availableLoopbackPort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Could not allocate a loopback port');
  }
  await new Promise<void>((resolveClose, rejectClose) =>
    server.close((error) => (error ? rejectClose(error) : resolveClose())),
  );
  return address.port;
}

export function assertTempDatabasePath(databasePath: string): void {
  const tempRoot = resolve(tmpdir());
  const relativePath = relative(tempRoot, resolve(databasePath));
  if (
    relativePath === '' ||
    relativePath === '..' ||
    relativePath.startsWith(`..${sep}`) ||
    isAbsolute(relativePath)
  ) {
    throw new Error('Refusing to use a database outside the test temp directory');
  }
}

export async function startIsolatedBackend(
  databasePath: string,
  port: number,
  seedDemoData: boolean,
): Promise<IsolatedBackendProcess> {
  assertTempDatabasePath(databasePath);
  const child = spawn(
    'uv',
    ['run', '--offline', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: backendDirectory,
      detached: process.platform !== 'win32',
      env: {
        PATH: process.env.PATH ?? '',
        HOME: process.env.HOME ?? tmpdir(),
        UV_NO_PROGRESS: '1',
        PYTHONUNBUFFERED: '1',
        PORTFOLIO_DATABASE_URL: `sqlite:///${databasePath}`,
        PORTFOLIO_DEMO_SEED: seedDemoData ? '1' : '0',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  let output = '';
  const capture = (chunk: Buffer): void => {
    output = `${output}${chunk.toString()}`.slice(-12000);
  };
  child.stdout?.on('data', capture);
  child.stderr?.on('data', capture);
  const spawnError: { current: Error | null } = { current: null };
  child.on('error', (error) => {
    spawnError.current = error;
  });
  const exit = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(
    (resolveExit) => {
      child.once('exit', (code, signal) => resolveExit({ code, signal }));
    },
  );
  const baseUrl = `http://127.0.0.1:${port}`;
  const processHandle: IsolatedBackendProcess = {
    child,
    exit,
    baseUrl,
    logs: () => output,
    stop: async () => {
      if (child.exitCode === null && child.signalCode === null && child.pid !== undefined) {
        try {
          process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGTERM');
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== 'ESRCH') child.kill('SIGTERM');
        }
        if (!(await waitForExit(processHandle, 5000))) {
          try {
            process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGKILL');
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== 'ESRCH') child.kill('SIGKILL');
          }
          await waitForExit(processHandle, 5000);
        }
      }
      if (child.exitCode === null && child.signalCode === null) {
        throw new Error(`Isolated backend process ${child.pid ?? 'unknown'} was not reaped`);
      }
    },
  };

  const readyBy = Date.now() + 30_000;
  while (Date.now() < readyBy) {
    if (spawnError.current || child.exitCode !== null || child.signalCode !== null) break;
    try {
      const response = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(1000) });
      const health = (await response.json()) as { schema_ready?: boolean };
      if (response.ok && health.schema_ready === true) return processHandle;
    } catch {
      // Retry only the isolated loopback health request while startup is in progress.
    }
    await delay(150);
  }

  await processHandle.stop();
  const startupError = spawnError.current ? `: ${spawnError.current.message}` : '';
  throw new Error(`Isolated demo backend did not become ready${startupError}.\n${output}`);
}
