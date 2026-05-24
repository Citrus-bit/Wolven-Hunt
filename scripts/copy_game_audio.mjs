import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import ffmpegPath from 'ffmpeg-static';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const sourceDir = join(root, '素材');
const targetDir = join(root, 'public', 'assets', 'game');
const lobbyBgm = join(root, 'public', 'assets', 'lobby', 'lobby_bgm.mp3');

const assets = [
  ['wolf_howl', 'audio', '狼嚎.mp3', 'audio/wolf_howl.mp3', 2200],
  ['night_guard', 'audio', '天黑了，守卫请睁眼.mp3', 'audio/night_guard.mp3', 2800],
  ['night_wolves', 'audio', '狼人请睁眼.mp3', 'audio/night_wolves.mp3', 2500],
  ['night_witch', 'audio', '女巫请睁眼.mp3', 'audio/night_witch.mp3', 2500],
  ['night_seer', 'audio', '预言家请睁眼.mp3', 'audio/night_seer.mp3', 2600],
  ['day_rooster', 'audio', '鸡鸣.mp3', 'audio/day_rooster.mp3', 1800],
  ['day_dawn', 'audio', '天,亮了.mp3', 'audio/day_dawn.mp3', 1800],
  ['day_death', 'audio', '昨晚,他死了.mp3', 'audio/day_death.mp3', 2500],
  ['day_peaceful', 'audio', '昨晚,是平安夜.mp3', 'audio/day_peaceful.mp3', 2500],
];

const effectAssets = [
  ['guard_shield', 'image', '守卫的护盾.png', 'effects/guard_shield.png'],
  ['wolf_attack', 'image', '狼人袭击.png', 'effects/wolf_attack.png'],
  ['seer_vision', 'image', '预言.png', 'effects/seer_vision.png'],
  ['potion_antidote', 'image', '女巫的解药.png', 'effects/potion_antidote.png'],
  ['potion_poison', 'image', '女巫的毒药.png', 'effects/potion_poison.png'],
  ['out_badge', 'image', 'OUT.png', 'effects/out_badge.png'],
];

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function copyIfChanged(source, target) {
  mkdirSync(dirname(target), { recursive: true });
  if (existsSync(target) && sha256(source) === sha256(target)) {
    return;
  }
  copyFileSync(source, target);
}

function durationMs(path, fallback) {
  if (!ffmpegPath) {
    return fallback;
  }
  const result = spawnSync(ffmpegPath, ['-i', path], { encoding: 'utf8' });
  const output = `${result.stdout || ''}\n${result.stderr || ''}`;
  const match = output.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
  if (!match) {
    return fallback;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  return Math.round((hours * 3600 + minutes * 60 + seconds) * 1000);
}

const manifest = {};

for (const [key, kind, sourceName, targetName, fallbackDuration] of assets) {
  const source = join(sourceDir, sourceName);
  const target = join(targetDir, targetName);
  copyIfChanged(source, target);
  manifest[key] = {
    key,
    kind,
    path: `/assets/game/${targetName}`,
    duration_ms: durationMs(target, fallbackDuration),
    source_sha256: sha256(source),
    target_sha256: sha256(target),
  };
}

if (!existsSync(lobbyBgm)) {
  copyIfChanged(join(sourceDir, '游戏大厅待机音乐.mp3'), lobbyBgm);
}

writeFileSync(
  join(targetDir, 'audio_manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8',
);

const effectManifest = {};

for (const [key, kind, sourceName, targetName] of effectAssets) {
  const source = join(sourceDir, sourceName);
  const target = join(targetDir, targetName);
  copyIfChanged(source, target);
  effectManifest[key] = {
    key,
    kind,
    path: `/assets/game/${targetName}`,
    source_sha256: sha256(source),
    target_sha256: sha256(target),
  };
}

writeFileSync(
  join(targetDir, 'effect_manifest.json'),
  `${JSON.stringify(effectManifest, null, 2)}\n`,
  'utf8',
);
