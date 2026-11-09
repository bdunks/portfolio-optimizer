import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { assertTempDatabasePath } from './isolated-backend';

describe('isolated backend database path guard', () => {
  it('accepts a database file below the system temp directory', () => {
    expect(() =>
      assertTempDatabasePath(join(tmpdir(), 'portfolio-optimizer-e2e', 'demo.sqlite3')),
    ).not.toThrow();
  });

  it('rejects parent traversal and an adjacent path sharing the temp prefix', () => {
    expect(() => assertTempDatabasePath(resolve(tmpdir(), '..', 'portfolio.sqlite3'))).toThrow(
      'Refusing to use a database outside the test temp directory',
    );
    expect(() => assertTempDatabasePath(`${tmpdir()}-outside/portfolio.sqlite3`)).toThrow(
      'Refusing to use a database outside the test temp directory',
    );
  });
});
