# STEP-03 游戏准备页 执行规格

> **本规格只覆盖第三步交付：游戏准备页前端 UI + 页面过渡动画**。规则契约见 `plan.md` §1–§6 与 `architecture.md` §1–§16；前端壳契约见 `plan.md` §14（含新增 §14.13）与 `architecture.md` §18（含新增 §18.12）。本文件是 GPT 实施手册 + Kiro 验收指标的镜像。
>
> **硬约束**（与 STEP-01/02 一致，仍然有效）：
>
> 1. 不得修改 `plan.md` §1–§6、`architecture.md` §1–§16；如有冲突先回到上层修订流程。
> 2. 前端代码不得 `import` 任何 `src/wolven_hunt/*`；不得读取 `configs/*`；不得发起 HTTP / WebSocket / SSE 请求。
> 3. 不得改名 / 移动 / 删除 `素材/` 目录下的任何原始文件。
> 4. 所有运行时静态资源命名为 ASCII 小写蛇形。

---

## 1. 交付目标

完成后用户在浏览器打开本地 dev server 应能看到（叠加在 STEP-01/02 已交付的大厅基础上）：

1. 点击 StartModal 的「进入游戏」按钮 → 画面渐黑（600ms）→ 切换到白天背景 → 画面渐亮（800ms），总过渡 1.4s。
2. 游戏准备页全屏显示白天背景图，8 个席位分左右两列（各 4 个）垂直居中分布。
3. 初始所有席位为空态：圆形边框 + 中央加号。
4. 点击空席位加号 → 弹出模型选择弹窗（复用 `LobbyModal`），展示 8 个模型卡片。
5. 已被其他席位占用的模型卡片置灰不可点击；点击可用卡片 → 分配到当前席位 → 弹窗关闭。
6. 已分配席位显示模型头像 + 加粗昵称；点击头像可重新打开选择弹窗更换模型。
7. 过渡期间 lobby BGM 静音。
8. 8 个席位圆圈始终显示 1-based 编号：左列自上而下 1–4，右列自上而下 5–8；左列编号在左下角，右列编号在右下角。

---

## 2. 资源准备

### 2.1 拷贝资源

将 `素材/` 中以下 2 个文件复制到 `public/assets/game/`（新建目录），使用 ASCII 小写蛇形目标文件名：

| 源 | 目标 |
|---|---|
| `素材/白天模式.png` (1672×941) | `public/assets/game/day_bg.png` |
| `素材/黑夜模式.png` (1672×941) | `public/assets/game/night_bg.png` |

**`素材/` 原文件不得改名 / 删除 / 移动。**

### 2.2 资源约束

- `night_bg.png` 本步骤暂不使用，预拷贝备用。
- 两张背景均为 16:9 宽屏（1672×941），使用 `object-fit: cover` 全屏覆盖。

---

## 3. 页面切换机制

### 3.1 App 层级状态

不引入路由库。在 `src/App.tsx` 管理页面状态：

```tsx
import { useCallback, useRef, useState } from 'react';
import { LobbyHome } from './components/Lobby/LobbyHome';
import { GamePage } from './components/Game/GamePage';

type Page = 'lobby' | 'game';
type TransitionPhase = 'idle' | 'fade-out' | 'fade-in';

export default function App() {
  const [page, setPage] = useState<Page>('lobby');
  const [phase, setPhase] = useState<TransitionPhase>('idle');
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleEnterGame = useCallback(() => {
    setPhase('fade-out');
  }, []);

  const handleTransitionEnd = () => {
    if (phase === 'fade-out') {
      setPage('game');
      // 强制 opacity=1 无动画，然后下一帧启动 fade-in
      requestAnimationFrame(() => {
        setPhase('fade-in');
      });
    } else if (phase === 'fade-in') {
      setPhase('idle');
    }
  };

  return (
    <>
      {page === 'lobby' && <LobbyHome onEnterGame={handleEnterGame} />}
      {page === 'game' && <GamePage />}
      <div
        ref={overlayRef}
        className={`page-transition-overlay ${
          phase !== 'idle' ? `page-transition-overlay--${phase}` : ''
        }`}
        onTransitionEnd={handleTransitionEnd}
      />
    </>
  );
}
```

### 3.2 Props 传递

- `LobbyHome` 新增 prop `onEnterGame: () => void`，传递给 `StartModal`。
- `StartModal` 新增 prop `onEnterGame: () => void`，`enterGame` 函数改为调用 `onEnterGame()` 而非 `console.log`。

---

## 4. 过渡动画

### 4.1 CSS

```css
.page-transition-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #050507;
  pointer-events: none;
  opacity: 0;
}

.page-transition-overlay--fade-out {
  opacity: 1;
  transition: opacity 600ms ease-in;
  pointer-events: all;
}

.page-transition-overlay--fade-in {
  opacity: 0;
  transition: opacity 800ms ease-out;
  pointer-events: none;
}
```

### 4.2 音频处理

在 `App.tsx` 的 `handleEnterGame` 中调用 `useLobbyAudio` 暴露的 mute 行为以静音 BGM。具体方案：

- 选项 A（推荐）：`App.tsx` 不直接调用音频。由 `LobbyHome` 在 `onEnterGame` 触发前确保 mute（调用 `toggleMute()` 仅当未 muted）。
- 选项 B：在 `App.tsx` 顶层引入 `useLobbyAudio()`，过渡触发时直接 `toggleMute()`。

实现时选 B 更直接，因为大厅卸载后 `LobbyHome` 不再渲染，但 `useLobbyAudio` 的 audio store 是模块级单例，所以 mute 状态会被保留。

```tsx
// App.tsx
const { muted, toggleMute } = useLobbyAudio();

const handleEnterGame = useCallback(() => {
  if (!muted) {
    toggleMute();
  }
  setPhase('fade-out');
}, [muted, toggleMute]);
```

不需要新增 fadeOut API —— 600ms 黑屏期间瞬时 mute，用户感知不到突兀切断。

---

## 5. 组件结构

新建目录 `src/components/Game/`，包含 3 个组件：

```
src/components/Game/
├── GamePage.tsx
├── GameSeat.tsx
└── ModelPicker.tsx
```

### 5.1 GamePage.tsx

游戏准备页根组件。

```tsx
import { useState } from 'react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import { GameSeat } from './GameSeat';
import { ModelPicker } from './ModelPicker';

const SEAT_COUNT = 8;

export function GamePage() {
  // 长度 8，每个值是 MODEL_SLOTS 的 slot index 或 null
  const [assignments, setAssignments] = useState<(number | null)[]>(
    () => Array.from({ length: SEAT_COUNT }, () => null),
  );
  const [pickerSeat, setPickerSeat] = useState<number | null>(null);

  const handleClickSeat = (seatIndex: number) => {
    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null) return;
    setAssignments((prev) => {
      const next = [...prev];
      next[pickerSeat] = slotIndex;
      return next;
    });
    setPickerSeat(null);
  };

  const leftSeats = [0, 1, 2, 3];
  const rightSeats = [4, 5, 6, 7];

  return (
    <main className="game-page" aria-label="Wolven Hunt 游戏准备">
      <img
        src="/assets/game/day_bg.png"
        alt=""
        className="game-bg"
        loading="eager"
      />
      <div className="game-seats" aria-label="席位区">
        <div className="game-seats-col game-seats-col--left">
          {leftSeats.map((seatIndex) => (
            <GameSeat
              key={seatIndex}
              seatIndex={seatIndex}
              side="left"
              assignment={assignments[seatIndex]}
              onClickSeat={handleClickSeat}
            />
          ))}
        </div>
        <div className="game-seats-col game-seats-col--right">
          {rightSeats.map((seatIndex) => (
            <GameSeat
              key={seatIndex}
              seatIndex={seatIndex}
              side="right"
              assignment={assignments[seatIndex]}
              onClickSeat={handleClickSeat}
            />
          ))}
        </div>
      </div>
      <ModelPicker
        open={pickerSeat !== null}
        onClose={() => setPickerSeat(null)}
        currentAssignment={pickerSeat !== null ? assignments[pickerSeat] : null}
        usedSlots={assignments.filter((s): s is number => s !== null)}
        onPick={handlePickModel}
      />
    </main>
  );
}
```

### 5.2 GameSeat.tsx

单个席位组件。

```tsx
import { Plus } from 'lucide-react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({ seatIndex, side, assignment, onClickSeat }: GameSeatProps) {
  const isEmpty = assignment === null;
  const slot = isEmpty ? null : MODEL_SLOTS[assignment];

  return (
    <div className={`game-seat game-seat--${side}`} data-seat-index={seatIndex}>
      <button
        type="button"
        className="game-seat-circle"
        aria-label={
          isEmpty ? `添加第 ${seatIndex + 1} 号席位的模型` : `更换 ${slot!.nickname}`
        }
        onClick={() => onClickSeat(seatIndex)}
      >
        {isEmpty ? (
          <Plus aria-hidden="true" size={36} strokeWidth={2.5} />
        ) : (
          <img src={slot!.iconPath} alt="" className="game-seat-avatar" />
        )}
        <span className="game-seat-number">{seatIndex + 1}</span>
      </button>
      <span className="game-seat-nickname">{isEmpty ? '' : slot!.nickname}</span>
      <span className="game-seat-role" aria-label="身份">
        {/* 身份分配留给后续步骤；本步骤显示空 */}
      </span>
    </div>
  );
}
```

### 5.3 ModelPicker.tsx

模型选择弹窗，复用 `LobbyModal`（variant="default"）。

```tsx
import { LobbyModal } from '../Lobby/LobbyModal';
import { MODEL_SLOTS } from '../../lib/modelConfigs';

type ModelPickerProps = {
  open: boolean;
  onClose: () => void;
  currentAssignment: number | null;
  usedSlots: number[];
  onPick: (slotIndex: number) => void;
};

export function ModelPicker({
  open,
  onClose,
  currentAssignment,
  usedSlots,
  onPick,
}: ModelPickerProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="选择模型">
      <div className="model-picker-grid" role="list">
        {MODEL_SLOTS.map((slot) => {
          const isCurrent = currentAssignment === slot.slot;
          const isUsedByOther = usedSlots.includes(slot.slot) && !isCurrent;

          return (
            <button
              key={slot.slot}
              type="button"
              className={`model-picker-card ${
                isCurrent ? 'model-picker-card--current' : ''
              } ${isUsedByOther ? 'model-picker-card--disabled' : ''}`}
              role="listitem"
              disabled={isUsedByOther}
              onClick={() => {
                if (!isUsedByOther) onPick(slot.slot);
              }}
            >
              <img src={slot.iconPath} alt="" className="model-picker-avatar" />
              <span className="model-picker-nickname">{slot.nickname}</span>
            </button>
          );
        })}
      </div>
    </LobbyModal>
  );
}
```

---

## 6. CSS 布局

在 `src/styles.css` 末尾追加：

```css
/* === STEP-03: 页面过渡 === */

.page-transition-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #050507;
  pointer-events: none;
  opacity: 0;
}

.page-transition-overlay--fade-out {
  opacity: 1;
  transition: opacity 600ms ease-in;
  pointer-events: all;
}

.page-transition-overlay--fade-in {
  opacity: 0;
  transition: opacity 800ms ease-out;
  pointer-events: none;
}

/* === STEP-03: 游戏页 === */

.game-page {
  position: relative;
  width: 100vw;
  min-height: 100dvh;
  overflow: hidden;
  background: #050507;
}

.game-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 0;
  user-select: none;
  pointer-events: none;
}

.game-seats {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5vh 3vw;
}

.game-seats-col {
  display: flex;
  flex-direction: column;
  gap: 2.5vh;
}

/* === STEP-03: 席位 === */

.game-seat {
  display: flex;
  align-items: center;
  gap: 12px;
}

.game-seat--right {
  flex-direction: row-reverse;
}

.game-seat-circle {
  position: relative;
  width: clamp(60px, 8vw, 100px);
  aspect-ratio: 1 / 1;
  border-radius: 50%;
  border: 2px dashed rgba(255, 255, 255, 0.6);
  background: rgba(0, 0, 0, 0.25);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0;
  transition: transform 120ms ease, border-color 120ms ease;
}

.game-seat-circle:hover {
  border-color: rgba(255, 255, 255, 0.9);
  transform: scale(1.04);
}

.game-seat-circle:focus-visible {
  outline: 2px solid #ffd166;
  outline-offset: 3px;
}

.game-seat-number {
  position: absolute;
  bottom: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: clamp(20px, 2.4vw, 28px);
  height: clamp(20px, 2.4vw, 28px);
  padding: 0 6px;
  color: #fff;
  font-size: clamp(12px, 1.2vw, 15px);
  font-weight: 700;
  line-height: 1;
  border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.5);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
}

.game-seat--right .game-seat-number {
  right: 6px;
  left: auto;
}

.game-seat-avatar {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.game-seat-nickname {
  color: #fff;
  font-size: clamp(14px, 1.4vw, 18px);
  font-weight: 700;
  text-shadow:
    0 1px 4px rgba(0, 0, 0, 0.9),
    0 0 10px rgba(0, 0, 0, 0.65);
  min-width: 80px;
}

.game-seat--right .game-seat-nickname {
  text-align: right;
}

.game-seat-role {
  /* 身份占位：本步骤为空，后续步骤填充 */
  display: none;
}

/* === STEP-03: 模型选择弹窗 === */

.model-picker-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 12px;
}

.model-picker-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 2px solid transparent;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
  color: #fff;
  text-align: left;
}

.model-picker-card:hover:not(.model-picker-card--disabled) {
  background: rgba(255, 255, 255, 0.12);
}

.model-picker-card--current {
  border-color: #ffd166;
}

.model-picker-card--disabled {
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(0.8);
}

.model-picker-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.model-picker-nickname {
  font-size: 16px;
}
```

---

## 7. 修改清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `public/assets/game/day_bg.png` | 新建（cp） | 白天背景 |
| `public/assets/game/night_bg.png` | 新建（cp） | 夜晚背景预备 |
| `src/App.tsx` | 修改 | 添加 Page 状态 + overlay + 条件渲染 |
| `src/components/Lobby/LobbyHome.tsx` | 修改 | 接收 `onEnterGame` prop 并传递给 StartModal |
| `src/components/Lobby/modals/StartModal.tsx` | 修改 | `enterGame` 调用 `onEnterGame()` |
| `src/components/Game/GamePage.tsx` | 新建 | 游戏准备页根组件 |
| `src/components/Game/GameSeat.tsx` | 新建 | 席位组件 |
| `src/components/Game/ModelPicker.tsx` | 新建 | 模型选择弹窗 |
| `src/styles.css` | 修改 | 追加 page-transition / game-page / game-seat / model-picker 样式 |
| `plan.md` | 修改 | §7 目录树添加 Game/ 与 game/ 资源；新增 §14.13 |
| `architecture.md` | 修改 | 新增 §18.12 |

---

## 8. 实施顺序

1. 拷贝资产到 `public/assets/game/`（`mkdir -p public/assets/game/`，然后 `cp 素材/白天模式.png public/assets/game/day_bg.png` 等）
2. 修改 `plan.md` + `architecture.md`（先更新文档再改代码）
3. 修改 `App.tsx`：添加 Page 状态 + overlay + 条件渲染
4. 修改 `LobbyHome.tsx`：接收并传递 `onEnterGame`
5. 修改 `StartModal.tsx`：调用 `onEnterGame`
6. 新建 `src/components/Game/GamePage.tsx`
7. 新建 `src/components/Game/GameSeat.tsx`
8. 新建 `src/components/Game/ModelPicker.tsx`
9. 修改 `src/styles.css`：追加新样式
10. 验证：`npm run typecheck` + `npm run build` + 浏览器手测

---

## 9. 验收指标

### A. 资产

| ID | 检查项 | 验证手段 |
|---|---|---|
| A1 | `public/assets/game/day_bg.png` 存在，尺寸 1672×941 | `file public/assets/game/day_bg.png` |
| A2 | `public/assets/game/night_bg.png` 存在，尺寸 1672×941 | 同上 |
| A3 | `素材/白天模式.png` / `素材/黑夜模式.png` 原文件未被改名/删除 | `git status` |

### B. 页面切换

| ID | 检查项 |
|---|---|
| B1 | 点击「进入游戏」后画面渐黑（约 600ms），随后渐亮（约 800ms）显示游戏页 |
| B2 | 过渡触发后 lobby BGM 立即静音 |
| B3 | 过渡完成后 lobby 组件不再渲染（DOM 中无 `.lobby-shell`） |
| B4 | 过渡期间 overlay `pointer-events: all`，阻止双击重复触发 |

### C. 游戏页布局

| ID | 检查项 |
|---|---|
| C1 | 白天背景全屏覆盖，`object-fit: cover` |
| C2 | 8 个席位分左右两列，各 4 个，垂直居中分布 |
| C3 | 空席位显示圆形虚线边框 + 中央加号图标（lucide `Plus`） |
| C4 | 席位圆圈使用 `clamp(60px, 8vw, 100px)` 响应式尺寸 |
| C5 | 左列席位昵称在右侧，右列席位昵称在左侧（`flex-direction: row-reverse`） |
| C6 | 8 个席位圆圈始终显示 1–8 编号；左列编号在左下角，右列编号在右下角 |
| C7 | 已分配席位昵称为加粗白字，并带增强文字阴影 |

### D. 模型选择

| ID | 检查项 |
|---|---|
| D1 | 点击空席位加号 → 弹出 LobbyModal，title="选择模型" |
| D2 | 弹窗内显示 8 个模型卡片（头像 + 昵称） |
| D3 | 已被其他席位占用的模型卡片置灰（opacity 0.4 + grayscale）且 `disabled` |
| D4 | 点击可用卡片 → 席位显示对应头像 + 昵称 → 弹窗关闭 |
| D5 | 点击已分配席位的头像 → 重新打开 picker，当前选中卡片高亮（黄色边框） |
| D6 | 重新选择后旧 slot 释放（再次打开其他席位 picker 不再置灰） |
| D7 | 同一模型在 8 个席位中只能出现一次 |

### E. 边界约束

| ID | 检查项 |
|---|---|
| E1 | `grep -RInE "fetch\\(\|axios\|XMLHttpRequest\|WebSocket\|EventSource" src/components/Game src/App.tsx` 无命中 |
| E2 | `grep -RInE "RuleEngine\|Referee\|FSM\|wolven_hunt" src/components/Game src/App.tsx` 无命中（除 false positive） |
| E3 | DevTools Console 无 error / warning |

### F. 构建

| ID | 检查项 |
|---|---|
| F1 | `npm run typecheck` 通过 |
| F2 | `npm run build` 通过 |
| F3 | dev server 启动后页面无白屏 / 报错 |

---

## 10. 不在本步骤范围

- 夜晚模式切换（资产已预备，逻辑留给后续步骤）
- 身份分配逻辑（席位预留 `.game-seat-role` 占位，但不实现）
- 「开始游戏」二级 CTA（8 席全满后的下一步操作）
- 游戏内聊天 / 投票 / 回合逻辑
- 任何后端 / LLM 接入
- 返回大厅按钮（暂不提供，刷新页面回大厅）
