import { spawn } from 'node:child_process';

const apiCommand = {
  name: 'api',
  command: 'uv',
  args: [
    'run',
    'python',
    '-m',
    'wolven_hunt.cli',
    'serve',
    '--host',
    '127.0.0.1',
    '--port',
    '7002',
  ],
};
const webCommand = {
  name: 'web',
  command: 'npm',
  args: ['run', 'dev'],
};
const commands = [
  ...((await existingApiIsHealthy()) ? [] : [apiCommand]),
  webCommand,
];

if (commands.length === 1) {
  console.log('[dev:api] reusing existing healthy API on http://127.0.0.1:7002');
}

const children = [];
let shuttingDown = false;

for (const { name, command, args } of commands) {
  const child = spawn(command, args, {
    stdio: ['inherit', 'pipe', 'pipe'],
    shell: false,
  });
  children.push(child);
  pipeOutput(child.stdout, name, process.stdout);
  pipeOutput(child.stderr, name, process.stderr);
  child.on('exit', (code, signal) => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    const reason = signal ? `signal ${signal}` : `code ${code ?? 0}`;
    console.error(`[dev:${name}] exited with ${reason}; stopping dev services`);
    stopChildren();
    process.exitCode = code ?? 1;
  });
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    stopChildren();
  });
}

async function existingApiIsHealthy() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 500);
    const response = await fetch('http://127.0.0.1:7002/healthz', {
      cache: 'no-store',
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!response.ok) {
      return false;
    }
    const data = await response.json().catch(() => null);
    return data?.ok === true;
  } catch {
    return false;
  }
}

function pipeOutput(stream, name, target) {
  let pending = '';
  stream.setEncoding('utf8');
  stream.on('data', (chunk) => {
    pending += chunk;
    const lines = pending.split(/\r?\n/);
    pending = lines.pop() ?? '';
    for (const line of lines) {
      target.write(`[dev:${name}] ${line}\n`);
    }
  });
  stream.on('end', () => {
    if (pending) {
      target.write(`[dev:${name}] ${pending}\n`);
    }
  });
}

function stopChildren() {
  for (const child of children) {
    if (!child.killed && child.exitCode === null) {
      child.kill('SIGTERM');
    }
  }
}
