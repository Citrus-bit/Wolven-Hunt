# STEP-01 / STEP-01b 大厅首页验收报告

验收时间：2026-05-21

## Summary

当前结论：pass。STEP-01b 已把系统 ffmpeg/bash 依赖替换为 `ffmpeg-static` + Node 脚本；`public/assets/lobby/lobby_pingpong.mp4` 已生成并可由 dev server 以 `video/mp4` 返回。原 STEP-01 的 A–H 与 STEP-01b 的 I1–I11 均已复测通过。

截图：`docs/specs/step-01b-lobby-screenshot.png`

## STEP-01 A-H

| ID | Status | Evidence |
|---|---|---|
| A1 | pass | `plan.md` 已有 §14「前端入口骨架（Web Lobby Shell）」，未修改 §1–§6。 |
| A2 | pass | `plan.md` §7 包含 `package.json`、`index.html`、`public/assets/lobby/`、`docs/specs/`。 |
| A2a | pass | `plan.md` / `architecture.md` 已声明 `package-lock.json`；`package.json` 与 `package-lock.json` 均存在。 |
| A3 | pass | `architecture.md` 已有 §18「Web Shell Boundary」。 |
| A4 | pass | `docs/specs/STEP-01-lobby-home.md` 已更新到 STEP-01b 的 `.mjs` / `ffmpeg-static` 版本。 |
| B1 | pass | `public/assets/lobby/` 包含 `lobby_pingpong.mp4`、`lobby_bgm.mp3`、`btn_start.png`、`btn_history.png`、`btn_settings.png`、`lobby_poster.jpg`。 |
| B2 | pass | `素材/` 原文件仍存在；实施过程只复制或读取素材，不改名、不移动、不删除。 |
| B3 | pass | `npm run assets:lobby` 成功输出 `[lobby] generated public/assets/lobby/lobby_pingpong.mp4`；静态 ffmpeg 读到目标时长 `00:00:10.08` 且无 `Audio:` 流。 |
| C1 | pass | `npm install ffmpeg-static@^5.2.0 -D` 成功，无阻断性 unmet peer warning。`npm audit` 仍有 Vite/esbuild moderate dev-server advisory，修复需 Vite 8 breaking upgrade，未在本步骤处理。 |
| C2 | pass | `npm run dev -- --host 127.0.0.1 --port 5173` 运行中；`curl -I /assets/lobby/lobby_pingpong.mp4` 返回 `Content-Type: video/mp4`。 |
| C3 | pass | `npm run build` 成功。 |
| C4 | pass | `npm run typecheck` 成功。 |
| D1 | pass | 浏览器中 `video.readyState=4`、`paused=false`，页面加载后视频正在播放。 |
| D2 | pass | 目标视频由原片正向段 + reverse 段 concat 生成；浏览器读到 `duration=10.08`。 |
| D3 | pass | 预生成单段 MP4，运行时 `<video loop>`，无 runtime reverse seek。 |
| D4 | pass | 视频 `loop=true` 且单段 ping-pong 文件可循环。 |
| D5 | pass | `<video poster="/assets/lobby/lobby_poster.jpg">`，海报资源 HTTP 200。 |
| D6 | pass | Chromium in-app browser 可播放；macOS Safari 未自动化复测。 |
| E1 | pass | 页面应用日志无 autoplay error；muted autoplay 失败路径被静默捕获。 |
| E2 | pass | 首次按钮点击后静音按钮从「开启声音」变为「静音」，说明 BGM 解锁状态已同步。 |
| E3 | pass | 点击 mute 后 aria-label 从「静音」切回「开启声音」。 |
| E4 | pass | 基础切换复测无崩溃；未做长时间页签恢复压测。 |
| F1 | pass | DOM 顺序：开始游戏 → 历史复盘 → 系统设置。 |
| F2 | pass | 三个按钮图片 src 分别为 `btn_start.png`、`btn_history.png`、`btn_settings.png`，截图可见。 |
| F3 | pass | CSS 定义 hover scale/brightness 与 active scale。 |
| F4 | pass | 原生 `<button>`，focus-visible outline 已定义。 |
| F5 | pass | 浏览器 console 捕获 `[lobby] click: start`、`history`、`settings`。 |
| F6 | pass | 三个按钮 `aria-label` 与图片 `alt` 均为中文按钮名。 |
| G1 | pass | `grep -RInE "fetch\(|axios|XMLHttpRequest|WebSocket|EventSource" src/components src/hooks` 无输出。 |
| G2 | pass | `grep -RInE "wolven_hunt|RuleEngine|Referee|FSM|random\(|seed|vote|role" src/components src/hooks` 无输出。 |
| G3 | pass | 应用正常流程无 error/warning；dev 模式仅有 Vite debug 与 React DevTools info。 |
| H1 | pass | `plan.md` §14 与 `architecture.md` §18 的 Web Shell 描述一致。 |
| H2 | pass | STEP-01 与 `plan.md` §14 已同步到 `.mjs` / `ffmpeg-static` 版本。 |
| H3 | pass | 新增顶层文件/目录已在 `plan.md` / `architecture.md` 声明；`node_modules/` 已加入 `.gitignore`。 |

## STEP-01b I1-I11

| ID | Status | Evidence |
|---|---|---|
| I1 | pass | `test ! -f scripts/build-lobby-pingpong.sh` 通过。 |
| I2 | pass | `scripts/build-lobby-pingpong.mjs` 首行为 `#!/usr/bin/env node`，含 `import ffmpegPath from 'ffmpeg-static'`。 |
| I3 | pass | `package.json` 中 `ffmpeg-static` 为 `^5.3.0`；`assets:lobby` 为 `node scripts/build-lobby-pingpong.mjs`。 |
| I4 | pass | `package-lock.json` 包含 `node_modules/ffmpeg-static`。 |
| I5 | pass | CommonJS 与 ESM 导入均输出 `node_modules/ffmpeg-static/ffmpeg` 路径。 |
| I6 | pass | `npm run assets:lobby` 不依赖系统 ffmpeg，退出码 0。 |
| I7 | pass | `public/assets/lobby/lobby_pingpong.mp4` 存在；`git ls-files public/assets/lobby/lobby_pingpong.mp4` 命中。 |
| I8 | pass | 静态 ffmpeg 读取目标：`Duration: 00:00:10.08`，输出无 `Audio:`；原片 `Duration: 00:00:05.04`。 |
| I9 | pass | `.gitignore` 对 `lobby_pingpong` / `/assets/lobby` 无匹配。 |
| I10 | pass | `plan.md`、`architecture.md`、STEP-01 文档均已更新到 `.mjs` 脚本和 `ffmpeg-static` 契约。 |
| I11 | pass | in-app browser 复测：视频播放、按钮 console、静音切换通过；截图已保存。 |

## Commands

```text
npm install ffmpeg-static@^5.2.0 -D
node -e "console.log(require('ffmpeg-static'))"
node -e "import('ffmpeg-static').then(m => console.log(m.default))"
test ! -f scripts/build-lobby-pingpong.sh
head -1 scripts/build-lobby-pingpong.mjs
grep -n "ffmpeg-static" package.json package-lock.json scripts/build-lobby-pingpong.mjs
npm run assets:lobby
FFMPEG_BIN=$(node -e "console.log(require('ffmpeg-static'))")
"$FFMPEG_BIN" -hide_banner -i public/assets/lobby/lobby_pingpong.mp4
"$FFMPEG_BIN" -hide_banner -i 素材/大厅界面_动图.mp4
npm run typecheck
npm run build
grep -RInE "wolven_hunt|RuleEngine|Referee|FSM|random\(|seed|vote|role" src/components src/hooks || true
grep -RInE "fetch\(|axios|XMLHttpRequest|WebSocket|EventSource" src/components src/hooks || true
git diff --check
```
