import { build } from 'esbuild';
import { mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const output = resolve('.test-output');
mkdirSync(output, { recursive: true });
const python = resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const fixtures = spawnSync(python, [resolve('../backend/tests/export_ui_fixtures.py'), resolve(output, 'fixtures.json')], { stdio: 'inherit' });
if (fixtures.error || fixtures.status !== 0) {
  console.error('UI fixtures need the project Python environment. Install requirements-dev.txt first.');
  process.exit(1);
}
await build({ entryPoints: ['tests/workspace.test.jsx'], bundle: true, platform: 'node', format: 'esm',
  packages: 'external', jsx: 'automatic', outfile: resolve(output, 'workspace.test.mjs') });
const tests = spawnSync(process.execPath, ['--test', resolve(output, 'workspace.test.mjs')], { stdio: 'inherit' });
if (tests.status === 0) rmSync(output, { recursive: true, force: true });
process.exit(tests.status ?? 1);
