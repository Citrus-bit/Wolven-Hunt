# STEP-01b 跨平台 ffmpeg 修订

> 本文件是 `STEP-01-lobby-home.md` 的修订交付包。原文 §2.2 / §3.1 / §6 B3 已被 STEP-01b 覆盖；GPT 实施时以本文件为准，不要回到 STEP-01 旧版 bash 脚本。
>
> 上层契约见 `plan.md` §14.4 / §14.8 与 `architecture.md` §18.3。

## 1. 触发原因

STEP-01 验收 B3 / D1–D6 全部 fail：`public/assets/lobby/lobby_pingpong.mp4` 没生成。原因是 `scripts/build-lobby-pingpong.sh` 依赖系统 ffmpeg + bash，本机和大量贡献者环境（尤其 Windows）都不一定有这两样东西。项目要开源，必须做到 `git clone && npm install && npm run dev` 即开即用。

## 2. 修订决策

- **跨平台 ffmpeg 来源**：用 npm devDependency `ffmpeg-static@^5.2.0`，覆盖 darwin-arm64 / darwin-x64 / linux-x64 / linux-arm64 / win32-x64。
- **构建脚本语言**：从 bash 切到 Node.js（`scripts/build-lobby-pingpong.mjs`），跨三大操作系统行为一致。
- **产物入 git**：`public/assets/lobby/lobby_pingpong.mp4`（约 5MB）随仓库提交，clone 后无需跑脚本即可启动；脚本只在替换素材时重跑。
- **不引入 Docker**：ffmpeg-static 已覆盖三大平台，再加 Docker 会增加贡献者门槛。

## 3. 文件操作清单

| 操作 | 路径 | 说明 |
|---|---|---|
| 删除 | `scripts/build-lobby-pingpong.sh` | 旧 bash 脚本，被 .mjs 取代 |
| 新建 | `scripts/build-lobby-pingpong.mjs` | 跨平台 Node 脚本（见 §4） |
| 修改 | `package.json` | 增加 `ffmpeg-static` devDep；`scripts.assets:lobby` → `node scripts/build-lobby-pingpong.mjs` |
| 修改 | `package-lock.json` | 由 `npm install` 自动更新 |
| 新建（脚本生成） | `public/assets/lobby/lobby_pingpong.mp4` | ping-pong 产物，约 5MB，需 `git add` |
| 不变 | `.gitignore` | 不要忽略 `public/assets/lobby/*.mp4` |

## 4. `scripts/build-lobby-pingpong.mjs` 内容契约

```js
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
  '-i', IN,
  '-filter_complex', '[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0,format=yuv420p[v]',
  '-map', '[v]',
  '-an',
  '-movflags', '+faststart',
  '-c:v', 'libx264',
  '-preset', 'slow',
  '-crf', '22',
  OUT,
];

const result = spawnSync(ffmpegPath, args, { stdio: 'inherit' });
if (result.status !== 0) {
  console.error(`[lobby] ffmpeg exited with code ${result.status}`);
  process.exit(result.status ?? 1);
}
console.log(`[lobby] generated ${OUT}`);
```

要点：

- `import ffmpegPath from 'ffmpeg-static'`：拿到二进制路径，无需 PATH。
- `process.argv[2]/[3]`：默认输入 `素材/大厅界面_动图.mp4`、默认输出 `public/assets/lobby/lobby_pingpong.mp4`，可通过命令行覆盖。
- `mkdirSync(..., { recursive: true })`：确保目录存在。
- `spawnSync(ffmpegPath, args, { stdio: 'inherit' })`：把 ffmpeg 输出原样透传到终端。
- shebang 仅作提示；调用方式固定为 `node scripts/build-lobby-pingpong.mjs`，不依赖 chmod。

## 5. `package.json` 变更

```jsonc
{
  "scripts": {
    "assets:lobby": "node scripts/build-lobby-pingpong.mjs"
  },
  "devDependencies": {
    "ffmpeg-static": "^5.2.0"
  }
}
```

执行 `npm install ffmpeg-static@^5.2.0 -D`，让 npm 自动更新 `package.json` 与 `package-lock.json`，然后手动把 `scripts.assets:lobby` 调整为新值。其余字段保持不变。

## 6. 实施顺序

1. 删除 `scripts/build-lobby-pingpong.sh`。
2. 新建 `scripts/build-lobby-pingpong.mjs`（§4 内容）。
3. 执行 `npm install ffmpeg-static@^5.2.0 -D`，确保 `package-lock.json` 同步更新。
4. 修改 `package.json` 的 `scripts.assets:lobby` 为 `node scripts/build-lobby-pingpong.mjs`。
5. 执行 `npm run assets:lobby`，生成 `public/assets/lobby/lobby_pingpong.mp4`。
6. `npm run typecheck && npm run build && npm run preview`，浏览器手测 D / E / F。
7. `git add scripts/build-lobby-pingpong.mjs package.json package-lock.json public/assets/lobby/lobby_pingpong.mp4` 并 `git rm scripts/build-lobby-pingpong.sh`，等待 Kiro 验收后提交。

## 7. 增量验收指标 I（叠加在 STEP-01 §6 A–H 之上）

- **I1**. `scripts/build-lobby-pingpong.sh` 已删除，仓库内不存在该文件。
- **I2**. `scripts/build-lobby-pingpong.mjs` 存在；首行 `#!/usr/bin/env node`；含 `import ffmpegPath from 'ffmpeg-static'`。
- **I3**. `package.json.devDependencies['ffmpeg-static']` 存在，版本 `^5.2.0` 或更高；`scripts['assets:lobby']` 等于 `node scripts/build-lobby-pingpong.mjs`。
- **I4**. `package-lock.json` 包含 `ffmpeg-static` 条目（`grep '"ffmpeg-static"' package-lock.json` 命中）。
- **I5**. `node_modules/ffmpeg-static/` 已安装；`node -e "console.log(require('ffmpeg-static'))"` 输出非 null 路径，且 `node -e "import('ffmpeg-static').then(m => console.log(m.default))"` 也可工作。
- **I6**. 在不依赖系统 ffmpeg 的前提下（`command -v ffmpeg` 失败也不影响），`npm run assets:lobby` 退出码为 0，最后一行包含 `[lobby] generated public/assets/lobby/lobby_pingpong.mp4`。
- **I7**. `public/assets/lobby/lobby_pingpong.mp4` 存在；`git ls-files public/assets/lobby/lobby_pingpong.mp4` 命中（已 tracked / 准备 commit）。
- **I8**. 用 `node -e "console.log(require('ffmpeg-static'))"` 拿到二进制，`<bin> -hide_banner -i public/assets/lobby/lobby_pingpong.mp4` 可读到 `Duration:`，输出无 `Audio:` 流；时长 ≈ 原片 × 2（误差 ±0.5s 可接受）。
- **I9**. `.gitignore` 未把 `public/assets/lobby/*.mp4` 加进去（`grep -n "lobby_pingpong\|/assets/lobby" .gitignore` 应为空）。
- **I10**. `plan.md` §14.4 / §14.8 / §7 目录树 与 `architecture.md` §18.3 已与本规格一致；`docs/specs/STEP-01-lobby-home.md` §2.2 / §3.1 scripts / §5 / §6 B3 / §7 验收命令均已更新到 `.mjs` 版本。
- **I11**. 重测原 D1–D6（视频播放）：之前因 mp4 缺失全 fail，本次需在浏览器中重新逐条复测并通过。

通过条件：原 STEP-01 §6 A–H + 本节 I1–I11 全部 pass。

## 8. Kiro 验收命令清单

```bash
# I1–I5 静态检查
test ! -f scripts/build-lobby-pingpong.sh
head -1 scripts/build-lobby-pingpong.mjs
grep -n "ffmpeg-static" package.json package-lock.json scripts/build-lobby-pingpong.mjs
node -e "console.log(require('ffmpeg-static'))"

# I6 跨平台脚本运行
unset PATH_HAS_FFMPEG; command -v ffmpeg || true
npm run assets:lobby

# I7–I9 产物与 .gitignore
git ls-files public/assets/lobby/lobby_pingpong.mp4
grep -n "lobby_pingpong\|/assets/lobby" .gitignore || echo "ok: .gitignore clean"

# I8 视频元数据
FFMPEG_BIN=$(node -e "console.log(require('ffmpeg-static'))")
"$FFMPEG_BIN" -hide_banner -i public/assets/lobby/lobby_pingpong.mp4 2>&1 | head -30
"$FFMPEG_BIN" -hide_banner -i 素材/大厅界面_动图.mp4 2>&1 | head -10

# I11 浏览器手测
npm run dev
# → 浏览器观察 D1–D6 / E1–E4 / F1–F6
```

## 9. 不在范围

- Dockerfile / docker-compose
- CI 自动重生成 ping-pong
- 替换素材的贡献者文档（等 STEP-02 一起补 README）
- 任何 Python 引擎、FastAPI、LLM 改动

## 10. 验收后产出

I1–I11 + 原 A–H 全 pass 后，由 Kiro 写入 `docs/specs/STEP-01-lobby-home.acceptance.md`：
- 全表 pass/fail 记录 + 命令输出片段 / 浏览器截图引用。
- 任何 fail 即整体不通过，回到 §6 实施顺序对应步骤返工。
