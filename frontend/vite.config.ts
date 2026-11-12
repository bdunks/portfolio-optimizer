import tailwindcss from '@tailwindcss/vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';

const frontendDirectory = fileURLToPath(new URL('.', import.meta.url));
const apiProxyPaths = ['/api/v1', '/health'] as const;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, frontendDirectory, ['QCLI_', 'PORTFOLIO_API_TARGET', 'PORTFOLIO_E2E']);
  const apiTarget =
    process.env.PORTFOLIO_API_TARGET ?? env.PORTFOLIO_API_TARGET ?? 'http://127.0.0.1:8000';
  const open = (process.env.PORTFOLIO_E2E ?? env.PORTFOLIO_E2E) !== '1';
  const proxy = Object.fromEntries(
    apiProxyPaths.map((path) => [path, { target: apiTarget, changeOrigin: false }]),
  );

  return {
    root: frontendDirectory,
    envDir: frontendDirectory,
    base: '/',
    envPrefix: 'QCLI_',
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 9000,
      strictPort: true,
      open,
      proxy,
    },
    preview: {
      host: '127.0.0.1',
      port: 9000,
      strictPort: true,
      open,
      proxy,
    },
    build: {
      outDir: 'dist/spa',
    },
  };
});
