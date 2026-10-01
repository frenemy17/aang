#!/usr/bin/env node

/**
 * Aang CLI — Node.js launcher and npm bridge for the Aang Python engine.
 * Supports npx aang-ai / npm install -g aang-ai.
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const rootDir = path.resolve(__dirname, '..');
const localVenvAang = path.join(rootDir, 'venv', 'bin', 'aang');
const localVenvPython = path.join(rootDir, 'venv', 'bin', 'python');

function findPython() {
  const candidates = ['python3.14', 'python3.13', 'python3.12', 'python3.11', 'python3', 'python'];
  for (const cmd of candidates) {
    try {
      const verOutput = execSync(`${cmd} -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"`, {
        stdio: ['ignore', 'pipe', 'ignore'],
        encoding: 'utf-8'
      }).trim();
      const [major, minor] = verOutput.split('.').map(Number);
      if (major === 3 && minor >= 11) {
        return { cmd, version: verOutput };
      }
    } catch (e) {
      // Continue search
    }
  }
  return null;
}

function runAang() {
  const args = process.argv.slice(2);
  let executable = '';
  let runArgs = [];

  if (fs.existsSync(localVenvAang)) {
    // 1. Direct local repository execution
    executable = localVenvAang;
    runArgs = args;
  } else if (fs.existsSync(localVenvPython)) {
    // 2. Local venv python module run
    executable = localVenvPython;
    runArgs = ['-m', 'aang.main', ...args];
  } else {
    // 3. Global / standalone npm installation
    const py = findPython();
    if (!py) {
      console.error('\x1b[31mError:\x1b[0m Aang requires Python >= 3.11 to run.');
      console.error('Please install Python 3.11+ from https://www.python.org/ or via your package manager.');
      process.exit(1);
    }

    const homeDir = os.homedir();
    const globalEnvDir = path.join(homeDir, '.aang', 'venv');
    const globalAang = path.join(globalEnvDir, 'bin', 'aang');

    if (fs.existsSync(globalAang)) {
      executable = globalAang;
      runArgs = args;
    } else {
      console.log('\x1b[36m⚡ First-time setup: Initializing Aang environment...\x1b[0m');
      try {
        fs.mkdirSync(path.join(homeDir, '.aang'), { recursive: true });
        execSync(`${py.cmd} -m venv "${globalEnvDir}"`, { stdio: 'inherit' });
        const pipCmd = path.join(globalEnvDir, 'bin', 'pip');
        execSync(`"${pipCmd}" install -e "${rootDir}"`, { stdio: 'inherit' });
        executable = globalAang;
        runArgs = args;
        console.log('\x1b[32m✓ Setup complete!\x1b[0m\n');
      } catch (err) {
        console.error('\x1b[31mFailed to bootstrap Aang environment:\x1b[0m', err.message);
        process.exit(1);
      }
    }
  }

  const child = spawn(executable, runArgs, {
    stdio: 'inherit',
    env: process.env
  });

  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
    } else {
      process.exit(code || 0);
    }
  });

  process.on('SIGINT', () => {
    // Forward interrupt to child
    if (child.pid) {
      child.kill('SIGINT');
    }
  });

  process.on('SIGTERM', () => {
    if (child.pid) {
      child.kill('SIGTERM');
    }
  });
}

runAang();
