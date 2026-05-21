#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import ffmpegPath from 'ffmpeg-static';

const IN = process.argv[2] ?? '素材/大厅界面_动图.mp4';
const OUT = process.argv[3] ?? 'public/assets/lobby/lobby_pingpong.mp4';

if (!ffmpegPath) {
  console.error('[lobby] ffmpeg-static did not provide a binary for this platform.');
  console.error('  Run `npm install` first; if it persists, check ffmpeg-static support for your OS/arch.');
  process.exit(1);
}

mkdirSync(path.dirname(OUT), { recursive: true });

const args = [
  '-y',
  '-i',
  IN,
  '-filter_complex',
  '[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0,format=yuv420p[v]',
  '-map',
  '[v]',
  '-an',
  '-movflags',
  '+faststart',
  '-c:v',
  'libx264',
  '-preset',
  'slow',
  '-crf',
  '22',
  OUT,
];

const result = spawnSync(ffmpegPath, args, { stdio: 'inherit' });
if (result.status !== 0) {
  console.error(`[lobby] ffmpeg exited with code ${result.status}`);
  process.exit(result.status ?? 1);
}
console.log(`[lobby] generated ${OUT}`);
