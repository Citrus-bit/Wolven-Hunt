# STEP-01 大厅首页（Lobby Home）执行规格

> **本规格只覆盖第一步交付：大厅首页**。规则契约见 `plan.md` §1–§6 与 `architecture.md` §1–§16；前端壳契约见 `plan.md` §14 与 `architecture.md` §18。本文件是 GPT 实施手册 + Kiro 验收指标的镜像。
>
> **硬约束**：
>
> 1. 不得修改 `plan.md` §1–§6、`architecture.md` §1–§16；如有冲突先回到上层修订流程。
> 2. 前端代码不得 `import` 任何 `src/wolven_hunt/*`；不得读取 `configs/*`；不得发起 HTTP/WebSocket/SSE 请求。
> 3. 不得改名 / 移动 / 删除 `素材/` 目录下的任何原始文件。
> 4. 所有运行时静态资源命名为 ASCII 小写蛇形。

---

## 1. 交付目标

完成后用户在浏览器打开本地 dev server 应能看到：

1. 大厅首页以「大厅界面_动图」为主视觉，**正放→倒放→正放**无缝循环。
2. 「游戏大厅待机音乐」作为 BGM 循环播放（首次交互后解锁声音）。
3. 大厅下方水平显示三个按钮：**开始游戏 → 历史复盘 → 系统设置**，使用素材中的 PNG 图标。

---

## 2. 资源准备

### 2.1 拷贝资源（保留原始素材不变）

新建目录 `public/assets/lobby/`，按下表拷贝：

| 源 | 目标 |
|---|---|
| `素材/游戏大厅待机音乐.mp3` | `public/assets/lobby/lobby_bgm.mp3` |
| `素材/大厅界面.jpg` | `public/assets/lobby/lobby_poster.jpg` |
| `素材/开始游戏_按钮.png` | `public/assets/lobby/btn_start.png` |
| `素材/历史复盘_按钮.png` | `public/assets/lobby/btn_history.png` |
| `素材/系统设置_按钮.png` | `public/assets/lobby/btn_settings.png` |

### 2.2 ping-pong 视频构建脚本（跨平台 Node 版本）

> 本节自 STEP-01b 起改为 Node.js 跨平台脚本。脚本不依赖系统 ffmpeg，也不依赖 bash。详细修订规格见 `docs/specs/STEP-01b-cross-platform-ffmpeg.md`。

新建 `scripts/build-lobby-pingpong.mjs`，写入：

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

通过 `npm install ffmpeg-static@^5.2.0 -D` 安装跨平台 ffmpeg，然后执行 `npm run assets:lobby` 生成 `public/assets/lobby/lobby_pingpong.mp4`。无需系统 ffmpeg；`ffmpeg-static` 已覆盖 Linux / macOS / Windows × x64 / arm64。

---

## 3. 前端骨架文件

### 3.1 `package.json`

最小依赖（版本可酌情升级，但保持主版本一致）：

- dependencies: `react@^18`, `react-dom@^18`, `lucide-react@^0.460`
- devDependencies: `vite@^5`, `@vitejs/plugin-react@^4`, `typescript@^5`, `@types/react@^18`, `@types/react-dom@^18`, `ffmpeg-static@^5.2.0`
- scripts:
  - `dev`: `vite`
  - `build`: `tsc -b && vite build`
  - `preview`: `vite preview`
  - `typecheck`: `tsc --noEmit`
  - `assets:lobby`: `node scripts/build-lobby-pingpong.mjs`

执行 `npm install` 后生成的 `package-lock.json` 是前端入口壳的一部分，必须保留。

### 3.2 `vite.config.ts`

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
});
```

### 3.3 `tsconfig.json` / `tsconfig.node.json`

标准 React + TS strict 模板（`"strict": true`、`"jsx": "react-jsx"`、`"moduleResolution": "bundler"`）。`tsconfig.node.json` 仅覆盖 `vite.config.ts`。

### 3.4 `index.html`

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Wolven Hunt 大厅</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

### 3.5 入口

- `src/main.tsx`：`createRoot(document.getElementById('root')!).render(<App />)`，引入 `./styles.css`。
- `src/App.tsx`：渲染 `<LobbyHome />`。
- `src/styles.css`：全局重置 + 大厅布局基础样式（无外部 CSS 框架）。

---

## 4. 大厅组件契约

### 4.1 `src/components/Lobby/LobbyHome.tsx`

- 组合 `LobbyVideo` + `LobbyButtons` + `MuteToggle`。
- 通过 `useLobbyAudio()` 获取 `{ muted, toggleMute, ensureUnlock }`。
- 监听全文档**首次** `pointerdown` 与 `keydown`，调用 `ensureUnlock()` 解锁 BGM；解锁后移除监听。
- 布局：
  - 全屏背景层是视频。
  - 底部水平居中放按钮组（`bottom: 6vh`）。
  - 右上角浮动 `MuteToggle`（`top: 16px; right: 16px`）。

### 4.2 `src/components/Lobby/LobbyVideo.tsx`

```tsx
<video
  src="/assets/lobby/lobby_pingpong.mp4"
  poster="/assets/lobby/lobby_poster.jpg"
  autoPlay
  muted
  loop
  playsInline
  preload="auto"
  aria-hidden="true"
  className="lobby-video"
/>
```

样式：`position: fixed; inset: 0; width: 100vw; height: 100vh; object-fit: cover; z-index: 0;`。

### 4.3 `src/components/Lobby/LobbyButtons.tsx`

- 接受 `onAction?: (kind: 'start' | 'history' | 'settings') => void`。
- 渲染顺序固定：`开始游戏` → `历史复盘` → `系统设置`。
- 每个按钮：

  ```tsx
  <button
    type="button"
    aria-label="开始游戏"
    className="lobby-btn"
    onClick={() => { console.log('[lobby] click: start'); onAction?.('start'); }}
  >
    <img src="/assets/lobby/btn_start.png" alt="开始游戏" />
  </button>
  ```

- 样式要求：
  - hover：`transform: scale(1.03); filter: brightness(1.1);`
  - active：`transform: scale(0.98);`
  - focus-visible：可见 outline。
  - 三按钮在视口宽度 ≥ 1024px 显示原比例；640–1024 等比缩放；< 640 仍单行三按钮，按比例缩小。

### 4.4 `src/components/Lobby/MuteToggle.tsx`

- 使用 `lucide-react` 的 `Volume2` / `VolumeX`。
- 从 `useLobbyAudio()` 取 `{ muted, toggleMute }`，点击 `toggleMute()`。
- `aria-label` 在 muted 时为「开启声音」，否则为「静音」。
- 样式：圆角矩形 / 圆形按钮，半透明背景 `rgba(0,0,0,0.4)`，hover 加亮。

### 4.5 `src/hooks/useLobbyAudio.ts`

- 模块级单例：

  ```ts
  let audio: HTMLAudioElement | null = null;
  function getAudio() {
    if (!audio) {
      audio = new Audio('/assets/lobby/lobby_bgm.mp3');
      audio.loop = true;
      audio.preload = 'auto';
      audio.muted = true;
    }
    return audio;
  }
  ```

- Hook 暴露 `{ muted, toggleMute, ensureUnlock }`：
  - `muted`：React state，初始 `true`。
  - `ensureUnlock()`：第一次调用时
    - `audio.muted = false`
    - `audio.play().catch((e) => { console.warn('[lobby] BGM unlock failed', e); audio!.muted = true; })`
    - 成功后 `setMuted(false)`。
  - `toggleMute()`：切换 `audio.muted`，同步 React state；首次切换时若未 play 也尝试 `audio.play()`。
- Hook 在 `useEffect` 中确保第一次渲染时调用 `audio.play()`（muted 状态下浏览器允许自动播放）。

---

## 5. 实施顺序

1. 写 `package.json` / `vite.config.ts` / `tsconfig*.json` / `index.html` / `src/main.tsx` / `src/App.tsx` / `src/styles.css`。
2. 创建 `public/assets/lobby/` 并执行 §2.1 资源拷贝。
3. 执行 `node scripts/build-lobby-pingpong.mjs`（或 `npm run assets:lobby`）生成 ping-pong 视频。
4. 实现 `useLobbyAudio` → `MuteToggle` → `LobbyVideo` → `LobbyButtons` → `LobbyHome`。
5. `npm install && npm run typecheck && npm run dev`，本地校验。
6. `npm run build`，确认 `dist/` 产物干净；`npm run preview` 可访问。

---

## 6. 验收指标（Kiro 逐条 check）

> 全部命中即通过。验收命令均在仓库根目录执行。

### A. 项目基准同步

- A1. `plan.md` 已新增 §14「前端入口骨架（Web Lobby Shell）」，且与 §1–§6 规则契约不冲突。
- A2. `plan.md` §7 目录树更新，包含 `package.json` / `index.html` / `public/assets/lobby/` / `docs/specs/`。
- A2a. `plan.md` / `architecture.md` 已声明 `package-lock.json`，且锁文件与 `package.json` 同步存在。
- A3. `architecture.md` 已新增 §18「Web Shell Boundary」，措辞与 plan §14 等价。
- A4. 本文件 `docs/specs/STEP-01-lobby-home.md` 与 plan §14 一致。

### B. 资源

- B1. `public/assets/lobby/lobby_pingpong.mp4`、`lobby_bgm.mp3`、`btn_start.png`、`btn_history.png`、`btn_settings.png`、`lobby_poster.jpg` 全部存在，文件名 **ASCII**。
- B2. `素材/` 原文件未被改名 / 删除。
- B3. `scripts/build-lobby-pingpong.mjs` 在零依赖（无系统 ffmpeg）的 macOS / Linux / Windows 上均可执行成功；`ffprobe` 显示 `public/assets/lobby/lobby_pingpong.mp4` 时长 ≈ 原片 × 2，无音轨。

### C. 构建

- C1. `npm install` 干净跑通，无阻断性 unmet peer warning。
- C2. `npm run dev` 启动无报错；浏览器打开 lobby 页可见。
- C3. `npm run build` 成功；`npm run preview` 可独立访问。
- C4. `npm run typecheck`（`tsc --noEmit`）零错误。

### D. 大厅视频

- D1. 页面打开 ≤ 2s 视频开始播放；首屏背景占满视口（cover）。
- D2. 第一轮：从首帧正向播到末帧（视觉上等同原片）。
- D3. 第二轮：从末帧倒回首帧（连续，**无 ended 黑屏 / 暂停闪烁**）。
- D4. 第三轮起回到正向，循环至少 3 个完整回合无视觉割裂。
- D5. 海报 `lobby_poster.jpg` 在视频缓冲时显示，不阻塞布局。
- D6. macOS Chrome / Safari 均能播放（Firefox 推荐通过）。

### E. BGM

- E1. 初始进入页面，无 console autoplay error。
- E2. 任何首次点击 / 键入后，`lobby_bgm.mp3` 开始播放并循环。
- E3. 右上角 mute 按钮可在「有声 / 静音」之间切换，图标随状态变更。
- E4. 切换页签 / 重新激活 tab，音频不崩溃。

### F. 按钮

- F1. 大厅下方水平显示三个按钮，顺序：开始游戏 → 历史复盘 → 系统设置。
- F2. 三张 PNG 图片可见、无拉伸畸变；按钮可点击区域与图片可见区域一致。
- F3. 鼠标 hover 有放大 / 高亮反馈；`:active` 有按下反馈。
- F4. 键盘 Tab 可依次聚焦三个按钮；focus ring 可见；Enter / Space 触发点击。
- F5. 点击三个按钮后浏览器 Console 各打印一行：`[lobby] click: start|history|settings`。
- F6. `aria-label` 为中文按钮名。

### G. 边界 / 代码质量

- G1. `src/components/Lobby/**` 与 `src/hooks/**` 不 import 任何 `wolven_hunt/*`、不读 `configs/*`、不发起网络请求。
- G2. 大厅页代码内不包含 RNG / 规则 / 角色 / 投票 / FSM 关键字（grep 检查）。
- G3. 浏览器 Console 在正常流程（首次进入 + 解锁 BGM + 三按钮各点一次）无 error / warning。

### H. 一致性

- H1. plan.md 与 architecture.md 中关于 Web Shell 的描述无字面冲突。
- H2. 本文件与 plan §14 描述一致。
- H3. 本步骤未引入 plan.md / architecture.md 未声明的目录或顶层文件。

---

## 7. Kiro 验收命令清单

```bash
# A. 基准同步
git diff plan.md architecture.md
sed -n '/## 14/,/## 15\|^---$/p' plan.md
sed -n '/## 18/,$p' architecture.md
test -f docs/specs/STEP-01-lobby-home.md

# B. 资源
ls -la public/assets/lobby/
ls -la 素材/
npm run assets:lobby   # 内部即 `node scripts/build-lobby-pingpong.mjs`
ffprobe -v error -show_entries format=duration -of default=nw=1 public/assets/lobby/lobby_pingpong.mp4

# C. 构建
npm install
npm run typecheck
npm run build
# npm run dev → 浏览器手测 D / E / F

# G. 边界
grep -RInE "wolven_hunt|RuleEngine|Referee|FSM|random\(|seed|vote|role" src/components src/hooks || true
grep -RInE "fetch\(|axios|XMLHttpRequest|WebSocket|EventSource" src/components src/hooks || true
```

---

## 8. 不在本步骤范围

- FastAPI / 引擎接入 / 真实 LLM。
- 路由（react-router）、按钮二级页。
- 国际化、主题、深色模式。
- PWA / SSR。
- 单元测试（前端测试在后续步骤）。

## 9. 验收报告输出

Kiro 验收完成后，产出 `docs/specs/STEP-01-lobby-home.acceptance.md`，对每个 ID（A1–H3）标注 `pass` / `fail` 与简短证据（截图路径、命令输出片段）。任意 `fail` 即整体不通过，需返工。
