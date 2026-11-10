#!/usr/bin/env node
// Run: node frontend/scripts/quasar-inventory.mjs [directory]
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const ignoredDirectories = new Set([
  '.git',
  '.quasar',
  'node_modules',
  'dist',
  'coverage',
  'test-results',
  'playwright-report',
  '.cache',
  '.vite',
  '.venv',
  '__pycache__',
]);
const ignoredFiles = new Set([
  'package-lock.json',
  'pnpm-lock.yaml',
  'yarn.lock',
  'bun.lock',
  'bun.lockb',
  path.basename(scriptPath),
  'quasar-inventory.test.mjs',
]);
const textExtensions = /\.(?:vue|[cm]?[jt]sx?|json|s?css|sass|less|html?|md|ya?ml|toml|sh|txt)$/i;

// shortcut: textual candidates include comments and cannot resolve aliases/dynamic strings; use source review before removal.
const rules = [
  [
    'Components and directives',
    /<\/?q-[\w-]+\b|\bQ[A-Z][A-Za-z0-9]*\b|\bv-(?:ripple|close-popup|touch-(?:pan|swipe|hold|repeat)|scroll(?:-fire)?|intersection|morph)\b/,
  ],
  [
    'Imports and runtime APIs',
    /\b(?:quasar|useQuasar|setQuasarLang|setQuasarIconSet)\b|\$q\b|@quasar\//i,
  ],
  [
    'Styles and layout utilities',
    /\bq-(?:[mp][atblrxy]-(?:none|xs|sm|md|lg|xl|auto)|gutter(?:-[xy])?-(?:none|xs|sm|md|lg|xl))\b|\b(?:row|column|flex|no-wrap|wrap|items-(?:start|end|center|baseline|stretch)|justify-(?:start|end|center|between|around|evenly)|content-(?:start|end|center|between|around|stretch)|self-(?:start|end|center|baseline|stretch)|col(?:-(?:(?:xs|sm|md|lg|xl)(?:-\d+)?|\d+|auto|grow|shrink))?|offset-(?:(?:xs|sm|md|lg|xl)-)?\d+|(?:lt|gt)-(?:xs|sm|md|lg|xl)|(?:xs|sm|md|lg|xl)-hide|hidden|rounded-borders|ellipsis(?:-\d+-lines)?|full-(?:width|height)|fit|absolute(?:-full|-center)?|fixed(?:-full|-center)?|text-(?:h[1-6]|subtitle[12]|body[12]|caption|overline|weight-\w+|(?:blue-grey|grey|primary|secondary|accent|positive|negative|warning|info|dark|white|black)(?:-\d+)?))\b|\$(?:primary|secondary|accent|positive|negative|warning|info|dark|breakpoint-[\w-]+|[\w-]+-(?:spaces|space|gutter))\b|quasar\.variables/,
  ],
  [
    'Icons and fonts',
    /material-icons|material-symbols|roboto-font|@quasar\/extras|\b(?:icon-set|iconSet)\b/i,
  ],
  [
    'Build and generated dependencies',
    /#q-app|\.quasar\b|quasar(?:\.config|\s+(?:dev|build|prepare|inspect|mode|serve))|@quasar\/app|quasar\/wrappers|quasar\/dist/i,
  ],
];

export async function scan(root) {
  const findings = [];
  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name, 'en'));
    for (const entry of entries) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!ignoredDirectories.has(entry.name)) await visit(filename);
      } else if (
        entry.isFile() &&
        !ignoredFiles.has(entry.name) &&
        (textExtensions.test(entry.name) ||
          /^(?:Dockerfile|Makefile|\.gitignore)$/.test(entry.name))
      ) {
        const content = await readFile(filename, 'utf8');
        if (content.includes('\0')) continue;
        const file = path.relative(root, filename).split(path.sep).join('/');
        content.split(/\r?\n/).forEach((source, index) => {
          for (const [category, pattern] of rules) {
            if (pattern.test(source))
              findings.push({ category, file, line: index + 1, source: source.trim() });
          }
        });
      }
    }
  }
  await visit(root);
  return findings;
}

export function formatReport(root, findings) {
  const output = [
    `Quasar inventory: ${root}`,
    'Textual candidates only; comments and generic CSS tokens may be false positives.',
    'Skips generated/vendor directories, lockfiles, symlinks, and this scanner/tests.',
    'Test, script, and documentation matches are included; zero findings is not proof of independence.',
  ];
  for (const [category] of rules) {
    const matches = findings.filter((finding) => finding.category === category);
    const files = new Set(matches.map((finding) => finding.file));
    output.push(`\n${category}: ${matches.length} matching lines in ${files.size} files`);
    for (const match of matches) output.push(`  ${match.file}:${match.line}: ${match.source}`);
  }
  output.push(
    `\nTotal: ${findings.length} category/line findings in ${new Set(findings.map((finding) => finding.file)).size} files (a line can match multiple categories).`,
  );
  return output.join('\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  const args = process.argv.slice(2);
  if (args.includes('--help')) {
    console.log(
      'Usage: node frontend/scripts/quasar-inventory.mjs [directory]\nDefaults to frontend. Prints read-only category/file/line candidates; findings do not fail the command.',
    );
  } else if (args.length > 1 || args.some((arg) => arg.startsWith('-'))) {
    console.error('Usage: node frontend/scripts/quasar-inventory.mjs [directory]');
    process.exitCode = 1;
  } else {
    const root = args[0] ? path.resolve(args[0]) : path.resolve(path.dirname(scriptPath), '..');
    try {
      console.log(formatReport(root, await scan(root)));
    } catch (error) {
      console.error(`Quasar inventory failed: ${error.message}`);
      process.exitCode = 1;
    }
  }
}
