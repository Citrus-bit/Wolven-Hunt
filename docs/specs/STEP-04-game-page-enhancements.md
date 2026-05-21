# STEP-04 游戏页 UI 增强 执行规格

> **本规格只覆盖第四步交付：游戏页顶栏 / 阶段指示 / 双聊天框 / 退出确认 / 模型连通性测试 / 进入夜晚**。规则契约见 `plan.md` §1–§6 与 `architecture.md` §1–§16；前端壳契约见 `plan.md` §14（含新增 §14.14）与 `architecture.md` §18（含新增 §18.13）。本文件是 GPT 实施手册 + Kiro 验收指标的镜像。
>
> **硬约束**（与 STEP-01/02/03 一致，仍然有效）：
>
> 1. 不得修改 `plan.md` §1–§6、`architecture.md` §1–§16；如有冲突先回到上层修订流程。
> 2. 前端代码不得 `import` 任何 `src/wolven_hunt/*`；不得读取 `configs/*`。
> 3. 网络请求豁免范围**严格限定**为本步骤文档登记的两类：同源 `fetch('/assets/game/rules.md')` 与用户主动触发的 `testModelConnection`。其它任何 HTTP / WebSocket / SSE 调用一律禁止。
> 4. 不得改名 / 移动 / 删除 `素材/` 目录下的任何原始文件。
> 5. 所有运行时静态资源命名为 ASCII 小写蛇形。
> 6. 不引入路由库；不引入 Markdown 富文本渲染库（rules.md 只允许轻量解析标题 / 列表 / 加粗，渲染为结构化正文）。

---

## 1. 交付目标

完成后用户在浏览器打开本地 dev server 应能看到（叠加在 STEP-03 已交付的游戏准备页基础上）：

1. 游戏页右上角显示两个 40×40 圆形按钮：规则（lucide `BookOpen`）+ 退出（lucide `X`）。
2. 游戏页顶部中心显示阶段指示：太阳/月亮图标 + `第1天` 文案（默认表示第 1 天白天），图标和文字垂直居中。
3. 中心区域显示左右双聊天框：左侧通用聊天框、右侧狼人专属聊天框。两栏永远同时可见，输入框 `disabled`。
4. 底部居中显示纵向两按钮：上为「测试模型连通性」、下为「夜深了…」。
5. 8 席未填满时，两个按钮均灰态 disabled。
6. 8 席填满后「测试模型连通性」按钮蓝色可点击；「夜深了…」仍灰态。
7. 点击测试 → 按钮变「正在测试中」且不可点，所有已分配席位头像变灰 + 三点 pulse 动画 → 完成后每个席位都显示 ✓（绿）或 ✗（红）徽标，底部显示通过数量摘要。
8. 全部 ✓ 后「夜深了…」变红可点击 → 触发 600ms 黑屏 + 800ms 亮起 → 切到夜晚背景 + 月亮图标。
9. 点规则 → 游戏页专用弹窗显示规则文档，正文渲染为可读标题 / 段落 / 列表，不露出 markdown `#` 标记。
10. 点退出 → 二次确认弹窗（取消 / 确认）→ 确认后 600ms 黑屏 + 800ms 亮起 → 切回大厅。
11. 切回大厅后 BGM **保持静音**（不自动还原）；用户可手动取消静音。
12. DEV 模式下显示一个 `[debug] 推进` 按钮，用于切换白天/黑夜并 +1 dayNumber；生产 build tree-shake。
13. 8 席填满后仍可调整席位：打开任一已分配席位的 `ModelPicker`，它使用游戏页自有弹窗外壳，不复用大厅竖版背景图；其它已占用模型卡片主体保持置灰不可直接选择，但右下角提供图标型「交换」按钮，点击后当前席位与该模型所在席位互换。

---

## 2. 资源准备

### 2.1 拷贝资源

将 `素材/Wolven Hunt游戏规则.md` 复制到 `public/assets/game/rules.md`，复制时**必须去掉**首行 ` ```md ` 与末行 ` ``` ` 围栏，只保留中间 markdown 内容。

| 源 | 目标 |
|---|---|
| `素材/Wolven Hunt游戏规则.md`（去除首末围栏） | `public/assets/game/rules.md` |
| `素材/小浣熊.png` | `public/assets/game/quick_assign_raccoon.png` |

`day_bg.png` / `night_bg.png` 已在 STEP-03 拷贝到 `public/assets/game/`，本步骤直接复用。`quick_assign_raccoon.png` 仅用于左下角「一键分配」装饰入口。

**`素材/` 原文件不得改名 / 删除 / 移动。**

### 2.2 资源约束

- `rules.md` 首行必须是 `# Wolven Hunt 游戏规则`；末行必须是规则正文，不能有 ` ``` ` 围栏。
- `rules.md` 体积应 < 10KB，可一次性 fetch 到内存渲染。

---

## 3. 数据模型与工具函数

### 3.1 `src/lib/gameStage.ts`（新建）

```ts
export type DayPhase = 'day' | 'night';

export type GameStage = {
  dayNumber: number;
  phase: DayPhase;
};

export const INITIAL_STAGE: GameStage = {
  dayNumber: 1,
  phase: 'day',
};
```

### 3.2 `src/lib/modelTest.ts`（新建）

```ts
import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  type ModelConfigUserInput,
} from './modelConfigs';

export type ModelTestStatus = 'idle' | 'testing' | 'pass' | 'fail';

export type ModelTestResult = {
  status: ModelTestStatus;
  errorMessage?: string;
};

export type ModelTestRequest = {
  baseUrl: string;
  apiKey: string;
  modelName: string;
};

function isCompleteConfig(
  config: Partial<ModelConfigUserInput>,
): config is ModelTestRequest {
  return Boolean(config.baseUrl && config.apiKey && config.modelName);
}

/**
 * 向 OpenAI 兼容端点发起最简 chat completion 请求验证模型可达。
 * baseUrl 形如 https://api.example.com/v1，自动拼 /chat/completions。
 * 单次请求超时 15s。
 */
export async function testModelConnection(
  req: ModelTestRequest,
  signal?: AbortSignal,
): Promise<ModelTestResult> {
  const url = req.baseUrl.replace(/\/+$/, '') + '/chat/completions';
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 15000);
  signal?.addEventListener('abort', () => controller.abort());
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${req.apiKey}`,
      },
      body: JSON.stringify({
        model: req.modelName,
        messages: [{ role: 'user', content: 'ping' }],
        max_tokens: 1,
      }),
      signal: controller.signal,
    });
    window.clearTimeout(timeoutId);
    if (!res.ok) {
      return { status: 'fail', errorMessage: `HTTP ${res.status}` };
    }
    const data = await res.json();
    if (typeof data !== 'object' || data === null) {
      return { status: 'fail', errorMessage: '非 JSON 响应' };
    }
    return { status: 'pass' };
  } catch (e) {
    window.clearTimeout(timeoutId);
    const msg = e instanceof Error ? e.message : '未知错误';
    return { status: 'fail', errorMessage: msg.slice(0, 80) };
  }
}

export function readModelConfig(slot: number): ModelTestRequest | null {
  const defaultConfig = MODEL_CONFIG_DEFAULTS[slot] ?? EMPTY_USER_INPUT;
  try {
    const raw = localStorage.getItem(`wolven_hunt.lobby.model_config.${slot}`);
    if (!raw) return isCompleteConfig(defaultConfig) ? defaultConfig : null;
    const parsed = JSON.parse(raw);
    const mergedConfig = {
      baseUrl: typeof parsed.baseUrl === 'string' ? parsed.baseUrl : defaultConfig.baseUrl,
      apiKey: typeof parsed.apiKey === 'string' ? parsed.apiKey : defaultConfig.apiKey,
      modelName: typeof parsed.modelName === 'string' ? parsed.modelName : defaultConfig.modelName,
    };
    return isCompleteConfig(mergedConfig) ? mergedConfig : null;
  } catch {
    return isCompleteConfig(defaultConfig) ? defaultConfig : null;
  }
}
```

实现选用 OpenAI 兼容协议（`POST {baseUrl}/chat/completions`，`Authorization: Bearer {apiKey}`，body `{model, messages, max_tokens: 1}`）——这是国内主流 LLM 网关（智谱 / 月之暗面 / DeepSeek / Minimax / Qwen 等）的通用协议。`max_tokens: 1` 让请求成本与延迟最低。

---

## 4. App 层级双向页面切换

修改 `src/App.tsx`：新增 `targetPageRef` 支持 lobby ↔ game 双向过渡。

```tsx
import { useCallback, useRef, useState } from 'react';
import { LobbyHome } from './components/Lobby/LobbyHome';
import { GamePage } from './components/Game/GamePage';
import { useLobbyAudio } from './hooks/useLobbyAudio';

type Page = 'lobby' | 'game';
type TransitionPhase = 'idle' | 'fade-out' | 'fade-in';

export default function App() {
  const [page, setPage] = useState<Page>('lobby');
  const [phase, setPhase] = useState<TransitionPhase>('idle');
  const targetPageRef = useRef<Page | null>(null);
  const { muted, toggleMute } = useLobbyAudio();

  const handleEnterGame = useCallback(() => {
    if (!muted) toggleMute();
    targetPageRef.current = 'game';
    setPhase('fade-out');
  }, [muted, toggleMute]);

  const handleExitGame = useCallback(() => {
    targetPageRef.current = 'lobby';
    setPhase('fade-out');
  }, []);

  const handleTransitionEnd = () => {
    if (phase === 'fade-out' && targetPageRef.current) {
      setPage(targetPageRef.current);
      targetPageRef.current = null;
      requestAnimationFrame(() => setPhase('fade-in'));
    } else if (phase === 'fade-in') {
      setPhase('idle');
    }
  };

  return (
    <>
      {page === 'lobby' && <LobbyHome onEnterGame={handleEnterGame} />}
      {page === 'game' && <GamePage onExitGame={handleExitGame} />}
      <div
        className={`page-transition-overlay ${
          phase !== 'idle' ? `page-transition-overlay--${phase}` : ''
        }`}
        onTransitionEnd={handleTransitionEnd}
      />
    </>
  );
}
```

- 退出时**不**调用 `toggleMute` ——避免回到大厅瞬间 BGM 突然恢复造成困惑。用户回到大厅后可手动按右上角浮动按钮取消静音。
- `targetPageRef` 用 `useRef` 而非 state 是为了在 fade-out → fade-in 之间不触发额外 re-render。

---

## 5. 组件结构

新增组件全部位于 `src/components/Game/`。最终目录如下：

```
src/components/Game/
├── GamePage.tsx              # STEP-03 已存在，本步骤大改
├── GameSeat.tsx              # STEP-03 已存在，本步骤新增 testStatus prop
├── ModelPicker.tsx           # STEP-03 已存在，本步骤改成游戏页自有弹窗 + 已占用模型交换入口
├── GameTopBar.tsx            # 新建
├── StageIndicator.tsx        # 新建
├── GameChat.tsx              # 新建
├── GameBottomActions.tsx     # 新建
├── RulesModal.tsx            # 新建
└── ExitConfirmModal.tsx      # 新建
```

### 5.1 `GameTopBar.tsx`（新建）

```tsx
import { BookOpen, X } from 'lucide-react';

type GameTopBarProps = {
  onClickRules: () => void;
  onClickExit: () => void;
};

export function GameTopBar({ onClickRules, onClickExit }: GameTopBarProps) {
  return (
    <div className="game-top-bar" role="toolbar" aria-label="游戏顶栏">
      <button
        type="button"
        className="game-top-btn"
        aria-label="查看游戏规则"
        onClick={onClickRules}
      >
        <BookOpen size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className="game-top-btn"
        aria-label="退出游戏返回大厅"
        onClick={onClickExit}
      >
        <X size={20} aria-hidden="true" />
      </button>
    </div>
  );
}
```

### 5.2 `StageIndicator.tsx`（新建）

```tsx
import { Sun, Moon } from 'lucide-react';
import type { GameStage } from '../../lib/gameStage';

type StageIndicatorProps = {
  stage: GameStage;
};

export function StageIndicator({ stage }: StageIndicatorProps) {
  const Icon = stage.phase === 'day' ? Sun : Moon;
  const ariaLabel = `第 ${stage.dayNumber} 天 ${stage.phase === 'day' ? '白天' : '黑夜'}`;
  return (
    <div className="game-stage-indicator" aria-label={ariaLabel}>
      <Icon
        size={36}
        strokeWidth={2.2}
        className={`game-stage-icon game-stage-icon--${stage.phase}`}
        aria-hidden="true"
      />
      <span className="game-stage-day-label" aria-hidden="true">
        第{stage.dayNumber}天
      </span>
    </div>
  );
}
```

### 5.3 `GameChat.tsx`（新建）

```tsx
export function GameChat() {
  return (
    <div className="game-chat" aria-label="游戏聊天区">
      <section className="game-chat-panel game-chat-panel--general" aria-label="通用聊天框">
        <header className="game-chat-header">通用聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite">
          {/* STEP-04 暂无消息总线 */}
        </div>
        <footer className="game-chat-footer">
          <input
            type="text"
            className="game-chat-input"
            placeholder="发言（待接入引擎）"
            disabled
            aria-disabled="true"
          />
        </footer>
      </section>
      <section className="game-chat-panel game-chat-panel--wolf" aria-label="狼人聊天框">
        <header className="game-chat-header">狼人聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite">
          {/* STEP-04 暂无消息总线 */}
        </div>
        <footer className="game-chat-footer">
          <input
            type="text"
            className="game-chat-input"
            placeholder="狼人夜聊（待接入引擎）"
            disabled
            aria-disabled="true"
          />
        </footer>
      </section>
    </div>
  );
}
```

### 5.4 `GameBottomActions.tsx`（新建）

```tsx
type GameBottomActionsProps = {
  allSeatsAssigned: boolean;
  allTestsPassed: boolean;
  isTesting: boolean;
  testMessage?: string | null;
  onClickTest: () => void;
  onClickEnterNight: () => void;
};

export function GameBottomActions({
  allSeatsAssigned,
  allTestsPassed,
  isTesting,
  testMessage,
  onClickTest,
  onClickEnterNight,
}: GameBottomActionsProps) {
  const testDisabled = !allSeatsAssigned || isTesting;
  const enterDisabled = !allSeatsAssigned || !allTestsPassed || isTesting;

  return (
    <div className="game-bottom-actions">
      <button
        type="button"
        className="game-bottom-btn game-bottom-btn--test"
        disabled={testDisabled}
        onClick={onClickTest}
      >
        {isTesting ? '正在测试中' : '测试模型连通性'}
      </button>
      <button
        type="button"
        className="game-bottom-btn game-bottom-btn--night"
        disabled={enterDisabled}
        onClick={onClickEnterNight}
      >
        夜深了…
      </button>
      {testMessage && (
        <p className="game-test-status" role="status" aria-live="polite">
          {testMessage}
        </p>
      )}
    </div>
  );
}
```

### 5.5 `RulesModal.tsx`（新建）

使用游戏页自有弹窗外壳，挂载时一次性 `fetch('/assets/game/rules.md')` 拿到纯文本。不得复用大厅 `settings_panel_bg.png` 背景图；正文必须放在规则专用滚动背景中，并通过轻量解析渲染为标题、段落、有序 / 无序列表与加粗文本，不允许用 `<pre>` 直接露出 markdown `#` 标记，不引入 markdown 渲染库。

```tsx
import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type RulesModalProps = {
  open: boolean;
  onClose: () => void;
};

// Implementation may keep the lightweight markdown parser in this module.

export function RulesModal({ open, onClose }: RulesModalProps) {
  const [content, setContent] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    fetch('/assets/game/rules.md')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : '加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="rules-modal-backdrop" onMouseDown={onClose}>
      <section className="rules-modal-panel" role="dialog" aria-modal="true">
        <button type="button" className="rules-modal-close" aria-label="关闭" onClick={onClose}>
          <X aria-hidden="true" size={20} />
        </button>
        <header className="rules-modal-header">
          <h2>游戏规则</h2>
        </header>
        <article className="rules-modal-body">
        {error ? (
          <p className="rules-modal-error">规则加载失败：{error}</p>
        ) : !content ? (
          <p className="rules-modal-loading">加载中…</p>
        ) : (
          <RulesDocument content={content} />
        )}
        </article>
      </section>
    </div>
  );
}
```

### 5.6 `ExitConfirmModal.tsx`（新建）

```tsx
import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type ExitConfirmModalProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function ExitConfirmModal({ open, onClose, onConfirm }: ExitConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="exit-confirm-backdrop" onMouseDown={onClose}>
      <div className="exit-confirm-panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="exit-confirm-close" aria-label="关闭" onClick={onClose}>
          <X aria-hidden="true" size={18} />
        </button>
        <h2>退出游戏</h2>
        <p className="exit-confirm-text">确定要退出当前游戏返回大厅吗？当前席位分配与测试结果不会被保存。</p>
        <div className="exit-confirm-actions">
          <button type="button" className="exit-confirm-btn exit-confirm-btn--cancel" onClick={onClose}>
            取消
          </button>
          <button type="button" className="exit-confirm-btn exit-confirm-btn--confirm" onClick={onConfirm}>
            确认退出
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 5.7 `GameSeat.tsx`（修改 — 新增 testStatus prop + 三点动画 + 徽标）

在原 STEP-03 实现上叠加：

```tsx
import { Plus, Check, X as XIcon } from 'lucide-react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import type { ModelTestStatus } from '../../lib/modelTest';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  testStatus?: ModelTestStatus;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  testStatus,
  onClickSeat,
}: GameSeatProps) {
  const isEmpty = assignment === null;
  const slot = isEmpty ? null : MODEL_SLOTS[assignment];
  const isTesting = testStatus === 'testing';
  const showBadge = testStatus === 'pass' || testStatus === 'fail';

  return (
    <div className={`game-seat game-seat--${side}`} data-seat-index={seatIndex}>
      <button
        type="button"
        className={`game-seat-circle ${isTesting ? 'game-seat-circle--testing' : ''}`}
        aria-label={
          isEmpty ? `添加第 ${seatIndex + 1} 号席位的模型` : `更换 ${slot!.nickname}`
        }
        onClick={() => onClickSeat(seatIndex)}
        disabled={isTesting}
      >
        {isEmpty ? (
          <Plus aria-hidden="true" size={36} strokeWidth={2.5} />
        ) : (
          <img src={slot!.iconPath} alt="" className="game-seat-avatar" />
        )}
        <span className="game-seat-number">{seatIndex + 1}</span>
        {isTesting && (
          <span className="game-seat-dots" aria-hidden="true">
            <span className="dot dot-1" />
            <span className="dot dot-2" />
            <span className="dot dot-3" />
          </span>
        )}
        {showBadge && (
          <span
            className={`game-seat-badge game-seat-badge--${testStatus}`}
            aria-label={testStatus === 'pass' ? '测试通过' : '测试失败'}
          >
            {testStatus === 'pass' ? (
              <Check size={14} strokeWidth={3} aria-hidden="true" />
            ) : (
              <XIcon size={14} strokeWidth={3} aria-hidden="true" />
            )}
          </span>
        )}
      </button>
      <span className="game-seat-nickname">{isEmpty ? '' : slot!.nickname}</span>
      <span className="game-seat-role" aria-label="身份" />
    </div>
  );
}
```

### 5.8 `GamePage.tsx`（修改 — 整合所有子组件 + 阶段切换 + 测试逻辑）

```tsx
import { useRef, useState } from 'react';
import { GameSeat } from './GameSeat';
import { ModelPicker } from './ModelPicker';
import { GameTopBar } from './GameTopBar';
import { StageIndicator } from './StageIndicator';
import { GameChat } from './GameChat';
import { GameBottomActions } from './GameBottomActions';
import { RulesModal } from './RulesModal';
import { ExitConfirmModal } from './ExitConfirmModal';
import { INITIAL_STAGE } from '../../lib/gameStage';
import type { GameStage } from '../../lib/gameStage';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  readModelConfig,
  testModelConnection,
} from '../../lib/modelTest';
import type { ModelTestResult } from '../../lib/modelTest';

const SEAT_COUNT = 8;
type BgPhase = 'idle' | 'fade-out' | 'fade-in';

type GamePageProps = {
  onExitGame: () => void;
};

function shuffledModelSlots() {
  const slots = MODEL_SLOTS.map((slot) => slot.slot);
  for (let index = slots.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [slots[index], slots[swapIndex]] = [slots[swapIndex], slots[index]];
  }
  return slots;
}

export function GamePage({ onExitGame }: GamePageProps) {
  const [assignments, setAssignments] = useState<(number | null)[]>(
    () => Array.from({ length: SEAT_COUNT }, () => null),
  );
  const [pickerSeat, setPickerSeat] = useState<number | null>(null);
  const [stage, setStage] = useState<GameStage>(INITIAL_STAGE);
  const [bgPhase, setBgPhase] = useState<BgPhase>('idle');
  const pendingStageRef = useRef<GameStage | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
  const [testResults, setTestResults] = useState<Record<number, ModelTestResult>>({});
  const [isTesting, setIsTesting] = useState(false);

  const allSeatsAssigned = assignments.every((a) => a !== null);
  const allTestsPassed =
    allSeatsAssigned &&
    assignments.every(
      (slotIdx) => slotIdx !== null && testResults[slotIdx]?.status === 'pass',
    );
  const bgSrc =
    stage.phase === 'day' ? '/assets/game/day_bg.png' : '/assets/game/night_bg.png';

  const handleClickSeat = (seatIndex: number) => {
    if (isTesting) return;
    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null) return;
    setAssignments((prev) => {
      const next = [...prev];
      next[pickerSeat] = slotIndex;
      return next;
    });
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[slotIndex];
      return next;
    });
    setPickerSeat(null);
  };

  const handleQuickAssign = () => {
    if (isTesting) return;
    setPickerSeat(null);
    setAssignments(shuffledModelSlots());
    setTestResults({});
  };

  const transitionToStage = (next: GameStage) => {
    if (bgPhase !== 'idle') return;
    pendingStageRef.current = next;
    setBgPhase('fade-out');
  };

  const handleStageOverlayTransitionEnd = () => {
    if (bgPhase === 'fade-out' && pendingStageRef.current) {
      setStage(pendingStageRef.current);
      pendingStageRef.current = null;
      requestAnimationFrame(() => setBgPhase('fade-in'));
    } else if (bgPhase === 'fade-in') {
      setBgPhase('idle');
    }
  };

  const handleClickTest = async () => {
    setIsTesting(true);
    const initial: Record<number, ModelTestResult> = {};
    assignments.forEach((slotIdx) => {
      if (slotIdx !== null) initial[slotIdx] = { status: 'testing' };
    });
    setTestResults(initial);

    const tasks = assignments
      .map((slotIdx) => slotIdx)
      .filter((s): s is number => s !== null)
      .map(async (slotIdx) => {
        const cfg = readModelConfig(slotIdx);
        if (!cfg) {
          return {
            slotIdx,
            result: { status: 'fail', errorMessage: '配置缺失' } as ModelTestResult,
          };
        }
        const result = await testModelConnection(cfg);
        return { slotIdx, result };
      });

    const results = await Promise.all(tasks);
    setTestResults((prev) => {
      const next = { ...prev };
      results.forEach(({ slotIdx, result }) => {
        next[slotIdx] = result;
      });
      return next;
    });
    setIsTesting(false);
  };

  const handleClickEnterNight = () => {
    transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
  };

  const handleConfirmExit = () => {
    setExitConfirmOpen(false);
    onExitGame();
  };

  const leftSeats = [0, 1, 2, 3];
  const rightSeats = [4, 5, 6, 7];

  return (
    <main className="game-page" aria-label="Wolven Hunt 游戏">
      <img
        src={bgSrc}
        alt=""
        className="game-bg"
        loading="eager"
        key={bgSrc}
      />
      <div
        className={`game-stage-overlay ${
          bgPhase !== 'idle' ? `game-stage-overlay--${bgPhase}` : ''
        }`}
        onTransitionEnd={handleStageOverlayTransitionEnd}
      />
      <GameTopBar
        onClickRules={() => setRulesOpen(true)}
        onClickExit={() => setExitConfirmOpen(true)}
      />
      <StageIndicator stage={stage} />
      <GameChat />
      <div className="game-quick-assign-helper">
        <img
          src="/assets/game/quick_assign_raccoon.png"
          alt=""
          className="game-quick-assign-mascot"
        />
        <button type="button" className="game-quick-assign" onClick={handleQuickAssign} disabled={isTesting}>
          一键分配
        </button>
      </div>
      <div className="game-seats" aria-label="席位区">
        <div className="game-seats-col game-seats-col--left">
          {leftSeats.map((seatIndex) => {
            const a = assignments[seatIndex];
            return (
              <GameSeat
                key={seatIndex}
                seatIndex={seatIndex}
                side="left"
                assignment={a}
                testStatus={a !== null ? testResults[a]?.status : undefined}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
        <div className="game-seats-col game-seats-col--right">
          {rightSeats.map((seatIndex) => {
            const a = assignments[seatIndex];
            return (
              <GameSeat
                key={seatIndex}
                seatIndex={seatIndex}
                side="right"
                assignment={a}
                testStatus={a !== null ? testResults[a]?.status : undefined}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
      </div>
      <GameBottomActions
        allSeatsAssigned={allSeatsAssigned}
        allTestsPassed={allTestsPassed}
        isTesting={isTesting}
        onClickTest={handleClickTest}
        onClickEnterNight={handleClickEnterNight}
      />
      {import.meta.env.DEV && (
        <button
          type="button"
          className="game-stage-debug"
          onClick={() => {
            transitionToStage(
              stage.phase === 'day'
                ? { dayNumber: stage.dayNumber, phase: 'night' }
                : { dayNumber: stage.dayNumber + 1, phase: 'day' },
            );
          }}
        >
          [debug] 推进
        </button>
      )}
      <ModelPicker
        open={pickerSeat !== null}
        onClose={() => setPickerSeat(null)}
        currentAssignment={pickerSeat !== null ? assignments[pickerSeat] : null}
        usedSlots={assignments.filter((s): s is number => s !== null)}
        onPick={handlePickModel}
      />
      <RulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} />
      <ExitConfirmModal
        open={exitConfirmOpen}
        onClose={() => setExitConfirmOpen(false)}
        onConfirm={handleConfirmExit}
      />
    </main>
  );
}
```

### 5.9 `LobbyHome.tsx` / `StartModal.tsx`（不修改）

STEP-03 已经把 `onEnterGame` 一路从 `App` → `LobbyHome` → `StartModal` 传递到位，本步骤无需再改。

---

## 6. CSS 追加（追加到 `src/styles.css` 末尾）

### 6.1 顶栏 + 阶段指示器

```css
/* === STEP-04: 游戏顶栏 === */

.game-top-bar {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 5;
  display: flex;
  gap: 10px;
}

.game-top-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 120ms ease, transform 120ms ease;
}

.game-top-btn:hover {
  background: rgba(0, 0, 0, 0.7);
  transform: scale(1.05);
}

.game-top-btn:focus-visible {
  outline: 2px solid #ffd166;
  outline-offset: 2px;
}

/* === STEP-04: 阶段指示器 === */

.game-stage-indicator {
  position: absolute;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 6px 18px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
}

.game-stage-icon--day {
  color: #ffd24a;
  filter: drop-shadow(0 0 8px rgba(255, 200, 80, 0.7));
}

.game-stage-icon--night {
  color: #c8d4ff;
  filter: drop-shadow(0 0 8px rgba(180, 200, 255, 0.7));
}

.game-stage-day-label {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  text-shadow: 0 2px 6px rgba(0, 0, 0, 0.85);
}
```

### 6.2 阶段切换 overlay（GamePage 内部）

```css
/* === STEP-04: 白天/黑夜切换 overlay === */

.game-stage-overlay {
  position: absolute;
  inset: 0;
  z-index: 4;
  background: #050507;
  pointer-events: none;
  opacity: 0;
}

.game-stage-overlay--fade-out {
  opacity: 1;
  transition: opacity 600ms ease-in;
  pointer-events: all;
}

.game-stage-overlay--fade-in {
  opacity: 0;
  transition: opacity 800ms ease-out;
  pointer-events: none;
}
```

注意：`.game-stage-overlay` 与 STEP-03 的 `.page-transition-overlay` (z-index 9999) **是两套不同的 overlay**。前者作用域是 GamePage 内部（白天/黑夜切换），后者作用域是 App 层级（lobby ↔ game 切换）。

### 6.3 双聊天框

```css
/* === STEP-04: 双聊天框 === */

.game-chat {
  position: absolute;
  top: 80px;
  left: clamp(118px, 25vw, 220px);
  right: clamp(118px, 25vw, 220px);
  bottom: clamp(200px, 20vh, 260px);
  z-index: 2;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  pointer-events: none;
}

.game-chat-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.4);
  pointer-events: auto;
  overflow: hidden;
  min-height: 200px;
}

.game-chat-panel--wolf {
  border-color: rgba(220, 80, 80, 0.75);
  background: rgba(60, 10, 10, 0.4);
}

.game-chat-header {
  padding: 8px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.game-chat-panel--wolf .game-chat-header {
  background: rgba(220, 80, 80, 0.18);
  border-bottom-color: rgba(220, 80, 80, 0.4);
}

.game-chat-body {
  flex: 1;
  padding: 8px 12px;
  overflow-y: auto;
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  line-height: 1.6;
}

.game-chat-footer {
  padding: 8px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
}

.game-chat-input {
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
}

.game-chat-input:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
```

### 6.4 底部按钮区

```css
/* === STEP-04: 底部按钮区 === */

.game-bottom-actions {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.game-bottom-btn {
  min-width: 220px;
  padding: 10px 28px;
  border: none;
  border-radius: 999px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  transition: background 120ms ease, transform 120ms ease;
}

.game-bottom-btn:disabled {
  background: rgba(28, 28, 34, 0.62);
  cursor: not-allowed;
  color: rgba(255, 255, 255, 0.6);
}

.game-bottom-btn--test:not(:disabled) {
  background: rgba(22, 72, 148, 0.94);
}
.game-bottom-btn--test:not(:disabled):hover {
  background: rgba(28, 86, 176, 0.98);
  transform: translateY(-1px);
}

.game-bottom-btn--night:not(:disabled) {
  background: rgba(118, 34, 38, 0.94);
}
.game-bottom-btn--night:not(:disabled):hover {
  background: rgba(150, 42, 46, 0.98);
  transform: translateY(-1px);
}

.game-stage-debug {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 5;
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
}
```

### 6.5 席位测试态（叠加到 STEP-03 的 `.game-seat-circle`）

```css
/* === STEP-04: 席位测试态 === */

.game-seat-circle--testing {
  filter: grayscale(0.9) brightness(0.55);
  pointer-events: none;
}

.game-seat-dots {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  pointer-events: none;
}

.game-seat-dots .dot {
  width: 7px;
  height: 7px;
  background: #fff;
  border-radius: 50%;
  opacity: 0.3;
  animation: game-seat-dot-pulse 1.2s infinite;
}

.game-seat-dots .dot-2 {
  animation-delay: 0.2s;
}

.game-seat-dots .dot-3 {
  animation-delay: 0.4s;
}

@keyframes game-seat-dot-pulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1.15);
  }
}

.game-seat-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #050507;
  pointer-events: none;
}

.game-seat--right .game-seat-badge {
  right: auto;
  left: -4px;
}

.game-seat-badge--pass {
  background: #34c759;
  color: #fff;
}

.game-seat-badge--fail {
  background: #ff3b30;
  color: #fff;
}
```

### 6.6 规则弹窗 + 退出确认弹窗

```css
/* === STEP-04: 规则弹窗 === */

.rules-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rules-modal-panel {
  width: min(920px, 92vw);
  max-height: min(86vh, 820px);
  overflow: hidden;
}

.rules-modal-body {
  overflow-y: auto;
}

.rules-modal-error {
  color: #ff8a85;
  font-size: 14px;
  padding: 10px 0;
}

/* === STEP-04: 退出确认弹窗 === */

.exit-confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(14px, 4vw, 32px);
}

.exit-confirm-panel {
  width: min(430px, 94vw);
  padding: 24px;
  overflow: hidden;
  border-radius: 8px;
}

.exit-confirm-title {
  margin: 0 42px 10px 0;
  font-size: clamp(23px, 3vw, 30px);
  line-height: 1.2;
}

.exit-confirm-text {
  margin: 0 0 20px;
  font-size: 15px;
  line-height: 1.6;
}

.exit-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
}

.exit-confirm-btn {
  min-width: 104px;
  min-height: 42px;
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
```

---

## 7. 修改清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `public/assets/game/rules.md` | 新建（去围栏拷贝） | 规则文档运行时来源 |
| `public/assets/game/quick_assign_raccoon.png` | 新建（拷贝） | 左下角一键分配装饰入口 |
| `src/lib/gameStage.ts` | 新建 | DayPhase / GameStage / INITIAL_STAGE |
| `src/lib/modelTest.ts` | 新建 | testModelConnection / readModelConfig + 类型 |
| `src/App.tsx` | 修改 | 增加 `targetPageRef` 与 `handleExitGame`；将 `<GamePage />` 改成 `<GamePage onExitGame={handleExitGame} />` |
| `src/components/Game/GameTopBar.tsx` | 新建 | 右上规则 + 退出按钮 |
| `src/components/Game/StageIndicator.tsx` | 新建 | 太阳/月亮 + 数字 |
| `src/components/Game/GameChat.tsx` | 新建 | 通用 + 狼人双聊天框 |
| `src/components/Game/GameBottomActions.tsx` | 新建 | 测试 + 夜深了… 两按钮 |
| `src/components/Game/RulesModal.tsx` | 新建 | fetch rules.md + 轻量解析为可读正文 |
| `src/components/Game/ExitConfirmModal.tsx` | 新建 | 游戏页自有紧凑确认面板 + 取消 / 确认两按钮 |
| `src/components/Game/GameSeat.tsx` | 修改 | 新增 `testStatus` prop + 三点动画 + ✓/✗ 徽标 |
| `src/components/Game/ModelPicker.tsx` | 修改 | 改成游戏页自有弹窗；已占用模型卡片保留右下角图标型「交换」按钮 |
| `src/components/Game/GamePage.tsx` | 修改 | 整合 stage / overlay / 各子组件 / 测试逻辑 / DEV [debug] 按钮 |
| `src/styles.css` | 修改 | 追加顶栏 / 阶段指示 / overlay / 聊天 / 底部按钮 / 席位测试态 / 规则与退出弹窗样式 |
| `plan.md` | 已修改（参考） | 已新增 §14.14 |
| `architecture.md` | 已修改（参考） | 已新增 §18.13 |
| `docs/specs/STEP-04-game-page-enhancements.md` | 新建（本文件） | GPT 实施手册 + 验收指标 |

---

## 8. 实施顺序

1. 拷贝 `素材/Wolven Hunt游戏规则.md` → `public/assets/game/rules.md`，去掉首末 ` ``` ` 围栏；首行必须是 `# Wolven Hunt 游戏规则`。
2. 新建 `src/lib/gameStage.ts` 与 `src/lib/modelTest.ts`。
3. 修改 `src/App.tsx`：增加 `targetPageRef` + `handleExitGame`，把 onExitGame 传给 GamePage。
4. 新建顺序：`GameTopBar` → `StageIndicator` → `GameChat` → `GameBottomActions` → `RulesModal` → `ExitConfirmModal`。
5. 修改 `GameSeat.tsx`：testStatus prop + 三点动画 JSX + ✓/✗ 徽标。
6. 修改 `ModelPicker.tsx`：移除对 `LobbyModal` 的复用，改成游戏页自有弹窗外壳；已占用模型卡片主体置灰 disabled，但右下角提供图标型「交换」按钮。
7. 重写 `GamePage.tsx`：整合 stage / overlay / 各子组件 / 测试逻辑 / DEV 推进按钮 / 模型交换逻辑。
8. 追加 `src/styles.css`：顶栏 / 阶段指示 / overlay / 聊天 / 底部按钮 / 席位测试态 / 模型交换图标按钮 / 规则与退出弹窗。
9. 验证：`npm run typecheck` + `npm run build`。
10. 浏览器手测：参见 §9 验收指标。

---

## 9. 验收指标

### A. 资产

| ID | 检查项 | 验证手段 |
|---|---|---|
| A1 | `public/assets/game/rules.md` 存在 | `ls public/assets/game/rules.md` |
| A2 | rules.md 首行为 `# Wolven Hunt 游戏规则` | `head -1 public/assets/game/rules.md` |
| A3 | rules.md 不含 ` ```md ` / ` ``` ` 围栏 | `grep -E '^\`\`\`' public/assets/game/rules.md` 无命中 |
| A4 | `素材/Wolven Hunt游戏规则.md` 原文件未改名/删除 | `git status` |

### B. 顶栏

| ID | 检查项 |
|---|---|
| B1 | 游戏页右上角显示规则（BookOpen）+ 退出（X）两个 40×40 圆形按钮 |
| B2 | 点规则 → RulesModal 打开，正文加载并展示 |
| B3 | 点退出 → ExitConfirmModal 打开 |
| B4 | 规则弹窗与退出弹窗均保留 X / Esc / 遮罩三种关闭路径 |

### C. 阶段指示与背景切换

| ID | 检查项 |
|---|---|
| C1 | 顶部中心显示太阳图标 + `第1天`（白天默认），图标和文字垂直居中 |
| C2 | DEV 模式右下角显示 `[debug] 推进` 按钮；生产 build 不出现 |
| C3 | 点 [debug] 推进 → 600ms 黑屏（`.game-stage-overlay--fade-out`）→ 切夜晚背景 + 月亮图标 → 800ms 亮起（`.game-stage-overlay--fade-in`）→ overlay opacity 回到 0 |
| C4 | 再次推进 → dayNumber +1 → 切回白天背景 |
| C5 | aria-label 形如 `第 N 天 白天/黑夜` |
| C6 | `.game-stage-overlay` 不与 App 层 `.page-transition-overlay` 冲突（两个 overlay 同时切换不会卡死） |

### D. 双聊天框

| ID | 检查项 |
|---|---|
| D1 | 中心区域同时显示左右两个聊天框 |
| D2 | 左标题为「通用聊天框」；右标题为「狼人聊天框」 |
| D3 | 狼人栏使用红色调边框（`rgba(220, 80, 80, ...)`） |
| D4 | 输入框 `disabled`，鼠标悬停 cursor 显示 not-allowed |
| D5 | 聊天区不遮挡席位列点击（席位仍可点开 ModelPicker） |

### E. 模型连通性测试

| ID | 检查项 |
|---|---|
| E1 | 左下角显示小浣熊装饰入口与「一键分配」按钮；测试中 disabled |
| E2 | 点击「一键分配」后 8 个席位全部填满，8 个 model slot 均只出现一次 |
| E3 | 一键分配只修改 GamePage 内存 `assignments`，不写 `localStorage` / 事件日志 / replay；触发后清空旧 testResults 和测试提示 |
| E4 | 8 席未填满时「测试模型连通性」按钮灰态 disabled |
| E5 | 8 席填满后「测试模型连通性」按钮蓝色可点 |
| E6 | 点击后所有已分配席位头像变灰（grayscale + brightness 0.55）+ 三点 pulse 动画 |
| E7 | 测试中按钮文字变「正在测试中」且 disabled；所有已分配头像至少展示一次可感知的三点 pulse loading；「夜深了…」也保持 disabled |
| E8 | 测试完成后每个已分配席位显示 ✓（绿）或 ✗（红）徽标，底部显示通过数量摘要 |
| E9 | `testModelConnection` 用 `POST {baseUrl}/chat/completions`，Bearer 鉴权，`max_tokens: 1`，超时 15s |
| E10 | 任一席位 ✗ → 「夜深了…」仍 disabled |
| E11 | 全部 ✓ → 「夜深了…」变红可点 |
| E12 | 在 ModelPicker 中重新分配某席位时，对应 slot 的 testResult 被清空，再次需要测试 |
| E13 | testResults 仅内存（grep `localStorage` 在 GamePage / modelTest.ts 仅出现读，不出现写 testResults 相关 key） |
| E14 | 8 席填满后打开任一席位，已占用模型卡片主体置灰 disabled，但右下角图标型「交换」按钮可点击且不显示文字标签 |
| E15 | 点击交换图标后当前席位与目标模型所在席位互换；8 个 model slot 仍唯一，不写 `localStorage` / 事件日志 / replay，不清空按 model slot 记录的 testResults |

### F. 进入夜晚

| ID | 检查项 |
|---|---|
| F1 | 全 ✓ 后点「夜深了…」→ `.game-stage-overlay--fade-out` 600ms |
| F2 | 黑屏后 `<img class="game-bg">` src 切到 `/assets/game/night_bg.png`，StageIndicator 切月亮 |
| F3 | 800ms 亮起后 overlay opacity 回到 0 |
| F4 | dayNumber 不变（仍为 1） |

### G. 退出流程

| ID | 检查项 |
|---|---|
| G1 | 点右上 X → ExitConfirmModal 打开，含取消 / 确认两按钮 |
| G2 | 点取消 → 弹窗关闭，仍在游戏页 |
| G3 | 点确认 → 弹窗关闭 → App 层 600ms 黑屏 → 切回大厅 → 800ms 亮起 |
| G4 | 切回大厅后 BGM 仍静音（不自动还原），右上角浮动按钮仍可手动取消静音 |
| G5 | 再次进入游戏：席位 / 测试结果 / 阶段全部初态（白天 + dayNumber 1 + 全空席位） |

### H. 边界约束

| ID | 检查项 | 命令 |
|---|---|---|
| H1 | `fetch(` 仅在 `src/components/Game/RulesModal.tsx` 与 `src/lib/modelTest.ts` 出现 | `grep -RInE "fetch\(" src/` |
| H2 | `WebSocket` / `EventSource` / `axios` / `XMLHttpRequest` 全树无命中 | `grep -RInE "WebSocket\|EventSource\|axios\|XMLHttpRequest" src/` |
| H3 | `RuleEngine` / `Referee` / `FSM` / `wolven_hunt` 在 `src/components/Game` / `src/App.tsx` / `src/lib` 无命中 | `grep -RInE "RuleEngine\|Referee\|FSM\|wolven_hunt" src/components/Game src/App.tsx src/lib` |
| H4 | `localStorage` 在 `src/components/Game` 无写入；`src/lib/modelTest.ts` 仅读 | `grep -RIn "localStorage" src/components/Game src/lib/modelTest.ts` 命中行均为 `getItem` |

### I. 构建

| ID | 检查项 |
|---|---|
| I1 | `npm run typecheck` 通过（无 TS 错误） |
| I2 | `npm run build` 通过 |
| I3 | 生产 build `dist/` 中 `[debug]` 文案被 tree-shake | `grep -r "\\[debug\\]" dist/` 无命中 |
| I4 | dev server 启动后游戏页无白屏 / Console 无 error |

### J. 文档

| ID | 检查项 |
|---|---|
| J1 | `plan.md` §14.14 存在，覆盖：顶栏 / 阶段切换 / 双聊天 / 测试流 / 退出流 / 同源 fetch 豁免 / 跨域 LLM 测试豁免 |
| J2 | `architecture.md` §18.13 与 §14.14 语义一致 |
| J3 | 本文件存在，含完整 TSX 骨架 + CSS 片段 + A–J 验收指标 |

---

## 10. 不在本步骤范围

- 阶段自动推进（`dayNumber` / `phase` 由引擎驱动）。
- 真实倒计时机制（暂不实现，留给后续步骤）。
- 聊天消息渲染、输入、发送、广播。
- 玩家身份分配（`.game-seat-role` 仍 `display: none`）。
- 狼人聊天框的可见性脱敏（接入 Referee 后再做）。
- 完整 markdown 富文本渲染库（仅允许本模块轻量解析标题 / 列表 / 加粗，避免引入新依赖）。
- 移动端 / 窄屏适配。
- 模型测试结果持久化。
- 「夜深了…」之后的真实游戏逻辑（仅触发阶段切换为夜晚，不实现夜晚行动）。

---

## 11. 风险登记

- **API key 明文传输**：`testModelConnection` 把 apiKey 放在 `Authorization: Bearer` 头中。HTTPS 部署下浏览器自动加密；HTTP / dev server 下网络层可见。文档明示用户**仅在本地 dev 或 HTTPS 部署使用**。
- **CORS 失败**：依赖 LLM 提供商的 CORS 策略。多数主流网关支持浏览器直连，不支持的提供商会被用户感知为 ✗（不静默吞错）。
- **过渡 overlay 嵌套**：`.page-transition-overlay`（z-index 9999）与 `.game-stage-overlay`（z-index 4）作用域分明；两者**不要**复用同一个 React state，避免互相打架。
- **DEV 推进按钮**：仅供开发期预览，生产构建必须被 tree-shake；用 `import.meta.env.DEV` 守卫即可（Vite 自动消除）。
- **替换素材时**：rules.md 由 `素材/Wolven Hunt游戏规则.md` 派生；如未来素材文档更新，需重新执行步骤 1（去围栏拷贝），不得直接编辑 `public/assets/game/rules.md`。
