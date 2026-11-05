#!/usr/bin/env node
'use strict';
// Installs the fresh-context Claude Code plugin from the files in this package:
// copies them to a per-user data folder, registers that folder as a marketplace, installs the plugin.
// No dependencies. Node 18+.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const NAME = 'fresh-context';
const PLUGIN = `${NAME}@${NAME}`;
const REPO = 'madebyalexander/fresh-context';
const PKG_ROOT = path.resolve(__dirname, '..');
const COPY = ['.claude-plugin', 'hooks', 'skills', 'README.md', 'LICENSE', 'CHANGELOG.md', 'package.json'];
const SKIP = new Set(['__pycache__', '.DS_Store', 'node_modules']);
const xdg = process.env.XDG_DATA_HOME;
const DATA_DIR = path.join(xdg && path.isAbsolute(xdg) ? xdg : path.join(os.homedir(), '.local', 'share'), NAME);
const WIN = process.platform === 'win32';

const USAGE = `Usage: npx ${NAME} [install | uninstall] [--dry-run] [--help]

  install     copy the plugin to ${DATA_DIR},
              add it as a marketplace and install ${PLUGIN} (default)
  uninstall   uninstall the plugin, remove the marketplace, delete that folder
  --dry-run   print the steps without doing anything
  --help      show this help

Needs the Claude Code CLI ("claude") on PATH. XDG_DATA_HOME moves the folder.`;

const say = (s) => process.stdout.write(s + '\n');
const fail = (s) => process.stderr.write(`${NAME}: ${s}\n`);

function claude(args, opts = {}) {
  const argv = WIN ? args.map((a) => `"${a}"`) : args;
  return spawnSync('claude', argv, { stdio: 'inherit', shell: WIN, ...opts });
}

function step(args) {
  say(`$ claude ${args.join(' ')}`);
  const r = claude(args);
  if (r.status !== 0) fail(`step failed (exit ${r.status ?? r.error?.code}): claude ${args.join(' ')}`);
  return r.status === 0;
}

// Only ever replace or delete a folder that is empty, missing, or an earlier copy of this plugin.
function ours(dir) {
  if (!fs.existsSync(dir)) return true;
  try {
    const m = JSON.parse(fs.readFileSync(path.join(dir, '.claude-plugin', 'marketplace.json'), 'utf8'));
    return m.name === NAME;
  } catch {
    return fs.readdirSync(dir).length === 0;
  }
}

function copyTree(src, dst) {
  if (fs.statSync(src).isDirectory()) {
    fs.mkdirSync(dst, { recursive: true });
    for (const e of fs.readdirSync(src)) {
      if (!SKIP.has(e) && !e.endsWith('.pyc')) copyTree(path.join(src, e), path.join(dst, e));
    }
  } else {
    fs.copyFileSync(src, dst);
    fs.chmodSync(dst, fs.statSync(src).mode & 0o777);
  }
}

function copyPlugin() {
  if (!ours(DATA_DIR)) throw new Error(`${DATA_DIR} exists and is not a ${NAME} copy; move it away or set XDG_DATA_HOME`);
  const tmp = `${DATA_DIR}.new-${process.pid}`;
  fs.rmSync(tmp, { recursive: true, force: true });
  for (const item of COPY) {
    if (fs.existsSync(path.join(PKG_ROOT, item))) copyTree(path.join(PKG_ROOT, item), path.join(tmp, item));
  }
  fs.rmSync(DATA_DIR, { recursive: true, force: true });
  fs.renameSync(tmp, DATA_DIR);
}

function registered() {
  const r = claude(['plugin', 'marketplace', 'list', '--json'], { stdio: ['ignore', 'pipe', 'ignore'], encoding: 'utf8' });
  try {
    return JSON.parse(r.stdout).find((m) => m.name === NAME) || null;
  } catch {
    return null;
  }
}

function main(argv) {
  const flags = new Set(argv.filter((a) => a.startsWith('-')));
  const cmds = argv.filter((a) => !a.startsWith('-'));
  const cmd = cmds[0] || 'install';
  const knownFlags = ['--dry-run', '--help', '-h'];
  if (flags.has('--help') || flags.has('-h')) return say(USAGE), 0;
  if (cmds.length > 1 || !['install', 'uninstall'].includes(cmd) || [...flags].some((f) => !knownFlags.includes(f))) {
    fail(`unknown arguments: ${argv.join(' ')}`);
    process.stderr.write(USAGE + '\n');
    return 2;
  }

  const plan = cmd === 'install'
    ? [`copy the plugin to ${DATA_DIR} (replacing an older copy)`,
       `claude plugin marketplace add ${DATA_DIR}   (or: claude plugin marketplace update ${NAME}, if already added)`,
       `claude plugin install ${PLUGIN}`]
    : [`claude plugin uninstall ${PLUGIN}`, `claude plugin marketplace remove ${NAME}`, `delete ${DATA_DIR}`];
  if (flags.has('--dry-run')) return say(`${NAME} ${cmd} (dry run), would run:\n  ` + plan.join('\n  ')), 0;

  const probe = claude(['--version'], { stdio: 'ignore' });
  if (probe.error || (WIN && probe.status !== 0)) {
    fail('the claude CLI is not on PATH. Install Claude Code, then run this again, or add the plugin by hand:');
    process.stderr.write(`  claude plugin marketplace add ${REPO}\n  claude plugin install ${PLUGIN}\n`);
    return 1;
  }

  if (cmd === 'uninstall') {
    let okAll = step(['plugin', 'uninstall', PLUGIN]);
    okAll = step(['plugin', 'marketplace', 'remove', NAME]) && okAll;
    if (!fs.existsSync(DATA_DIR)) {
      // nothing to delete
    } else if (ours(DATA_DIR)) {
      fs.rmSync(DATA_DIR, { recursive: true, force: true });
      say(`deleted ${DATA_DIR}`);
    } else {
      fail(`left ${DATA_DIR} in place: it is not a ${NAME} copy`);
      okAll = false;
    }
    return okAll ? 0 : 1;
  }

  try {
    copyPlugin();
  } catch (e) {
    fail(e.message);
    return 1;
  }
  say(`copied the plugin to ${DATA_DIR}`);
  const existing = registered();
  const real = (p) => { try { return fs.realpathSync(p); } catch { return path.resolve(p); } };
  if (existing && !(existing.source === 'directory' && existing.path && real(existing.path) === real(DATA_DIR))) {
    say(`note: marketplace "${NAME}" is already added from ${existing.path || existing.repo || existing.url || existing.source}; updating that one`);
  }
  const added = existing ? step(['plugin', 'marketplace', 'update', NAME]) : step(['plugin', 'marketplace', 'add', DATA_DIR]);
  if (!added || !step(['plugin', 'install', PLUGIN])) return 1;
  say(`Done. Restart Claude Code; commands: /${NAME}:handoff, /${NAME}:tokens`);
  return 0;
}

process.exitCode = main(process.argv.slice(2));
