# 神职夜晚特效不显示 — 诊断 & 修复 Plan

## Context

需求：守卫护盾 / 狼人袭击 / 预言家查验 / 女巫毒&解药 四个夜晚特效要在前端席位上呈现（图标贴在头像上 / 砸瓶动画 / 持续时长按规则）。

现状（我把后端→SSE→前端一路看完了）：**所有线都已经接通**，代码层面没有缺件：

- 后端 `src/wolven_hunt/storage/spectator_effects.py` 在 `GUARD_PROTECT / WOLF_KILL_DECIDED / SEER_CHECK / WITCH_ACTION / DAY_ANNOUNCE` 上正确产出 `SpectatorEffect`。我看了最新 run `runs/e716aa85…/events.jsonl`，五种事件都按时序生成了。
- `runtime.GameSession.publish_event` 在 `event_log.append` 回调里调用 `event_to_spectator_effects(event, self.event_log.events)` 并把 dict 写进 `_effect_rows`。
- `api/sse.py` 第 32–33 行在每个 raw_event 后 `for effect in session.effect_rows_for_seq(cursor): yield "spectator_effect" event`，与 `game_event` 同流出。
- `lib/gameApi.ts` 的 `subscribeGameEvents` 已经监听 `spectator_effect`。
- `GamePage` 把它喂进 `setSpectatorEffects` + `setRecentEffects`，分别驱动席位贴附特效（`buildSeatEffectMap` → `GameSeat`）和飞行/横幅（`GameEffectsLayer`）。
- `public/assets/game/effects/*` 六张图都在；`d29bb5d` 之后 `dist/` 也已经有这些资源。
- CSS 关键帧 `game-effect-guard-pulse / wolf-strike / seer-flash / potion-flight / potion-burst / out-pop` 全部在 `styles.css:1920–2240`。
- 现有 `tests/frontend/gameEffects*.test.*` 都在覆盖 happy path，且通过。

**所以"没看到"99% 不是缺实现，而是端到端运行链路上某一处把它们吞掉了。** 这个 plan 的目标是先做差异性诊断，定位到真因再动手，而不是再写第四版方案。

下面把 GPT 三轮没解决的最可能根因从高到低列出，并给出"先验证后修"的执行步骤。

---

## 最可能的真因（按概率排序）

### A. dist 缓存 / 跑的根本不是新代码（最常见）
后端 `api/app.py:70` 在 dist 存在时 `app.mount("/", StaticFiles(directory=dist_dir, html=True))`。如果用户访问的是 7002 端口（FastAPI），它服务的是 `dist/`。`dist/assets/` 里的 JS 是上一次 `npm run build` 的产物，d29bb5d 的 React 代码改动如果没有重新 build 就根本没进 bundle。
- **观察现象**：浏览器 DevTools → Sources，搜索 `GameEffectsLayer` 或 `game-effect-flight`，如果没有 → 是旧 bundle。
- **验证**：`grep -r "activeRecentEffectAnnouncements" /Users/tampouseng/Desktop/Wolven\ Hunt/dist/assets/ 2>&1 | head` —— 应该能找到该函数名。找不到 = dist 是旧的。

### B. 用户跑的是 vite dev (7001) 但后端没起 / SSE 没连上
`vite.config.ts` 把 `/games`, `/models` 代理到 `127.0.0.1:7002`。若后端没启动，`subscribeGameEvents` 的 `EventSource` 会直接 onerror，`streamStatus → 'error'`，没有任何 `spectator_effect` 帧到达，前端自然空空如也。
- **观察现象**：右上角 `GameTopBar` 的 stream 状态 / 浏览器 Network → EventStream tab 没有 `spectator_effect` 行。
- **快速判断**：在浏览器 DevTools Console 看是否有 `[spectator_effect received]`（DEV 模式下 `GamePage.logSpectatorEffectsReceived` 会打印）。完全没有 → 没收到。

### C. live pacing 卡在 NIGHT_START 的 ack（前端 audio 异常时反而会卡）
`GamePage.handleAudioTrigger`（962 行附近）用 `gameAudio.playSequence(['wolf_howl', 'night_guard'])` 之后才发 `sendAck(gameId, 'NIGHT_START', 'night_intro_done')`。
- 浏览器 autoplay policy 禁止未交互播放，或 mp3 文件路径错，`playSequence` 走不到 await 之后但 catch 兜底确实会补 ack。
- 但要确认：测试时如果用户点了"进入黑夜"按钮（`handleClickEnterNight` 里 `void gameAudioControls.unlock()`）那确实解锁了。否则 audio 卡 promise 不解决，pacing 一直停在 NIGHT_START，**根本走不到 NIGHT_GUARD 事件**，自然没有任何特效产生。
- **观察现象**：`runs/<game_id>/events.jsonl` 里只有 `phase_enter NIGHT_START`，看不到 `guard_protect`。
- **验证**：`/bin/ls -t /Users/tampouseng/Desktop/Wolven\ Hunt/runs | head -1`，再 `cat events.jsonl | grep -c phase_enter` 看进度。

### D. 浏览器开了"减少动效" → 飞行动画退化为 burst，但 burst 也没渲染时
`GameEffectsLayer.useEffect` 第 88 行：`reduceMotion ? null : buildPotionFlight(...)`。如果 `reduceMotion = true`，flight 设为 null，再走 `buildPotionBurst`。但 burst 的实现里（第 188 行）也依赖 `layerRef.current` 和 `seatCenter`。
- macOS 系统设置 → 辅助功能 → 显示 → 减少动画，会全程命中。
- 不会让席位贴附图标失效（贴附是 `GameSeat` 渲染，不依赖 `prefers-reduced-motion`），但飞行/砸瓶动画会塌缩。
- 验证：DevTools → Rendering → Emulate CSS media feature `prefers-reduced-motion: no-preference` 后再试。

### E. spec/seq 边界：witch action 是 `skip` 时 source 仍被设置但 burst 被过滤
`activePotionEffects` 里 `isWitchPotionAction(effect)` 只在 `meta.action ∈ {save, poison}` 时返回 true。`skip` 直接被滤掉，**没有飞行动画**，这个是预期行为。 
- 不是 bug，但要在文案/讲解中明确："女巫选择不用药 → 不应有动画"。

### F. seat selector 不匹配 → seatCenter() 返回 null → flight/burst 不渲染（但席位贴附可能还在）
`GameEffectsLayer.seatCenter` 用 `document.querySelector('[data-seat-index="${seat - 1}"] .game-seat-circle')`。`GameSeat.tsx` 第 67 行确实有 `data-seat-index={seatIndex}`。匹配正确。
- 唯一可能塌的场景：layerRef 在第一次渲染时还是 null（Effect 已经跑），React StrictMode 下 effect 会重跑两次，第二次 layerRef 已挂载就 OK。
- 风险点：如果 seat DOM 在动画启动之前还没渲染（dead seat 隐藏？），querySelector 失败。死亡席位仍渲染 `.game-seat--dead`，selector 仍能命中，应不出问题。

---

## 诊断步骤（GPT 第一步必须做的）

不要再写代码。先按下面顺序做差异性诊断：

1. `cd /Users/tampouseng/Desktop/Wolven\ Hunt && /bin/ls -t runs | head -1` 拿到最新 run id；`grep -E "guard_protect|wolf_kill_decided|seer_check|witch_action" runs/<id>/events.jsonl | wc -l`
   - = 0 → 落到 C（pacing 卡住），跳到 §修复-C
   - > 0 → 后端在产，问题在前端，进入步骤 2
2. 让用户在浏览器开 DevTools，打开 Network → EventStream，点开 `/games/<id>/stream`，查看是否能看到 `event: spectator_effect` 的行
   - 没有 → A 或 B（前端 bundle 旧 / 后端没起 / SSE 错），跳到 §修复-A&B
   - 有 → 进入步骤 3
3. DevTools Console 搜 `[spectator_effect received]`
   - 没有 → A（dist 旧 bundle，console.info 是新代码加的），跳到 §修复-A
   - 有 → 步骤 4
4. DevTools Console 搜 `[spectator_effect rendered]`
   - 没有 → React 拿到了但 `GameEffectsLayer` 没渲染（announcement 路径），定位到 `activeRecentEffectAnnouncements` 的过期判断或时钟未滴答
   - 有 → 步骤 5
5. Elements 面板搜 `game-effect-flight` / `game-effect-burst` / `game-seat-effect--guard`
   - 节点存在但不可见 → CSS 问题（z-index / overflow / opacity），跳到 §修复-CSS
   - 节点不存在 → DOM 选择器或 reduceMotion，跳到 §修复-D&F

步骤 1–5 必须出结论再决定下一步动作。

---

## 修复路径（按诊断结论选一）

### 修复-A&B：bundle/服务问题（最可能）
1. 终止已有 dev/uvicorn 进程。
2. 让用户明确选择运行模式：
   - **dev 模式**：终端 1 `make dev-api`（或 `uv run uvicorn wolven_hunt.api.app:create_app --factory --port 7002`）；终端 2 `npm run dev`；浏览器开 `http://localhost:7001`。
   - **生产模式**：`npm run build` 后 `make dev-api`，浏览器开 `http://localhost:7002`。
3. 删 `dist/` 和浏览器站点缓存（DevTools → Network → Disable cache 勾上）后再试。
4. 跑测试确认前端逻辑没问题：`npm run test:frontend -- tests/frontend/gameEffectsLayer.test.tsx tests/frontend/gameEffects.test.ts`。

### 修复-C：pacing 卡在 NIGHT_START 的 audio ack
真凶是：用户没点击页面就进入 / autoplay 被拒 / `gameAudio.playSequence` 在 promise 里 hang 没 throw。
- `src/components/Game/GamePage.tsx` 的 `handleAudioTrigger`（约 922-961 行）已经有 try/catch 兜底发 ack，但**只在 throw 时触发**。如果 promise 卡死不 reject，ack 永远不发。
- 修法（最小侵入）：给 audio promise 加 `Promise.race` 超时兜底（如 6s），超时直接 `sendAck` 推进 pacing。改动只在 `handleAudioTrigger`，不动 fsm/runtime。
- 验证：拔网/把 mp3 路径手动改坏跑一局，应能正常进入 NIGHT_GUARD 并看到守卫盾牌。

### 修复-D&F：reduceMotion / DOM 选择器塌
- D：在 `GameEffectsLayer.tsx` 把 reduceMotion 分支保留（用 burst 替飞行），并确认 burst 自身能渲染。同时给 `.game-effect-flight`、`.game-effect-burst` 的 reduce-motion 媒体查询里**至少保留一个静态淡入淡出**，而不是直接关动画导致 `opacity: 0` 永远不变。当前 `styles.css:2929-2950` 的 reduce-motion 块需要看一下是不是把 opacity 关零了。
- F：保险起见，把 `seatCenter` 查询限定在当前游戏页容器里，避免未来页面出现重复席位节点时串到别处；并确保 `buildPotionFlight` / `buildPotionBurst` 失败时不会把 effect 标记为已播放，等下一次 clock tick 重试。

### 修复-CSS：节点存在但不可见
- 检查 `.game-effects-layer` 的祖先链上有没有 `transform/filter/will-change` 制造的新 stacking context 把它压在 bg 之下。
- 检查 `.game-effects-layer { overflow: hidden }` 是否裁掉了 announcement banner（top: 14vh 应该够，但如果 `.game-page` 设了 `overflow: hidden` 而 `.game-effects-layer` 受窗口 100% 限制，banner 可能被截）。

---

## 关键文件 & 必读位置

后端（一般不动）：
- `src/wolven_hunt/storage/spectator_effects.py`（单源真理：事件 → effect）
- `src/wolven_hunt/orchestration/runtime.py:205-217`（`publish_event` 调用 `event_to_spectator_effects`）
- `src/wolven_hunt/api/sse.py:32-33`（SSE emit）

前端（动这里）：
- `src/components/Game/GamePage.tsx:104-110, 168-184, 339-356, 837-867`（state + 流接入 + ingest）
- `src/components/Game/GameEffectsLayer.tsx`（飞行 / 砸瓶 / 横幅）
- `src/components/Game/GameSeat.tsx:105-142`（席位贴附）
- `src/lib/gameEffects.ts`（时长、活跃判定、announcement 队列）
- `src/styles.css:1920-2250, 2929-2950`（特效 CSS 含 reduce-motion）

资源：
- `public/assets/game/effects/*`（已就位）
- `public/assets/game/effect_manifest.json`（key → path 校验）

测试：
- `tests/frontend/gameEffects.test.ts` & `gameEffectsLayer.test.tsx` 已覆盖 happy path
- `tests/frontend/gameSeat.test.tsx` 覆盖席位贴附特效图标与资源路径。

---

## 验证清单（执行人完成后必跑）

1. `npm run build` 无 TS 错误。
2. `npm run test:frontend -- tests/frontend/gameEffects.test.ts tests/frontend/gameEffectsLayer.test.tsx tests/frontend/gameSeat.test.tsx` 全绿。
3. `uv run pytest tests/unit/test_spectator_effects.py tests/integration/test_spectator_mvp.py tests/leakage/test_sse_spectator_only.py` 全绿。
4. 端到端手测（这步必须做，前两步只能证逻辑没回归，证不了用户问题已解）：
   - 启动 backend + frontend，开浏览器 DevTools 录 EventStream 一局。
   - 录屏一局，确认四种特效全部出现：守卫蓝盾持续到天亮、狼袭红刀（被守命中时 3s 缓散）、预言查验头像闪 3.5s、女巫瓶子从 9 号位飞向目标头像并砸出 burst。
   - 横幅区四条公告依次浮现且 8s 过期。
   - 把 macOS reduce-motion 打开再跑一遍，确认 fallback（静态闪现）能看到。
5. 把 e2e 录屏放到 PR 描述里，避免又走"改了但没测"的循环。

---

## 不要做的事

- 不要改 `plan.md` / `architecture.md` 已定义的事件 → effect 映射，那条契约已经对齐。
- 不要在 `event_log` 里塞 ack/timer 状态，pacing/ack 是 spectator-only 不能进 replay hash。
- 不要为了"显示出来"把私有事件公开化（`SEER_CHECK` 等仍是 seat-private，spectator 路径只通过 `SpectatorEffect` 暴露图标，不暴露结果）。
- 不要再写第四版"重写 effects 系统"的方案；先按上面诊断步骤定位真因，95% 概率是 §A&B 的部署/缓存问题。
