#!/usr/bin/env node
// Run: node frontend/scripts/quasar-inventory.mjs [directory]
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { parse } from 'vue/compiler-sfc';

const scriptPath = fileURLToPath(import.meta.url);
const ignoredDirectories = new Set([
  '.git', '.quasar', 'node_modules', 'dist', 'coverage', 'test-results',
  'playwright-report', '.cache', '.vite', '.venv', '__pycache__',
]);
const ignoredFiles = new Set([
  'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb',
  path.basename(scriptPath), 'quasar-inventory.test.mjs',
]);
const textExtensions = /\.(?:vue|[cm]?[jt]sx?|json|s?css|sass|less|html?|md|ya?ml|toml|sh|txt)$/i;
const categories = [
  'Direct Quasar dependencies', 'Quasar-specific styling',
  'Ambiguous legacy styling', 'References and tooling', 'Analysis limitations',
];
const quasarPackage = /^(?:quasar(?:\/|$)|@quasar\/|#q-app(?:\/|$))/;
const mention = /\bquasar\b|@quasar\/|#q-app|<\/?q-[\w-]+|\bQ(?:Btn|Card|MarkupTable)\b/i;
const specificClass = /^(?:q-[\w-]+|(?:col|offset)-(?:[a-z]+-)?\d+|col-(?:auto|grow|shrink)|(?:lt|gt)-(?:xs|sm|md|lg|xl)|(?:xs|sm|md|lg|xl)-hide|rounded-borders|ellipsis-\d+-lines|full-(?:width|height)|text-(?:h[1-6]|subtitle[12]|body[12]|caption|overline|weight-\w+|positive|negative))$/;
const sharedClass = /^(?:row|column|flex|no-wrap|wrap|items-(?:start|end|center|baseline|stretch)|justify-(?:start|end|center|between|around|evenly)|content-(?:start|end|center|between|around|stretch)|self-(?:start|end|center|baseline|stretch)|col|hidden|ellipsis|fit|absolute(?:-full|-center)?|fixed(?:-full|-center)?|text-(?:primary|secondary|accent|warning|info|dark|white|black))$/;
const directives = /^(?:ripple|close-popup|touch-(?:pan|swipe|hold|repeat)|scroll(?:-fire)?|intersection|morph)$/;

export async function scan(root) {
  const findings = [];
  async function inspect(filename) {
    const content = await readFile(filename, 'utf8');
    if (content.includes('\0')) return;
    const file = path.relative(root, filename).split(path.sep).join('/');
    // Migration-owned primitives are deliberately outside this inventory's scope.
    if (/(?:^|\/)src\/components\/ui\//.test(file)) return;
    const lines = content.split(/\r?\n/);
    const referenceFile = /(?:^|\/)(?:scripts|e2e|test-utils)\/|\.(?:spec|test)\.[^.]+$|\.(?:md|txt)$|(?:^|\/)\.vscode\//.test(file);
    const importedComponents = new Set();
    const seen = new Set();
    function add(category, offset, reason) {
      if (referenceFile && category !== 'Analysis limitations') category = 'References and tooling';
      const line = content.slice(0, offset).split('\n').length;
      const key = `${category}:${line}:${reason}`;
      if (seen.has(key)) return;
      seen.add(key);
      findings.push({ category, file, line, source: lines[line - 1]?.trim() ?? '', reason });
    }
    function classes(value, offset) {
      for (const match of value.matchAll(/\S+/g)) {
        const token = match[0];
        if (specificClass.test(token)) add('Quasar-specific styling', offset + match.index, `class ${token}`);
        else if (sharedClass.test(token)) add('Ambiguous legacy styling', offset + match.index, `shared class ${token}; ownership requires review`);
      }
    }
    function script(source, base = 0, classExpression = false) {
      const ast = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, /\.tsx$/.test(filename) ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      for (const diagnostic of ast.parseDiagnostics) add('Analysis limitations', base + (diagnostic.start ?? 0), ts.flattenDiagnosticMessageText(diagnostic.messageText, ' '));
      function visit(node) {
        const offset = base + node.getStart(ast);
        if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && quasarPackage.test(node.moduleSpecifier.text)) {
          add('Direct Quasar dependencies', offset, `module ${node.moduleSpecifier.text}`);
          if (ts.isImportDeclaration(node)) {
            for (const binding of node.importClause?.namedBindings?.elements ?? []) importedComponents.add(binding.name.text);
          }
        }
        if (ts.isCallExpression(node)) {
          const name = node.expression.getText(ast);
          if (['useQuasar', 'setQuasarLang', 'setQuasarIconSet'].includes(name) || /^\$q\./.test(name)) add('Direct Quasar dependencies', offset, `runtime call ${name}`);
          if ((name === 'require' || node.expression.kind === ts.SyntaxKind.ImportKeyword) && node.arguments[0] && ts.isStringLiteral(node.arguments[0]) && quasarPackage.test(node.arguments[0].text)) add('Direct Quasar dependencies', offset, `module ${node.arguments[0].text}`);
        }
        if (ts.isPropertyAccessExpression(node) && /^(?:this\.)?\$q(?:\.|$)/.test(node.getText(ast))) add('Direct Quasar dependencies', offset, 'Quasar instance API');
        if (classExpression) {
          if (ts.isStringLiteralLike(node)) classes(node.text, offset);
          if (ts.isPropertyAssignment(node) && ts.isIdentifier(node.name)) classes(node.name.text, offset);
        } else if (ts.isCallExpression(node) && /^(?:cn|cva|clsx)$/.test(node.expression.getText(ast))) {
          // These helpers carry literal classes; arbitrary application strings do not.
          function literals(child) {
            if (ts.isStringLiteralLike(child)) classes(child.text, base + child.getStart(ast));
            ts.forEachChild(child, literals);
          }
          node.arguments.forEach(literals);
        }
        ts.forEachChild(node, visit);
      }
      visit(ast);
    }
    // shortcut: CSS/Sass selectors use textual extraction; computed selectors need manual review.
    function styles(source, base) {
      // Preserve offsets while excluding comments. Only selectors are class evidence.
      const clean = source.replace(/\/\*[\s\S]*?\*\//g, (s) => s.replace(/[^\n]/g, ' ')).replace(/\/\/[^\n]*/g, (s) => ' '.repeat(s.length));
      for (const match of clean.matchAll(/\.([a-zA-Z_][\w-]*)(?=[\s.#:[>+~,{])/g)) classes(match[1], base + match.index);
      for (const match of clean.matchAll(/(?:@(?:import|use|forward)\s+[^;\n]*(?:quasar|quasar\.variables)|\$(?:primary|secondary|accent|positive|negative|warning|info|dark|breakpoint-[\w-]+)\b)/g)) add('Quasar-specific styling', base + match.index, `Sass dependency ${match[0]}`);
    }
    if (referenceFile) {
      let offset = 0;
      for (const line of lines) {
        if (mention.test(line)) add('References and tooling', offset, 'Quasar reference; not application-runtime evidence');
        offset += line.length + (content.includes('\r\n') ? 2 : 1);
      }
      return;
    }
    if (/\.vue$/.test(filename)) {
      const { descriptor, errors } = parse(content, { filename });
      for (const error of errors) add('Analysis limitations', error.loc?.start?.offset ?? 0, error.message ?? String(error));
      for (const block of [descriptor.script, descriptor.scriptSetup]) if (block) script(block.content, block.loc.start.offset);
      for (const block of descriptor.styles) styles(block.content, block.loc.start.offset);
      function template(node) {
        if (node.type === 1) {
          if (/^q-[\w-]+$/.test(node.tag) || importedComponents.has(node.tag)) add('Direct Quasar dependencies', node.loc.start.offset, `component ${node.tag}`);
          else if (/^Q[A-Z]\w*$/.test(node.tag)) add('References and tooling', node.loc.start.offset, `possible auto-registered component ${node.tag}; verify registration`);
          for (const prop of node.props) {
            if (prop.type === 6 && prop.name === 'class') classes(prop.value?.content ?? '', prop.value?.loc.start.offset ?? prop.loc.start.offset);
            if (prop.type === 7) {
              if (directives.test(prop.name)) add('Direct Quasar dependencies', prop.loc.start.offset, `directive v-${prop.name}`);
              if (prop.exp && (prop.arg?.content === 'class' || /\$q\b|\buseQuasar\b/.test(prop.exp.content))) script(`(${prop.exp.content})`, prop.exp.loc.start.offset - 1, prop.name === 'bind' && prop.arg?.content === 'class');
            }
          }
        }
        if (node.type === 5) script(`(${node.content.content})`, node.content.loc.start.offset - 1);
        for (const child of node.children ?? []) template(child);
      }
      if (descriptor.template?.ast) template(descriptor.template.ast);
      for (const block of [descriptor.template, descriptor.script, descriptor.scriptSetup, ...descriptor.styles]) if (block?.src) add('Analysis limitations', block.loc.start.offset, `external block ${block.src}; inspect referenced source`);
    } else if (/\.[cm]?[jt]sx?$/.test(filename)) script(content);
    else if (/\.(?:s?css|sass|less)$/.test(filename)) styles(content, 0);
    else if (path.basename(filename) === 'package.json') {
      try {
        const pkg = JSON.parse(content);
        for (const section of ['dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies']) {
          for (const name of Object.keys(pkg[section] ?? {})) if (quasarPackage.test(name)) add('Direct Quasar dependencies', content.indexOf(`"${name}"`), `${section}: ${name}`);
        }
        for (const [name, command] of Object.entries(pkg.scripts ?? {})) if (/\bquasar\s+(?:dev|build|prepare|inspect|mode|serve)\b/.test(command)) add('Direct Quasar dependencies', content.indexOf(`"${name}"`), `Quasar script ${name}`);
      } catch (error) { add('Analysis limitations', 0, error.message); }
    }
    if (/(?:^|\/)quasar\.config\./.test(file)) add('References and tooling', 0, 'Quasar configuration; verify whether still consumed');
    let offset = 0;
    for (const line of lines) {
      if (mention.test(line) && !findings.some((f) => f.file === file && f.line === content.slice(0, offset).split('\n').length)) add('References and tooling', offset, 'Quasar reference; not proven executable');
      offset += line.length + (content.includes('\r\n') ? 2 : 1);
    }
  }
  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name, 'en'));
    for (const entry of entries) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!ignoredDirectories.has(entry.name) && entry.name !== 'scripts' && !/(?:^|[\\/])src[\\/]components[\\/]ui$/.test(filename)) await visit(filename);
      } else if (entry.isFile() && !ignoredFiles.has(entry.name) && (textExtensions.test(entry.name) || /^(?:Dockerfile|Makefile|\.gitignore)$/.test(entry.name))) await inspect(filename);
    }
  }
  await visit(root);
  return findings;
}

export function formatReport(root, findings) {
  const output = [
    `# Quasar inventory: ${root}`,
    'Excludes generated/vendor directories, lockfiles, symlinks, scripts/, scanner/tests, and src/components/ui/.',
    'Static analysis only: computed imports/classes, selectors and runtime registration need review. Zero findings does not prove independence.',
  ];
  const notes = {
    'Direct Quasar dependencies': 'Package, import, component, directive or runtime API evidence; configuration may be inactive.',
    'Quasar-specific styling': 'Quasar-named class or Sass dependency candidates.',
    'Ambiguous legacy styling': 'Shared class names; not proof of Quasar usage.',
    'References and tooling': 'References, tests, docs, tooling or unverified registration; not proven application-runtime dependencies.',
    'Analysis limitations': 'Parsing or external-source gaps requiring review.',
  };
  for (const category of categories) {
    const matches = findings.filter((finding) => finding.category === category);
    const files = [...new Set(matches.map((finding) => finding.file))];
    const locations = new Set(matches.map((finding) => `${finding.file}:${finding.line}`));
    output.push(`\n## ${category} (${locations.size} lines, ${files.length} files)`, notes[category]);
    for (const file of files) {
      output.push(`\n### ${file}`);
      const byLine = new Map();
      for (const match of matches.filter((finding) => finding.file === file)) {
        if (!byLine.has(match.line)) byLine.set(match.line, { source: match.source, reasons: new Set() });
        byLine.get(match.line).reasons.add(match.reason);
      }
      for (const [line, { source, reasons }] of byLine) {
        output.push(`- ${file}:${line}: ${source}`);
        if (category === 'Analysis limitations') {
          for (const reason of reasons) output.push(`  - ${reason}`);
        }
      }
    }
  }
  const total = new Set(findings.map((finding) => `${finding.category}:${finding.file}:${finding.line}`)).size;
  output.push(`\n## Total: ${total} category/line findings in ${new Set(findings.map((finding) => finding.file)).size} files`);
  return output.join('\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  const args = process.argv.slice(2);
  if (args.includes('--help')) console.log('Usage: node frontend/scripts/quasar-inventory.mjs [directory]\nDefaults to frontend. Read-only findings do not fail the command.');
  else if (args.length > 1 || args.some((arg) => arg.startsWith('-'))) {
    console.error('Usage: node frontend/scripts/quasar-inventory.mjs [directory]');
    process.exitCode = 1;
  } else {
    const root = args[0] ? path.resolve(args[0]) : path.resolve(path.dirname(scriptPath), '..');
    try { console.log(formatReport(root, await scan(root))); }
    catch (error) {
      console.error(`Quasar inventory failed: ${error.message}`);
      process.exitCode = 1;
    }
  }
}
