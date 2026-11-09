import { createHash } from 'node:crypto';
import { readdir, readFile, realpath, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseForESLint, type AST } from 'vue-eslint-parser';
import tsParser from '@typescript-eslint/parser';
import postcss from 'postcss';

export type Finding = {
  id: string;
  rule: string;
  file: string;
  line: number;
  column: number;
  evidence: string;
  context: string;
  suggestion: string;
  confidence: 'high' | 'medium' | 'low';
  caution: string;
};
export type Inventory = {
  schemaVersion: number;
  scope: string;
  limitations: string[];
  files: { file: string; sha256: string }[];
  styles: { file: string; line: number; context: string; owner: string }[];
  quasarUsage: { file: string; line: number; component: string }[];
  findings: Finding[];
};
const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const hash = (text: string) => createHash('sha256').update(text).digest('hex');
const slash = (name: string) => name.split(path.sep).join('/');
const limitations = [
  'Candidates, not defects. No UI changes, CSS deletion, cascade analysis, rendered-style or accessibility verification.',
  'Scope: .vue/.css/.scss/.sass/.less under frontend/src plus local CSS style-src/import references inside the repository. Symlinks are not followed. Test scripts, public HTML, assets and dependencies are excluded.',
  'Template detection uses native tags, static class/role names and literal strings in bound class expressions; computed class names and dynamic components are unresolved. No JavaScript execution or component expansion.',
  'Bound inline styles are inventoried but not evaluated, including object/array literals. Script-created styles, render functions, CSS-in-JS and runtime style injection are outside scope.',
  'CSS and CSS-compatible SCSS (full-line // comments masked without changing coordinates) are parsed. Sass variables, interpolation, nesting and preprocessor directives are unsupported. Sass/Less files and unresolved imports are disclosed.',
  'Duplication means identical ordered blocks of at least three declarations (including !important), not semantic equivalence or proof of redundancy. Shared style-src is parsed once and owners are listed separately.',
  'Layout/spacing findings are low-confidence review candidates. Grid is legitimate; gap is not interchangeable with gutters. No numeric value is assumed equal to a Quasar token.',
  'Selectors are heuristic text matches, not resolved selector ASTs. Scoped/deep/global and responsive context must be preserved. Unused CSS is not detected.',
  'Static inline style attributes are listed whole, not parsed into declaration-level or duplicate-block findings. CSS imports with conditions are parsed as source, not evaluated in their importer cascade.',
];

export async function audit(root: string): Promise<Inventory> {
  root = await realpath(root);
  const report: Inventory = {
    schemaVersion: 1,
    scope: 'frontend/src',
    limitations,
    files: [],
    styles: [],
    quasarUsage: [],
    findings: [],
  };
  const sources = new Map<string, string>();
  const parsedCss = new Set<string>();
  const duplicates = new Map<
    string,
    { file: string; offset: number; evidence: string; context: string }[]
  >();
  const relative = (file: string) => slash(path.relative(root, file));
  async function source(file: string) {
    if (!sources.has(file)) sources.set(file, await readFile(file, 'utf8'));
    return sources.get(file)!;
  }
  function add(
    file: string,
    offset: number,
    rule: string,
    evidence: string,
    context: string,
    suggestion: string,
    confidence: Finding['confidence'],
    caution: string,
  ) {
    const before = sources.get(file)!.slice(0, offset);
    const line = before.split('\n').length;
    const column = offset - before.lastIndexOf('\n');
    const item = {
      id: '',
      rule,
      file: relative(file),
      line,
      column,
      evidence: evidence.trim(),
      context,
      suggestion,
      confidence,
      caution,
    };
    item.id = hash(JSON.stringify(item)).slice(0, 16);
    if (!report.findings.some((other) => other.id === item.id)) report.findings.push(item);
  }
  function unresolved(file: string, offset: number, evidence: string, context: string) {
    add(
      file,
      offset,
      'coverage.unresolved',
      evidence,
      context,
      'Investigate manually; no automatic Quasar equivalent',
      'low',
      'This construct was not resolved; inventory coverage is incomplete here.',
    );
  }
  async function localReference(
    owner: string,
    offset: number,
    ref: string,
    context: string,
  ): Promise<string | null> {
    if (!ref.startsWith('.')) {
      unresolved(owner, offset, ref, context);
      return null;
    }
    const target = path.resolve(path.dirname(owner), ref);
    try {
      const resolved = await realpath(target);
      if (
        resolved !== target ||
        path.relative(root, resolved).startsWith('..') ||
        !resolved.endsWith('.css')
      ) {
        unresolved(owner, offset, ref, context);
        return null;
      }
      return resolved;
    } catch {
      unresolved(owner, offset, ref, context);
      return null;
    }
  }
  async function css(file: string, code: string, base: number, context: string) {
    const key = `${file}:${base}`;
    if (parsedCss.has(key)) return;
    parsedCss.add(key);
    report.styles.push({
      file: relative(file),
      line: sources.get(file)!.slice(0, base).split('\n').length,
      context,
      owner: relative(file),
    });
    let sheet;
    try {
      sheet = postcss.parse(code, { from: file });
    } catch (error) {
      unresolved(file, base, String(error).replaceAll(root, '<root>'), context);
      return;
    }
    const imports: { ref: string; offset: number }[] = [];
    sheet.walkAtRules((at) => {
      if (at.name === 'import') {
        const match = at.params.match(/^(?:url\(\s*)?['"]([^'"]+)['"]\s*\)?/);
        if (match) imports.push({ ref: match[1]!, offset: base + (at.source?.start?.offset ?? 0) });
        else unresolved(file, base + (at.source?.start?.offset ?? 0), at.toString(), context);
      } else if (
        ![
          'media',
          'supports',
          'layer',
          'container',
          'keyframes',
          '-webkit-keyframes',
          'font-face',
          'charset',
          'property',
          'scope',
          'starting-style',
        ].includes(at.name)
      ) {
        unresolved(file, base + (at.source?.start?.offset ?? 0), at.toString(), context);
      }
    });
    sheet.walkRules((rule) => {
      const offset = base + (rule.source?.start?.offset ?? 0);
      const ancestors: string[] = [];
      for (let parent = rule.parent; parent && parent.type !== 'root'; parent = parent.parent) {
        if (parent.type === 'atrule') ancestors.unshift(`@${parent.name} ${parent.params}`);
      }
      const location = [context, ...ancestors, rule.selector].join(' / ');
      const declarations = rule.nodes.filter((node) => node.type === 'decl');
      const evidence = `${rule.selector} { ${declarations.map((d) => d.toString()).join('; ')} }`;
      if (context.includes('(scss)') && rule.parent?.type === 'rule')
        unresolved(file, offset, evidence, `${location} / SCSS nesting not compiled`);
      const emit = (
        id: string,
        suggestion: string,
        confidence: Finding['confidence'],
        caution: string,
      ) => add(file, offset, id, evidence, location, suggestion, confidence, caution);
      if (/\.q-[\w-]+/.test(rule.selector))
        emit(
          'css.quasar-override',
          'Prefer supported Quasar props, slots or theme variables where possible',
          'high',
          'Intentional branding may remain. Internal classes can change; preserve scoped/deep selectors and responsive behavior.',
        );
      if (
        /button|input|select|textarea|(?:primary|secondary|danger|text|icon)-button|:disabled|:focus/.test(
          rule.selector,
        )
      )
        emit(
          'css.control',
          'q-btn / q-input / q-select / q-checkbox props and states',
          'medium',
          'Preserve focus visibility, labels, form submission, disabled/loading behavior and decimal-string inputs; native controls can be intentional.',
        );
      if (/card|panel|notice|banner|badge|chip/.test(rule.selector))
        emit(
          'css.surface',
          /notice|banner|alert|error/.test(rule.selector)
            ? 'q-banner for messages'
            : /badge|chip/.test(rule.selector)
              ? 'q-badge / q-chip'
              : 'q-card / q-card-section for appropriate surfaces',
          'medium',
          'Names are heuristic; domain components and semantic sections can remain. Notices need live-region role review, not automatic q-card conversion.',
        );
      const layout = declarations.filter((d) =>
        /^(display|flex.*|align-.*|justify-.*|gap|row-gap|column-gap|margin.*|padding.*)$/.test(
          d.prop,
        ),
      );
      if (layout.length)
        emit(
          'css.layout-spacing',
          'Review row / column / items-* / justify-* and q-[mp]* spacing utilities',
          'low',
          'Compare actual computed values, breakpoints, specificity and wrapping. Keep Grid, custom spacing and domain layout when appropriate; do not assume token equivalence.',
        );
      if (declarations.length >= 3) {
        const signature = declarations
          .map((d) => `${d.prop}:${d.value}${d.important ? '!important' : ''}`)
          .join(';');
        const group = duplicates.get(signature) ?? [];
        group.push({ file, offset, evidence, context: location });
        duplicates.set(signature, group);
      }
      if (declarations.some((d) => /v-bind\(|#\{|\$[\w-]/.test(d.value)))
        unresolved(file, offset, evidence, location);
    });
    for (const item of imports) {
      const target = await localReference(file, item.offset, item.ref, `${context} / @import`);
      if (target)
        await css(
          target,
          await source(target),
          0,
          'external CSS; usage context listed at importer',
        );
    }
  }
  const native: Record<string, string> = {
    button: 'q-btn',
    input: 'q-input',
    select: 'q-select',
    textarea: 'q-input type=textarea',
    table: 'q-markup-table; q-table only when its data features are needed',
    progress: 'q-linear-progress',
    meter: 'q-linear-progress after semantic review',
    details: 'q-expansion-item after semantic review',
  };
  async function vue(file: string, code: string) {
    let parsed;
    try {
      parsed = parseForESLint(code, {
        parser: tsParser,
        ecmaVersion: 2022,
        sourceType: 'module',
        filePath: file,
      });
    } catch (error) {
      unresolved(file, 0, String(error).replaceAll(root, '<root>'), 'Vue parser failure');
      return;
    }
    const template = parsed.ast.templateBody;
    // Vue SFCs support self-closing tags that the HTML tokenizer reports as errors.
    for (const error of template?.errors ?? [])
      if (error.code !== 'non-void-html-element-start-tag-with-trailing-solidus')
        unresolved(file, error.index ?? 0, error.message, 'Vue template parser error');
    const attrValue = (node: AST.VElement, name: string) => {
      const attr = node.startTag.attributes.find((a) => !a.directive && a.key.name === name);
      return attr && !attr.directive ? attr.value?.value : undefined;
    };
    function walk(node: AST.VElement) {
      const tag = node.rawName;
      const componentTag = tag
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .replace(/^Q(?=[A-Z])/, 'q-')
        .toLowerCase();
      const opening = code.slice(...node.startTag.range);
      const context = `template <${tag}>`;
      const inputType = (attrValue(node, 'type') || 'text').toLowerCase();
      const inputMode = attrValue(node, 'inputmode');
      const inputComponents: Record<string, string> = {
        checkbox: 'q-checkbox',
        radio: 'q-radio',
        file: 'q-file',
      };
      if (componentTag.startsWith('q-'))
        report.quasarUsage.push({
          file: relative(file),
          line: node.loc.start.line,
          component: componentTag,
        });
      if (native[tag])
        add(
          file,
          node.range[0],
          'template.native-control',
          opening,
          context,
          tag === 'input'
            ? (inputComponents[inputType] ??
                `q-input type=${inputType}${inputMode ? ` inputmode=${inputMode}` : ''}`)
            : native[tag]!,
          'high',
          'Candidate only. Preserve semantic HTML, keyboard/label associations, form submit/reset, disabled/loading behavior, events and decimal-string financial values; do not add .number coercion.',
        );
      const classes = node.startTag.attributes.filter((a) =>
        !a.directive
          ? a.key.name === 'class'
          : a.key.name.name === 'bind' &&
            a.key.argument?.type === 'VIdentifier' &&
            a.key.argument.name === 'class',
      );
      const classText = classes
        .map((a) =>
          !a.directive
            ? (a.value?.value ?? '')
            : [
                ...(a.value?.expression ? code.slice(...a.value.expression.range) : '').matchAll(
                  /['"]([^'"]+)['"]/g,
                ),
              ]
                .map((m) => m[1])
                .join(' '),
        )
        .join(' ');
      const role = attrValue(node, 'role');
      if (
        !componentTag.startsWith('q-') &&
        (/card|panel|notice|banner|badge|chip/i.test(`${tag} ${classText}`) ||
          ['alert', 'status'].includes(role ?? ''))
      ) {
        const notice =
          /notice|banner|error|alert|message/i.test(`${tag} ${classText}`) ||
          ['alert', 'status'].includes(role ?? '');
        add(
          file,
          node.range[0],
          'template.custom-surface',
          opening,
          context,
          notice
            ? 'q-banner for messages (review role)'
            : /badge|chip/i.test(`${tag} ${classText}`)
              ? 'q-badge / q-chip'
              : 'q-card / q-card-section, or retain semantic/domain component',
          'medium',
          'Heuristic name/role match, not proof of reinvention. Inspect shared component implementation first. Preserve headings, slots and live-region politeness; q-banner defaults to alert.',
        );
      }
      for (const attr of node.startTag.attributes) {
        if (!attr.directive && attr.key.name === 'style' && attr.value) {
          add(
            file,
            attr.range[0],
            'template.inline-style',
            code.slice(...attr.range),
            context,
            'Review Quasar utilities only when computed styles are equivalent',
            'low',
            'Inline styles may be intentional; preserve specificity and custom dimensions.',
          );
        } else if (
          attr.directive &&
          attr.key.name.name === 'bind' &&
          attr.key.argument?.type === 'VIdentifier' &&
          attr.key.argument.name === 'style'
        ) {
          unresolved(
            file,
            attr.range[0],
            code.slice(...attr.range),
            `${context} / bound inline style (not evaluated)`,
          );
        } else if (
          attr.directive &&
          attr.key.name.name === 'bind' &&
          (!attr.key.argument || attr.key.argument.type !== 'VIdentifier')
        ) {
          unresolved(
            file,
            attr.range[0],
            code.slice(...attr.range),
            `${context} / spread or dynamic binding`,
          );
        }
      }
      if (
        tag === 'component' ||
        node.startTag.attributes.some((a) => !a.directive && a.key.name === 'is')
      )
        unresolved(file, node.range[0], opening, `${context} / dynamic component`);
      for (const child of node.children) if (child.type === 'VElement') walk(child);
    }
    if (template) walk(template);
    else
      unresolved(
        file,
        0,
        'No parsed template (script/render-only SFC or external template)',
        'Vue template',
      );
    for (const block of parsed.services?.getDocumentFragment()?.children ?? []) {
      if (block.type !== 'VElement') continue;
      if (block.name === 'template' && attrValue(block, 'src'))
        unresolved(file, block.range[0], code.slice(...block.startTag.range), 'external template');
      if (block.name !== 'style') continue;
      const context = `Vue ${block.startTag.attributes.some((a) => !a.directive && a.key.name === 'scoped') ? 'scoped' : 'global'} style${attrValue(block, 'module') !== undefined ? ' module' : ''}`;
      const src = attrValue(block, 'src');
      if (src) {
        report.styles.push({
          file: relative(file),
          line: block.loc.start.line,
          context: `${context} src=${src}`,
          owner: relative(file),
        });
        const target = await localReference(file, block.range[0], src, context);
        if (target)
          await css(
            target,
            await source(target),
            0,
            'external CSS; usage context listed at importer',
          );
      } else {
        const base = block.startTag.range[1];
        const styleCode = code.slice(base, block.endTag?.range[0] ?? base);
        await stylesheet(file, styleCode, base, context, attrValue(block, 'lang') ?? 'css');
      }
    }
  }
  async function stylesheet(
    file: string,
    code: string,
    base: number,
    context: string,
    lang: string,
  ) {
    if (lang === 'scss') {
      code = code.replace(/^[ \t]*\/\/[^\r\n]*/gm, (comment) => ' '.repeat(comment.length));
      if (
        /\$[\w-]|#\{|@(use|forward|mixin|include|extend|function|if|each|for|while)\b|[&]/.test(
          code,
        )
      ) {
        unresolved(file, base, 'Unsupported SCSS constructs; stylesheet not parsed', context);
        return;
      }
    } else if (lang !== 'css') {
      unresolved(file, base, `Unsupported stylesheet language: ${lang}`, context);
      return;
    }
    await css(file, code, base, `${context} (${lang})`);
  }
  async function visit(directory: string) {
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) =>
      compare(a.name, b.name),
    )) {
      const file = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) await visit(file);
      else if (/\.(vue|css|scss|sass|less)$/.test(entry.name)) {
        const code = await source(file);
        if (entry.name.endsWith('.vue')) await vue(file, code);
        else
          await stylesheet(
            file,
            code,
            0,
            'standalone stylesheet; import/use not inferred',
            path.extname(file).slice(1),
          );
      }
    }
  }
  await visit(path.join(root, 'frontend/src'));
  for (const group of duplicates.values())
    if (group.length > 1) {
      const peers = group
        .map(
          (item) =>
            `${relative(item.file)}:${sources.get(item.file)!.slice(0, item.offset).split('\n').length}`,
        )
        .sort(compare);
      for (const item of group)
        add(
          item.file,
          item.offset,
          'css.duplicate-block',
          item.evidence,
          item.context,
          'Review shared styling or Quasar props/utilities',
          'medium',
          `Identical ordered declarations at ${peers.join(', ')}. Do not delete without checking scope, cascade, media conditions and ownership.`,
        );
    }
  report.files = [...sources]
    .map(([file, code]) => ({ file: relative(file), sha256: hash(code) }))
    .sort((a, b) => compare(a.file, b.file));
  report.findings.sort(
    (a, b) =>
      compare(a.file, b.file) ||
      a.line - b.line ||
      a.column - b.column ||
      compare(a.rule, b.rule) ||
      compare(a.id, b.id),
  );
  report.styles.sort(
    (a, b) => compare(a.file, b.file) || a.line - b.line || compare(a.context, b.context),
  );
  report.quasarUsage.sort(
    (a, b) => compare(a.file, b.file) || a.line - b.line || compare(a.component, b.component),
  );
  return report;
}

export function markdown(report: Inventory): string {
  const escape = (value: string) =>
    value
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('|', '&#124;')
      .replaceAll('`', '&#96;')
      .replace(/\r?\n/g, ' ');
  const counts = new Map<string, number>();
  for (const item of report.findings) counts.set(item.rule, (counts.get(item.rule) ?? 0) + 1);
  return [
    '# Quasar normalization candidates',
    '',
    'Generated; do not edit. Candidates are not defects. Manual decisions live in `dispositions.json`, not in this report.',
    '',
    `Scope: ${report.scope}. ${report.files.length} source files; ${report.findings.length} candidates; ${report.quasarUsage.length} existing Quasar component uses.`,
    '',
    '## Limits and migration safeguards',
    '',
    ...report.limitations.map((s) => `- ${s}`),
    '',
    '## Rule counts',
    '',
    ...[...counts].sort(([a], [b]) => compare(a, b)).map(([rule, count]) => `- ${rule}: ${count}`),
    '',
    '## Findings',
    '',
    '| Evidence location / ID | Rule / confidence | Source and context | Suggested equivalent | Migration caution |',
    '| --- | --- | --- | --- | --- |',
    ...report.findings.map(
      (f) =>
        `| ${f.file}:${f.line}:${f.column}<br>${f.id} | ${f.rule} / ${f.confidence} | ${escape(f.evidence)}<br>${escape(f.context)} | ${escape(f.suggestion)} | ${escape(f.caution)} |`,
    ),
    '',
    '## Style coverage and external owners',
    '',
    ...report.styles.map((s) => `- ${s.file}:${s.line} — ${escape(s.context)}`),
    '',
    '## Existing Quasar usage',
    '',
    ...report.quasarUsage.map((u) => `- ${u.file}:${u.line} — ${u.component}`),
    '',
    '## Input manifest (SHA-256)',
    '',
    ...report.files.map((f) => `- ${f.file}: ${f.sha256}`),
    '',
  ].join('\n');
}

export function validateDispositions(value: unknown, findings: Finding[]): void {
  if (!Array.isArray(value)) throw new Error('Dispositions must be an array');
  const ids = new Set(findings.map((f) => f.id));
  const seen = new Set<string>();
  for (const item of value) {
    if (
      !item ||
      typeof item.findingId !== 'string' ||
      !ids.has(item.findingId) ||
      seen.has(item.findingId) ||
      !['approved', 'rejected'].includes(item.disposition)
    )
      throw new Error(
        'Disposition requires a unique current findingId and approved/rejected disposition (legacy decisions need explicit re-review)',
      );
    seen.add(item.findingId);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const args = process.argv.slice(2);
  if (
    args.length > 1 ||
    (args.length === 1 && !['--write', '--markdown', '--check-dispositions'].includes(args[0]!))
  )
    throw new Error(
      'Usage: node frontend/scripts/quasar-audit.mts [--markdown | --write | --check-dispositions]',
    );
  const report = await audit(root);
  const output = path.join(root, 'docs/quasar-audit');
  const json = JSON.stringify(report, null, 2) + '\n';
  if (args[0] === '--write') {
    await mkdir(output, { recursive: true });
    await writeFile(path.join(output, 'inventory.json'), json);
    await writeFile(path.join(output, 'inventory.md'), markdown(report));
    console.log(
      `${report.findings.length} candidates in ${report.files.length} files; wrote docs/quasar-audit/inventory.{json,md}`,
    );
  } else if (args[0] === '--check-dispositions') {
    validateDispositions(
      JSON.parse(await readFile(path.join(output, 'dispositions.json'), 'utf8')),
      report.findings,
    );
    console.log('Manual dispositions are valid against current findings.');
  } else process.stdout.write(args[0] === '--markdown' ? markdown(report) : json);
}
