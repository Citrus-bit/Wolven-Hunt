# STEP-02 大厅弹窗与系统设置 执行规格

> **本规格只覆盖第二步交付：大厅弹窗层 + 系统设置**。规则契约见 `plan.md` §1–§6 与 `architecture.md` §1–§16；前端壳契约见 `plan.md` §14（含新增 §14.10–§14.12）与 `architecture.md` §18（含新增 §18.9–§18.11）。本文件是 GPT 实施手册 + Kiro 验收指标的镜像。
>
> **硬约束**（与 STEP-01 一致，仍然有效）：
>
> 1. 不得修改 `plan.md` §1–§6、`architecture.md` §1–§16；如有冲突先回到上层修订流程。
> 2. 前端代码不得 `import` 任何 `src/wolven_hunt/*`；不得读取 `configs/*`；不得发起 HTTP / WebSocket / SSE 请求。**模型配置字段（baseUrl / apiKey / modelName）只写 `localStorage`，不被任何 fetch 消费**。
> 3. 不得改名 / 移动 / 删除 `素材/` 目录下的任何原始文件。
> 4. 所有运行时静态资源命名为 ASCII 小写蛇形。

---

## 1. 交付目标

完成后用户在浏览器打开本地 dev server 应能看到（叠加在 STEP-01 已交付的大厅基础上）：

1. 点击大厅下方任一按钮（开始游戏 / 历史复盘 / 系统设置），打开同一种弹窗外壳，弹窗背景图为 `素材/大厅设置栏.png`，按钮 kind 切换内部内容。
2. **开始游戏** 弹窗：两段提示文案 + 「进入游戏」按钮（点击仅 `console.log('[lobby] enter game')` 并关闭弹窗）。
3. **历史复盘** 弹窗：「功能开发中，敬请期待。」+ 「未来可让用户以上帝视角逐步还原推理过程。」两段占位文案。
4. **系统设置** 弹窗：
   - 0–100 整数音量滑块，实时驱动 BGM 音量；松开后写 `localStorage.wolven_hunt.lobby.volume`；刷新后保持。
   - 8 条模型条目，每条含中文昵称（只读）、对应图标（PNG）、`baseurl` / `apikey` / `modelName` 三个输入框；初始全空，用户自填后 300ms debounce 写入 `localStorage.wolven_hunt.lobby.model_config.{slot}`；刷新后保持。
5. 三种关闭方式：右上角 `<X />` 按钮、`Esc` 键、点击遮罩区。

---

## 2. 资源准备

### 2.1 拷贝资源（保留原始素材不变）

将 `素材/` 中以下 9 个文件复制到 `public/assets/lobby/`，使用 ASCII 小写蛇形目标文件名：

| 源 | 目标 |
|---|---|
| `素材/大厅设置栏.png` | `public/assets/lobby/settings_panel_bg.png` |
| `素材/minimax老师.png` | `public/assets/lobby/model_icon_minimax_laoshi.png` |
| `素材/万问.png` | `public/assets/lobby/model_icon_wanwen.png` |
| `素材/光之明面.png` | `public/assets/lobby/model_icon_guangzhimingmian.png` |
| `素材/大米.png` | `public/assets/lobby/model_icon_dami.png` |
| `素材/学霸.png` | `public/assets/lobby/model_icon_xueba.png` |
| `素材/小豆包儿.png` | `public/assets/lobby/model_icon_xiaodoubao.png` |
| `素材/海瑟音.png` | `public/assets/lobby/model_icon_haiseyin.png` |
| `素材/阿元替身版.png` | `public/assets/lobby/model_icon_ayuan_tishenban.png` |

**`素材/` 原文件不得改名 / 删除 / 移动。** 复制方式自由（`cp` / Finder / Windows 资源管理器），只要目标文件名与上表完全一致即可。

### 2.2 资源约束

- 8 张图标的 ASCII 文件名是用 pinyin 转写得到，不做 provider 推断；中文昵称是 UI 标签，由 §3.1 的 TS 配置驱动。
- `settings_panel_bg.png` 约 1.7MB；首次打开弹窗时建议 `loading="eager"` 或 `<link rel="preload" as="image">` 预热，避免点击后白屏。

---

## 3. 数据模型

### 3.1 `src/lib/modelConfigs.ts`

新建文件，导出 8 个 slot 的静态配置 + 用户输入类型 + 空值常量：

```ts
export type ModelConfigSlot = {
  /** 0..7，固定 slot 索引 */
  slot: number;
  /** 中文昵称，UI 标签，不进 localStorage */
  nickname: string;
  /** 图标 ASCII 路径，runtime 读 */
  iconPath: string;
};

export type ModelConfigUserInput = {
  /** API base URL，留空表示未配置 */
  baseUrl: string;
  /** API key，留空表示未配置 */
  apiKey: string;
  /** model name，留空表示未配置 */
  modelName: string;
};

export const MODEL_SLOTS: readonly ModelConfigSlot[] = [
  { slot: 0, nickname: 'minimax老师',   iconPath: '/assets/lobby/model_icon_minimax_laoshi.png' },
  { slot: 1, nickname: '万问',          iconPath: '/assets/lobby/model_icon_wanwen.png' },
  { slot: 2, nickname: '光之明面',      iconPath: '/assets/lobby/model_icon_guangzhimingmian.png' },
  { slot: 3, nickname: '大米',          iconPath: '/assets/lobby/model_icon_dami.png' },
  { slot: 4, nickname: '学霸',          iconPath: '/assets/lobby/model_icon_xueba.png' },
  { slot: 5, nickname: '小豆包儿',      iconPath: '/assets/lobby/model_icon_xiaodoubao.png' },
  { slot: 6, nickname: '海瑟音',        iconPath: '/assets/lobby/model_icon_haiseyin.png' },
  { slot: 7, nickname: '阿元替身版',    iconPath: '/assets/lobby/model_icon_ayuan_tishenban.png' },
] as const;

export const EMPTY_USER_INPUT: ModelConfigUserInput = {
  baseUrl: '',
  apiKey: '',
  modelName: '',
};

export const VOLUME_DEFAULT = 80;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 100;
```

### 3.2 localStorage 协议

| key | value | 默认值 | 写入触发 |
|---|---|---|---|
| `wolven_hunt.lobby.volume` | number 字符串，0–100 | `'80'` | 用户拖动音量滑块 |
| `wolven_hunt.lobby.muted` | `'true'` / `'false'` | `'true'`（首次） | 用户切静音 |
| `wolven_hunt.lobby.model_config.{slot}` | JSON `{baseUrl, apiKey, modelName}` | 整体不存在 | 用户改写任一字段（debounce 300ms） |

- key 命名以 `wolven_hunt.lobby.` 为命名空间。
- 0–100 整数音量在 hook 内换算 `audio.volume = volume / 100`。
- 模型配置按 slot 存独立 key，便于 partial 更新；不存在 key 视为未配置。
- 读 / 写失败（QuotaExceededError、SecurityError、JSON parse error）走 try/catch，仅 `console.warn`，不阻塞 UI。
- 不允许写入 §3.2 三类 key 之外的任何 `localStorage` key。

### 3.3 `src/hooks/useLocalStorage.ts`

新建通用 hook：

```ts
import { useCallback, useEffect, useRef, useState } from 'react';

export type LocalStorageSerializer<T> = {
  read: (raw: string) => T;
  write: (value: T) => string;
};

export function useLocalStorage<T>(
  key: string,
  initialValue: T,
  serializer: LocalStorageSerializer<T>,
  options?: { debounceMs?: number }
): [T, (next: T) => void] {
  const debounceMs = options?.debounceMs ?? 0;

  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initialValue;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) return initialValue;
      return serializer.read(raw);
    } catch (err) {
      console.warn(`[lobby] failed to read localStorage key=${key}`, err);
      return initialValue;
    }
  });

  const timer = useRef<number | null>(null);

  const writeNow = useCallback((next: T) => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(key, serializer.write(next));
    } catch (err) {
      console.warn(`[lobby] failed to write localStorage key=${key}`, err);
    }
  }, [key, serializer]);

  const update = useCallback((next: T) => {
    setValue(next);
    if (debounceMs > 0) {
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => writeNow(next), debounceMs);
    } else {
      writeNow(next);
    }
  }, [debounceMs, writeNow]);

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  return [value, update];
}
```

要点：
- 首次渲染从 `localStorage` 读，解析失败 fallback 到 `initialValue`；不抛错。
- `debounceMs > 0` 时 setter 走 debounce；模型配置用 `300`，音量与静音用 `0`。
- 卸载时清 timer。
- SSR-safe：`typeof window === 'undefined'` 直接返回 `initialValue`。

### 3.4 `src/hooks/useLobbyAudio.ts` 增量改造

现有快照类型扩展为：

```ts
type AudioSnapshot = { muted: boolean; unlocked: boolean; volume: number };
```

行为：
- 模块初始化时从 `localStorage` 读 `wolven_hunt.lobby.volume`（缺省 80）与 `wolven_hunt.lobby.muted`（缺省 `'true'`），应用到 `<audio>` 元素：`audio.volume = snapshot.volume / 100`、`audio.muted = snapshot.muted`。
- 暴露 `volume: number`（0–100 整数）与 `setVolume(v: number)`；setter 内 clamp `[0, 100]`，更新 snapshot + audio + 立即 `localStorage.setItem('wolven_hunt.lobby.volume', String(v))`。
- 现有 `toggleMute` 行为补充：写 `localStorage.setItem('wolven_hunt.lobby.muted', String(audio.muted))`。
- `ensureUnlock` 行为不变；解锁后 audio.volume 维持当前 volume，不重置。
- volume === 0 时**不**自动设置 muted（语义独立）。
- 写失败仅 `console.warn`，不阻塞 UI。

---

## 4. 组件契约

### 4.1 `src/components/Lobby/LobbyModal.tsx`（通用外壳）

Props：

```ts
type LobbyModalProps = {
  open: boolean;
  onClose: () => void;
  /** 弹窗标题，必填，用于 aria-labelledby */
  title: string;
  /** 弹窗主体内容 */
  children: React.ReactNode;
};
```

行为：
- `open === false` 直接返回 `null`，不挂载。
- 通过 `createPortal` 渲染到 `document.body`，避免被 `LobbyHome` 的 transform 影响。
- 关闭：① 右上角 `<X />` 按钮（lucide-react）；② `Esc` 键（监听 `window.keydown`）；③ 点击遮罩区（`onMouseDown` 在遮罩根，`stopPropagation` 在弹窗主体）。三者都调用 `onClose`。
- 焦点：`open` 变 `true` 时记录 `document.activeElement`，把焦点移到弹窗根；`open` 变 `false` 时调用记录元素的 `.focus()`。
- 加 `role="dialog"`、`aria-modal="true"`、`aria-labelledby={titleId}`；标题元素 `id={titleId}`，用 `useId` 生成。
- 弹窗主体由 `<img src="/assets/lobby/settings_panel_bg.png" loading="eager" />` 铺底，`object-fit: contain`，主内容用 `position: absolute` 落在图上沿。
- 不锁 body scroll（首页本来 `overflow: hidden`）。

骨架：

```tsx
import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type LobbyModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
};

export function LobbyModal({ open, onClose, title, children }: LobbyModalProps) {
  const titleId = useId();
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    rootRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      lastFocusedRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="lobby-modal-backdrop" onMouseDown={onClose}>
      <div
        className="lobby-modal-frame"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={rootRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <img src="/assets/lobby/settings_panel_bg.png" alt="" className="lobby-modal-bg" loading="eager" />
        <button type="button" className="lobby-modal-close" aria-label="关闭" onClick={onClose}>
          <X size={20} />
        </button>
        <div className="lobby-modal-content">
          <h2 id={titleId} className="lobby-modal-title">{title}</h2>
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
```

### 4.2 `src/components/Lobby/modals/StartModal.tsx`

```tsx
import { LobbyModal } from '../LobbyModal';

type StartModalProps = { open: boolean; onClose: () => void };

export function StartModal({ open, onClose }: StartModalProps) {
  const enterGame = () => {
    console.log('[lobby] enter game');
    onClose();
  };
  return (
    <LobbyModal open={open} onClose={onClose} title="开始游戏">
      <p className="lobby-modal-text">尊敬的玩家您好，该游戏目前处于测试版本，所有 api key 均免费开放，请享受游戏吧～</p>
      <p className="lobby-modal-tip">温馨提示：玩家可以选择人机对战或者 AI 内战，具体游戏规则可在局内查看。</p>
      <button type="button" className="lobby-modal-cta" onClick={enterGame}>进入游戏</button>
    </LobbyModal>
  );
}
```

### 4.3 `src/components/Lobby/modals/HistoryModal.tsx`

```tsx
import { LobbyModal } from '../LobbyModal';

type HistoryModalProps = { open: boolean; onClose: () => void };

export function HistoryModal({ open, onClose }: HistoryModalProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="历史复盘">
      <p className="lobby-modal-text">功能开发中，敬请期待。</p>
      <p className="lobby-modal-tip">未来可让用户以上帝视角逐步还原推理过程。</p>
    </LobbyModal>
  );
}
```

### 4.4 `src/components/Lobby/modals/VolumeSlider.tsx`

```tsx
import { useLobbyAudio } from '../../../hooks/useLobbyAudio';

export function VolumeSlider() {
  const { volume, setVolume } = useLobbyAudio();
  return (
    <div className="lobby-volume-slider">
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={volume}
        onChange={(e) => setVolume(Number(e.target.value))}
        aria-label="BGM 音量"
      />
      <span className="lobby-volume-value">{volume}</span>
    </div>
  );
}
```

### 4.5 `src/components/Lobby/modals/ModelConfigList.tsx`

包含 `ModelConfigRow` 内部组件，map `MODEL_SLOTS` 渲染 8 行。每行使用独立的 `useLocalStorage` 实例，key 为 `wolven_hunt.lobby.model_config.{slot}`，debounce 300ms，serializer 用 `JSON.parse` / `JSON.stringify`，缺省值 `EMPTY_USER_INPUT`。

```tsx
import { MODEL_SLOTS, EMPTY_USER_INPUT, type ModelConfigSlot, type ModelConfigUserInput } from '../../../lib/modelConfigs';
import { useLocalStorage } from '../../../hooks/useLocalStorage';

const SERIALIZER = {
  read: (raw: string) => {
    try {
      const parsed = JSON.parse(raw);
      return {
        baseUrl: typeof parsed.baseUrl === 'string' ? parsed.baseUrl : '',
        apiKey: typeof parsed.apiKey === 'string' ? parsed.apiKey : '',
        modelName: typeof parsed.modelName === 'string' ? parsed.modelName : '',
      };
    } catch {
      return EMPTY_USER_INPUT;
    }
  },
  write: (value: ModelConfigUserInput) => JSON.stringify(value),
};

function ModelConfigRow({ slot }: { slot: ModelConfigSlot }) {
  const [config, setConfig] = useLocalStorage<ModelConfigUserInput>(
    `wolven_hunt.lobby.model_config.${slot.slot}`,
    EMPTY_USER_INPUT,
    SERIALIZER,
    { debounceMs: 300 }
  );
  const update = (patch: Partial<ModelConfigUserInput>) => setConfig({ ...config, ...patch });

  return (
    <div className="lobby-model-row">
      <img src={slot.iconPath} alt={slot.nickname} className="lobby-model-icon" />
      <span className="lobby-model-nickname">{slot.nickname}</span>
      <input type="text"     value={config.baseUrl}   onChange={(e) => update({ baseUrl: e.target.value })}   placeholder="baseurl"   autoComplete="off" />
      <input type="password" value={config.apiKey}    onChange={(e) => update({ apiKey: e.target.value })}    placeholder="apikey"    autoComplete="off" />
      <input type="text"     value={config.modelName} onChange={(e) => update({ modelName: e.target.value })} placeholder="model 名" autoComplete="off" />
    </div>
  );
}

export function ModelConfigList() {
  return (
    <div className="lobby-model-list">
      {MODEL_SLOTS.map((slot) => (
        <ModelConfigRow key={slot.slot} slot={slot} />
      ))}
    </div>
  );
}
```

### 4.6 `src/components/Lobby/modals/SettingsModal.tsx`

```tsx
import { LobbyModal } from '../LobbyModal';
import { VolumeSlider } from './VolumeSlider';
import { ModelConfigList } from './ModelConfigList';

type SettingsModalProps = { open: boolean; onClose: () => void };

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="系统设置">
      <section className="lobby-settings-volume">
        <h3>音量</h3>
        <VolumeSlider />
      </section>
      <section className="lobby-settings-models">
        <h3>模型配置</h3>
        <ModelConfigList />
      </section>
    </LobbyModal>
  );
}
```

### 4.7 `src/components/Lobby/LobbyHome.tsx` 装配增量

在现有 LobbyHome 中：
- 增加 `const [activeModal, setActiveModal] = useState<LobbyAction | null>(null);`
- 给现有 `<LobbyButtons />` 加 `onAction={(kind) => setActiveModal(kind)}`。
- 在 `<MuteToggle />` 之后渲染：

```tsx
<StartModal    open={activeModal === 'start'}    onClose={() => setActiveModal(null)} />
<HistoryModal  open={activeModal === 'history'}  onClose={() => setActiveModal(null)} />
<SettingsModal open={activeModal === 'settings'} onClose={() => setActiveModal(null)} />
```

`LobbyButtons.tsx` 不需要改动（`onAction` 回调已就位）。

---

## 5. 样式（追加到 `src/styles.css`）

新增类与 z-index：

| 类名 | 作用 | z-index |
|---|---|---|
| `.lobby-modal-backdrop` | 遮罩层 | 5 |
| `.lobby-modal-frame` | 背景图容器 | 6 |
| `.lobby-modal-content` | 内容区（绝对定位在图上） | 7 |
| `.lobby-modal-close` | 右上角关闭按钮 | 8 |

视觉规范：
- 遮罩 `position: fixed; inset: 0; background: rgba(0,0,0,0.55); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center;`。
- `.lobby-modal-frame` 使用 `position: relative;`；内嵌 `<img class="lobby-modal-bg">` 作为背景图，`max-width: min(720px, 92vw); max-height: 86vh; object-fit: contain;`。
- `.lobby-modal-content` 用 `position: absolute; inset: 0; padding: clamp(24px, 6vh, 48px) clamp(24px, 6vw, 64px); overflow-y: auto;`，文字与控件落在背景图上。
- `.lobby-modal-close` 圆形按钮，`position: absolute; top: 12px; right: 12px; width: 36px; height: 36px; border-radius: 50%; background: rgba(0,0,0,0.45);` hover `0.65`。
- `.lobby-modal-title` 字号 `clamp(20px, 3vh, 28px)`，颜色 `#fff7df`，居中或左对齐均可。
- `.lobby-modal-text` / `.lobby-modal-tip` 颜色 `#f8f4ec`，行高 1.6；tip 字号略小、透明度略低。
- `.lobby-modal-cta` 浅金色背景，深色文字，`padding: 10px 24px; border-radius: 999px;` hover `transform: scale(1.03);`。
- 表单 input：浅色半透明背景 `rgba(255,255,255,0.92)`，深色文字 `#1a1a1a`，`border-radius: 6px; padding: 6px 10px;` focus-visible outline 用既有金色 `rgba(255,232,166,0.95)`。
- `.lobby-volume-slider` 使用原生 `<input type="range">`；不强求像素一致的 thumb 自定义。
- `.lobby-model-row` `display: grid; grid-template-columns: 36px auto 1fr 1fr 1fr; gap: 10px; align-items: center;`。
- 移动端 `@media (max-width: 640px)`：背景图 `max-width: 96vw`；`.lobby-model-row` 改 `grid-template-columns: 36px auto; row-gap: 6px;` 让三个 input 堆叠到下一行（用 `grid-column: 1 / -1;`）。

---

## 6. 实施顺序

1. **资源拷贝**：把 §2.1 表中的 9 个 PNG 从 `素材/` 复制到 `public/assets/lobby/`，确认文件名与目标完全一致。
2. **数据层**：新建 `src/lib/modelConfigs.ts`（§3.1），新建 `src/hooks/useLocalStorage.ts`（§3.3）。
3. **音频 hook 改造**：修改 `src/hooks/useLobbyAudio.ts`，按 §3.4 增加 `volume` 状态、`setVolume` 方法，初始化时读 `localStorage`，每次更新时写 `localStorage`；`toggleMute` 增加写 `localStorage` 的副作用。
4. **弹窗外壳**：新建 `src/components/Lobby/LobbyModal.tsx`（§4.1）。
5. **三套内容**：新建 `src/components/Lobby/modals/{StartModal,HistoryModal,VolumeSlider,ModelConfigList,SettingsModal}.tsx`。
6. **装配**：修改 `src/components/Lobby/LobbyHome.tsx`（§4.7），加 `activeModal` state、给 `<LobbyButtons>` 接 `onAction`、渲染三个 Modal。
7. **样式**：把 §5 的新增类追加到 `src/styles.css`。
8. **构建校验**：`npm run typecheck && npm run build`，确保零错误。
9. **本地手测**：`npm run dev`，逐条核 §7 验收指标 A–F；浏览器 console 不应有 error / warning。
10. 提交。

---

## 7. 验收指标 A–F（叠加在 STEP-01 / STEP-01b 已 pass 的基础上）

> 全部命中即通过。验收命令均在仓库根目录执行。

### A. 资源 + 命名

- A1. `素材/` 中 1 张设置栏图（`大厅设置栏.png`）+ 8 张模型图标（`minimax老师.png` / `万问.png` / `光之明面.png` / `大米.png` / `学霸.png` / `小豆包儿.png` / `海瑟音.png` / `阿元替身版.png`）**未被改名 / 删除 / 移动**。
- A2. `public/assets/lobby/` 新增 9 张 PNG，文件名与 §2.1 表完全一致；ASCII 小写蛇形。
- A3. `git ls-files public/assets/lobby/` 命中所有 9 张新图（已 tracked）。

### B. 数据层

- B1. `src/lib/modelConfigs.ts` 存在；`MODEL_SLOTS` 是长度为 8 的 `readonly` 常量数组；每条含 `slot / nickname / iconPath` 三字段；`iconPath` 与 A2 命名一致；导出 `EMPTY_USER_INPUT` 与 `VOLUME_DEFAULT/MIN/MAX`。
- B2. `src/hooks/useLocalStorage.ts` 存在；导出受控 hook，SSR-safe（`typeof window === 'undefined'` 返回 initialValue），写入失败仅 `console.warn`，支持 `debounceMs`。
- B3. `src/hooks/useLobbyAudio.ts` 暴露 `volume: number` 与 `setVolume(v: number)`；初始从 `localStorage.wolven_hunt.lobby.volume` 读，缺省 80；setter 内 clamp 到 0–100；`toggleMute` 写 `localStorage.wolven_hunt.lobby.muted`。
- B4. `localStorage` 写入仅限 §3.2 三类 key（grep `localStorage.setItem` 检查）。

### C. 弹窗外壳

- C1. 点击「开始游戏」打开 StartModal；点击「历史复盘」打开 HistoryModal；点击「系统设置」打开 SettingsModal。每次只有一个弹窗 open。
- C2. 三种关闭方式都生效：① 右上角 `<X />` 按钮 ② `Esc` 键 ③ 点击遮罩区。再次打开不残留旧状态。
- C3. 弹窗用 `createPortal` 渲染到 `document.body`，DOM 层级独立于 `LobbyHome`（DevTools 可见）。
- C4. 弹窗背景图为 `/assets/lobby/settings_panel_bg.png`；HTTP 200；首次打开 ≤ 800ms 完成图加载（`<img loading="eager">`）。
- C5. 焦点行为：打开时焦点进入弹窗根（`role="dialog"` 元素），关闭时还原焦点到触发按钮。键盘 Tab 不会逃到下层 lobby 按钮。
- C6. 弹窗根含 `role="dialog"`、`aria-modal="true"`、`aria-labelledby` 指向 `<h2 id="…">{title}</h2>`。

### D. 内容

- D1. StartModal 显示完整两段文案：
  ① `尊敬的玩家您好，该游戏目前处于测试版本，所有 api key 均免费开放，请享受游戏吧～`
  ② `温馨提示：玩家可以选择人机对战或者 AI 内战，具体游戏规则可在局内查看。`
- D2. StartModal 含「进入游戏」按钮；点击后浏览器 console 打印 `[lobby] enter game` 并关闭弹窗。
- D3. HistoryModal 含「功能开发中，敬请期待。」与「未来可让用户以上帝视角逐步还原推理过程。」两段。
- D4. SettingsModal 显示音量分区与 8 条模型条目分区（标题分别为「音量」与「模型配置」）。
- D5. 音量滑块拖动 → BGM 音量实时变化（`<audio>`.volume 同步）；松开后 `localStorage.wolven_hunt.lobby.volume` 同步更新；刷新页面音量保持。
- D6. 8 条模型条目按 `MODEL_SLOTS` 顺序显示：图标（HTTP 200）+ 中文昵称（只读 `<span>`）+ 三个 input；初始 `baseUrl/apiKey/modelName` 三个 input 全为空。
- D7. 在任一 slot 任一字段输入字符 → 300ms 后 `localStorage.wolven_hunt.lobby.model_config.{slot}` 更新；刷新页面值保留；清空字段也能正确同步（key 仍存在，但 JSON value 各字段为空字符串）。
- D8. `apikey` input 为 `type="password"`；其他两个为 `type="text"`；三个 input 都 `autoComplete="off"`。

### E. 边界

- E1. `grep -RInE "fetch\(|axios|XMLHttpRequest|WebSocket|EventSource" src/components src/hooks src/lib` 仍无输出（弹窗内绝不发请求）。
- E2. `grep -RInE "RuleEngine|Referee|FSM|random\(|seed|vote" src/components src/hooks src/lib` 仍无输出，且 `grep -RInE "src/wolven_hunt|configs/" src/components src/hooks src/lib` 仍无输出。合法的 `wolven_hunt.lobby.*` localStorage 命名空间与 ARIA `role` 属性不属于违规。
- E3. `grep -RInE "localStorage\.setItem" src/` 命中的 key 全部以 `wolven_hunt.lobby.` 开头（volume / muted / model_config.{0..7}）。
- E4. 浏览器 console 在「打开三种弹窗 + 拖音量 + 改模型字段 + 关闭弹窗」流程中无 error / warning。

### F. 构建 + 文档

- F1. `npm run typecheck` 零错误。
- F2. `npm run build` 成功。
- F3. `plan.md` §14（含新增 14.10–14.12）与 `architecture.md` §18（含新增 18.9–18.11；架构文档 §18.8 已是 STEP-01 的「阶段交付规格」，故此处偏移一位）保持等价；§14.3 / §18.3 资源清单与 §2.1 表一致。
- F4. 本文件 `docs/specs/STEP-02-lobby-modal-and-settings.md` 与 plan §14 / architecture §18 一致。
- F5. `docs/specs/STEP-01-lobby-home.acceptance.md` 不被修改（保持 STEP-01 的最终记录）。

通过条件：A1–F5 全 pass。任一 fail 整体不通过，按 §6 实施顺序对应步骤返工。

---

## 8. Kiro 验收命令清单

```bash
# A. 资源
ls -la public/assets/lobby/ | grep -E "settings_panel_bg|model_icon_"
ls -la 素材/ | grep -E "大厅设置栏|minimax老师|万问|光之明面|大米|学霸|小豆包儿|海瑟音|阿元替身版"
git ls-files public/assets/lobby/ | grep -E "settings_panel_bg|model_icon_"

# B / D8. 数据层 + 类型契约
test -f src/lib/modelConfigs.ts
test -f src/hooks/useLocalStorage.ts
grep -n "MODEL_SLOTS" src/lib/modelConfigs.ts
grep -n "type=\"password\"" src/components/Lobby/modals/ModelConfigList.tsx

# C. 弹窗外壳
grep -n "createPortal" src/components/Lobby/LobbyModal.tsx
grep -n "role=\"dialog\"\|aria-modal=\"true\"\|aria-labelledby" src/components/Lobby/LobbyModal.tsx

# E. 边界
grep -RInE "fetch\(|axios|XMLHttpRequest|WebSocket|EventSource" src/components src/hooks src/lib || echo "ok: no network"
grep -RInE "RuleEngine|Referee|FSM|random\(|seed|vote" src/components src/hooks src/lib || echo "ok: no engine refs"
grep -RInE "src/wolven_hunt|configs/" src/components src/hooks src/lib || echo "ok: no forbidden imports"
grep -RInE "localStorage\.setItem" src/ || echo "ok: no setItem"

# F. 构建
npm run typecheck
npm run build
# npm run dev → 浏览器手测 C / D / E4
```

---

## 9. 不在本步骤范围

- 模型字段的网络消费（任何 fetch / WebSocket / SSE）→ 等 P2 FastAPI。
- 历史复盘真实逻辑、对局回放渲染 → 等 STEP-04+。
- 「进入游戏」按钮接路由、对局准备页 → 等 STEP-03。
- API key 加密 / 安全存储（localStorage 是明文）→ 用户已确认仅本地测试用，开源 README 时再加风险声明。
- 国际化、深色 / 浅色主题切换。
- 任何 Python 引擎 / FastAPI / LLM 改动。

---

## 10. 验收报告输出

A1–F5 全 pass 后，由 Kiro 写入 `docs/specs/STEP-02-lobby-modal-and-settings.acceptance.md`：
- 全表 pass/fail 记录 + 命令输出片段 / 浏览器截图引用。
- 任何 fail 即整体不通过，回到 §6 实施顺序对应步骤返工。



