import { createHash, randomUUID } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, writeFile, rename, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const { audit, markdown, validateDispositions } = await import(new URL('./quasar-audit.mts', import.meta.url).href);

const etag = (data) => `"${createHash('sha256').update(data).digest('hex')}"`;
const failure = (status, message) => Object.assign(new Error(message), { status });
const sort = (items) =>
  items
    .map(({ findingId, disposition }) => ({ findingId, disposition }))
    .sort((a, b) => (a.findingId < b.findingId ? -1 : a.findingId > b.findingId ? 1 : 0));

export function createReviewServer(directory, root = fileURLToPath(new URL('../../', import.meta.url))) {
  const file = (name) => path.join(directory, name);
  async function decisionsFile() {
    try {
      return await readFile(file('dispositions.json'), 'utf8');
    } catch (error) {
      if (error.code === 'ENOENT') return '[]\n';
      throw error;
    }
  }
  let writes = Promise.resolve();
  const server = createServer(async (request, response) => {
    const address = server.address();
    const origin = `http://127.0.0.1:${address.port}`;
    const send = (status, body, headers = {}) => {
      response.writeHead(status, {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Cross-Origin-Resource-Policy': 'same-origin',
        ...headers,
      });
      response.end(body);
    };
    try {
      if (
        request.headers.host !== `127.0.0.1:${address.port}` ||
        (request.headers.origin && request.headers.origin !== origin)
      )
        throw failure(403, 'Local same-origin requests only.');
      const route = request.url;
      if (
        request.method === 'GET' &&
        ['/', '/review.html', '/inventory.json', '/dispositions.json'].includes(route)
      ) {
        const data =
          route === '/dispositions.json'
            ? await decisionsFile()
            : await readFile(file(route === '/' ? 'review.html' : route.slice(1)), 'utf8');
        send(200, data, {
          ETag: etag(data),
          'Content-Type': route.endsWith('.json')
            ? 'application/json; charset=utf-8'
            : 'text/html; charset=utf-8',
        });
        return;
      }
      if (route === '/rerun-audit') {
        request.resume();
        if (request.method !== 'POST') throw failure(405, 'Method not allowed.');
        if (request.headers.origin !== origin ||
            request.headers['content-type'] !== 'application/json')
          throw failure(403, 'Same-origin JSON writes only.');
        const operation = writes.then(async () => {
          const report = await audit(root);
          await writeFile(file('inventory.md'), markdown(report));
          const temporary = file(`.inventory-${randomUUID()}.tmp`);
          try {
            await writeFile(temporary, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
            await rename(temporary, file('inventory.json'));
          } finally {
            await rm(temporary, { force: true });
          }
        });
        writes = operation.catch(() => {});
        await operation;
        send(200, JSON.stringify({ ok: true }));
        return;
      }
      if (route !== '/dispositions.json') throw failure(404, 'Not found.');
      if (request.method !== 'PUT') throw failure(405, 'Method not allowed.');
      if (
        request.headers.origin !== origin ||
        request.headers['content-type'] !== 'application/json'
      )
        throw failure(403, 'Same-origin JSON writes only.');
      if (!request.headers['if-match'] || !request.headers['x-inventory-version'])
        throw failure(428, 'Inventory and disposition versions are required.');
      if (Number(request.headers['content-length']) > 1024 * 1024) {
        request.resume();
        throw failure(413, 'Decision file exceeds 1 MiB.');
      }
      const chunks = [];
      let size = 0;
      for await (const chunk of request.iterator({ destroyOnReturn: false })) {
        size += chunk.length;
        if (size > 1024 * 1024) {
          request.resume();
          throw failure(413, 'Decision file exceeds 1 MiB.');
        }
        chunks.push(chunk);
      }
      const body = Buffer.concat(chunks).toString('utf8');
      let values;
      try {
        values = JSON.parse(body);
      } catch {
        throw failure(400, 'Invalid JSON.');
      }
      const operation = writes.then(async () => {
        const inventoryText = await readFile(file('inventory.json'), 'utf8');
        const previous = await decisionsFile();
        if (
          request.headers['if-match'] !== etag(previous) ||
          request.headers['x-inventory-version'] !== etag(inventoryText)
        )
          throw failure(
            409,
            'Files changed on disk. Export pending decisions, then reload and reconcile; nothing was overwritten.',
          );
        try {
          validateDispositions(values, JSON.parse(inventoryText).findings);
        } catch {
          throw failure(422, 'Decisions need unique current IDs and approved/rejected values.');
        }
        const data = JSON.stringify(sort(values), null, 2) + '\n';
        const temporary = file(`.dispositions-${randomUUID()}.tmp`);
        try {
          await writeFile(temporary, data, { flag: 'wx', mode: 0o600 });
          // shortcut: external editors are not locked; use one writer and reload if files change.
          if (
            etag(await decisionsFile()) !== etag(previous) ||
            etag(await readFile(file('inventory.json'), 'utf8')) !== etag(inventoryText)
          )
            throw failure(
              409,
              'Files changed during save. Export pending decisions and reconcile.',
            );
          await rename(temporary, file('dispositions.json'));
        } finally {
          await rm(temporary, { force: true });
        }
        return data;
      });
      writes = operation.catch(() => {});
      const data = await operation;
      send(200, data, { ETag: etag(data) });
    } catch (error) {
      send(
        error.status ?? 500,
        JSON.stringify({
          error: error.status
            ? error.message
            : 'Local file operation failed. No save was confirmed; check file permissions and retry.',
        }),
      );
    }
  });
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createReviewServer(
    fileURLToPath(new URL('../../docs/quasar-audit/', import.meta.url)),
  );
  server.on('error', (error) => {
    console.error(`Review helper: ${error.message}`);
    process.exitCode = 1;
  });
  server.listen(0, '127.0.0.1', () => {
    console.log(`Quasar audit reviewer: http://127.0.0.1:${server.address().port}/`);
    console.log(
      'Inventory loads automatically; decisions auto-save to docs/quasar-audit/dispositions.json. Ctrl+C to stop.',
    );
  });
}
