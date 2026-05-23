# STEP-05 Python 引擎核心与 FSM 编排 执行规格

> **本规格只覆盖第五步交付：Python 引擎核心、Referee、纯 Python FSM、deterministic mock agent、内存 EventLog、replay_deterministic、5 类测试**。规则契约见 `plan.md` §1–§6 与 `architecture.md` §1–§16；前端壳契约（已交付）见 `plan.md` §14 与 `architecture.md` §18。本文件是 GPT 实施手册 + Kiro 验收指标的镜像。
>
> **硬约束**（与 STEP-01/02/03/04 一致，仍然有效）：
>
> 1. 不得修改 `plan.md` §1–§6、`architecture.md` §1–§16；如有冲突先回到上层修订流程。
> 2. 不得改名 / 移动 / 删除 `素材/` 目录下的任何原始文件。
> 3. **本步骤只动 Python 后端**：不修改 `src/components/`、`src/hooks/`、`src/lib/`、`src/App.tsx`、`src/main.tsx`、`src/styles.css`、`public/`、`package.json`、`vite.config.ts`、`tsconfig*.json`、`scripts/build-lobby-pingpong.mjs`。前端验收用例必须仍然通过。
> 4. 后端代码不得 `import` 任何前端 TS / TSX；前端代码也不得 `import` `src/wolven_hunt/*`（plan.md §14.1 / architecture.md §18.1 已固化）。
> 5. **本步骤不接 LLM**、**不写 FastAPI**、**不写 SSE**、**不持久化磁盘**：内存 EventLog 即可；持久化和 LiteLLM 网关留给 STEP-06。
> 6. 板子规则不得硬编码进 `core/`：所有规则旋钮（`first_night_can_die`、`max_uses_per_game`、`fallback.actions` 等）必须从 `configs/games/_rule_sets/majority_or_massacre_all.yaml` + `configs/games/_role_packs/classic_8_three_gods.yaml` 读取。
> 7. **Referee 是唯一权限边界**：`RuleEngine.apply` 不接 `player_id`、不读 PlayerView、不写 LLM；任何脱敏 / 合法性校验 / 视角分发都走 Referee。

---

## 1. 交付目标

完成后开发者在仓库根目录运行 Python 工具链应能看到：

1. `uv sync --extra dev` 装好全部依赖；`uv run pytest` 跑通 5 类测试套（unit / integration / leakage / golden / property）。
2. `uv run ruff check src tests` 与 `uv run ruff format --check src tests` 通过。
3. `uv run mypy src/wolven_hunt` 在 strict 配置下通过（0 error）。
4. `uv run python -m wolven_hunt.cli simulate --config configs/games/classic_8.yaml --seed wolven-hunt-demo-seed-001` 在 stdout 输出从 `game_start` 到 `game_end` 的脱敏（spectator）事件流，进程退出码为 0，**100% deterministic**——同一 `--seed` 跑两遍 stdout 必须 byte-identical。
5. `uv run python -m wolven_hunt.cli replay --events <path>` 能把上一步导出的事件 JSONL 还原成同样的时间线（`replay_deterministic`），并断言事件 seq、type、payload 与原日志一致。
6. 集成测试在固定 seed 下跑 100 局：每局都收敛到 `game_end`，胜负事件 `payload.winner` 落在 `wolf` 或 `good`，事件日志全程 `seq` 严格递增、`alive_wolves + alive_good == alive_total` 不变量恒成立。
7. 泄漏测试覆盖 `seer_check_result` / `guard_protect` / 狼队夜聊 / 完整 `role_assignment` / `llm_call` 5 个白名单场景，每条都断言越权 seat 的 PlayerView 中**绝不**包含相应 payload。

> 用户态可感知验证：`uv run python -m wolven_hunt.cli simulate ... | head -50` 能看到 `phase_enter` / `guard_protect`（仅守卫视角）/ `wolf_chat_message`（仅狼队视角）/ `speech` / `vote_cast` / `exile` / `win_check` 等典型事件流，且 spectator 视角下私有事件已被过滤。

---

## 2. Python 工程链

### 2.1 `pyproject.toml`（新建）

```toml
[project]
name = "wolven-hunt"
version = "0.1.0"
description = "Wolven Hunt: deterministic 8-player AI werewolf engine."
requires-python = ">=3.11"
authors = [{ name = "Wolven Hunt Team" }]
readme = "README.md"
license = { text = "Proprietary" }
dependencies = [
  "pydantic>=2.6,<3",
  "pyyaml>=6.0,<7",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0,<9",
  "pytest-cov>=5.0,<6",
  "hypothesis>=6.100,<7",
  "ruff>=0.5,<1",
  "mypy>=1.10,<2",
  "types-PyYAML",
]

[project.scripts]
wolven-hunt = "wolven_hunt.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wolven_hunt"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/wolven_hunt"]
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = "yaml"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
  "golden: deterministic golden trace tests",
  "property: hypothesis property tests",
  "leakage: PlayerView leakage tests",
]
```

### 2.2 `uv.lock`

随 `pyproject.toml` 提交（`uv lock`）以保证 CI 可复现。

### 2.3 `.gitignore`

`.gitignore` 已在 STEP-01 加过 `.venv/` / `__pycache__/` / `.pytest_cache/` / `.mypy_cache/` / `.ruff_cache/`，本步骤不动。

### 2.4 `Makefile`（新建，可选但推荐）

```makefile
.PHONY: install lint format typecheck test test-fast cov simulate

install:
	uv sync --extra dev

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

typecheck:
	uv run mypy src/wolven_hunt

test:
	uv run pytest

test-fast:
	uv run pytest -m "not golden and not property"

cov:
	uv run pytest --cov=wolven_hunt --cov-report=term-missing

simulate:
	uv run python -m wolven_hunt.cli simulate --config configs/games/classic_8.yaml --seed wolven-hunt-demo-seed-001
```

---

## 3. 模块结构

最终 `src/wolven_hunt/` 目录如下（保持 §14 / §18 命名空间不动；本步骤只填实业务代码 + `__init__.py`）：

```
src/wolven_hunt/
├── __init__.py
├── cli.py                       # python -m wolven_hunt.cli {simulate, replay}
├── core/
│   ├── __init__.py
│   ├── ids.py                   # GameId / EventId / PromptVersion 包装
│   ├── seat.py                  # Seat (1-based int 包装) + Camp / Role 枚举
│   ├── events.py                # Event 模型 + EventType 枚举（v1.0）
│   ├── state.py                 # GameState（不可变，dataclasses(frozen=True)）
│   ├── actions.py               # Action 类层级（GuardProtect / WolfVote / SeerCheck / Speech / Vote / WitchAction / LastWords ...）
│   ├── rng.py                   # DeterministicRNG（基于 random_seed + rng_stream 派生）
│   ├── win.py                   # WinCondition 纯函数（读 GameState → 'wolf' | 'good' | None）
│   └── rule_engine.py           # apply(state, action) -> (new_state, [Event]); 纯函数
├── referee/
│   ├── __init__.py
│   ├── visibility.py            # filter_for_seat(events, seat) -> events
│   ├── view.py                  # PlayerView dataclass + build_view(state, events, seat)
│   └── validate.py              # validate_action(state, action, rule_set) -> Ok | Reject(reason)
├── orchestration/
│   ├── __init__.py
│   ├── phases.py                # Phase 枚举（GAME_START..GAME_END）
│   └── fsm.py                   # FSM.run(initial_state, agents, rng) -> EventLog
├── agents/
│   ├── __init__.py
│   ├── interface.py             # PlayerInterface（Protocol）+ AgentDecision dataclass
│   ├── deterministic_mock.py    # DeterministicMockAgent（每个角色一份策略）
│   └── human_stub.py            # HumanPlayer stub（NotImplementedError，仅占位以保持 plan §11.P3 入口）
├── storage/
│   ├── __init__.py
│   ├── event_log.py             # EventLog（append-only、in-memory、单调 seq）
│   ├── jsonl.py                 # to_jsonl / from_jsonl，仅 CLI 导出/导入用
│   └── replay.py                # replay_deterministic(events) -> 时间线渲染 + 一致性断言
├── config/
│   ├── __init__.py
│   ├── loader.py                # 读取 configs/games/classic_8.yaml + role_pack + rule_set，合成 GameConfig
│   └── schema.py                # GameConfig / RolePack / RuleSet pydantic models
└── llm/                         # 保留空目录，仅放 README.md 占位（本步骤不实现）
    └── README.md                # "P2 LiteLLM 网关入口；STEP-06 实现"
```

测试目录（已在 STEP-01 创建空骨架）：

```
tests/
├── conftest.py                  # 共享 fixture：load_config / build_initial_state / rng / mock_agents
├── unit/
│   ├── test_events.py
│   ├── test_state.py
│   ├── test_rng.py
│   ├── test_win.py
│   ├── test_rule_engine_seer.py
│   ├── test_rule_engine_guard.py
│   ├── test_rule_engine_wolf.py
│   ├── test_rule_engine_witch.py
│   ├── test_rule_engine_vote.py
│   ├── test_rule_engine_pk.py
│   ├── test_rule_engine_last_words.py
│   ├── test_referee_validate.py
│   └── test_referee_view.py
├── integration/
│   └── test_fsm_full_loop.py    # 跑 100 局 mock，断言收敛 + 事件流不变量
├── leakage/
│   └── test_player_view_leakage.py
├── golden/
│   ├── fixtures/
│   │   └── classic_8_seed_001.events.jsonl   # 黄金事件流（首次跑通后冻结）
│   └── test_classic_8_golden.py
└── property/
    └── test_invariants.py       # hypothesis 不变量
```

---

## 4. 数据模型契约

### 4.1 `core/ids.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID, uuid4

@dataclass(frozen=True, slots=True)
class GameId:
    value: UUID

    @classmethod
    def new(cls) -> "GameId":
        return cls(uuid4())

@dataclass(frozen=True, slots=True)
class EventId:
    value: UUID

    @classmethod
    def new(cls) -> "EventId":
        return cls(uuid4())
```

`GameId` / `EventId` 是 UUID 的不透明包装，禁止直接当 `str` 用。

### 4.2 `core/seat.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class Camp(StrEnum):
    WOLF = "wolf"
    GOOD = "good"

class Role(StrEnum):
    WOLF = "wolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    GUARD = "guard"

ROLE_TO_CAMP: dict[Role, Camp] = {
    Role.WOLF: Camp.WOLF,
    Role.VILLAGER: Camp.GOOD,
    Role.SEER: Camp.GOOD,
    Role.WITCH: Camp.GOOD,
    Role.GUARD: Camp.GOOD,
}

@dataclass(frozen=True, slots=True, order=True)
class Seat:
    """1-based seat number, fixed range [1, 8] for classic_8."""
    number: int

    def __post_init__(self) -> None:
        if not 1 <= self.number <= 8:
            raise ValueError(f"seat number out of [1,8]: {self.number}")
```

### 4.3 `core/events.py`

事件类型枚举严格对齐 `architecture.md` §9：

```python
class EventType(StrEnum):
    # 流程
    GAME_START = "game_start"
    PHASE_ENTER = "phase_enter"
    PHASE_EXIT = "phase_exit"
    GAME_END = "game_end"
    # 夜晚
    GUARD_PROTECT = "guard_protect"
    WOLF_CHAT_MESSAGE = "wolf_chat_message"
    WOLF_KILL_VOTE = "wolf_kill_vote"
    WOLF_KILL_DECIDED = "wolf_kill_decided"
    WOLF_TIE_RANDOM = "wolf_tie_random"
    SEER_CHECK = "seer_check"
    SEER_CHECK_RESULT = "seer_check_result"
    NO_DEATH_TONIGHT = "no_death_tonight"
    DEATH_AT_NIGHT = "death_at_night"
    # 白天
    DAY_ANNOUNCE = "day_announce"
    LAST_WORDS = "last_words"
    SPEECH = "speech"
    WITCH_ACTION = "witch_action"
    VOTE_CAST = "vote_cast"
    VOTE_RESULT = "vote_result"
    VOTE_PK_ENTER = "vote_pk_enter"
    PEACEFUL_DAY = "peaceful_day"
    EXILE = "exile"
    # 系统
    WIN_CHECK = "win_check"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_INVALID_ACTION = "agent_invalid_action"
    AGENT_FALLBACK_TRIGGERED = "agent_fallback_triggered"
    # 元数据（仅写入存储层，不进 PlayerView）
    LLM_CALL = "llm_call"
```

`Event` Pydantic 模型字段对齐 `architecture.md` §9：

```python
class Visibility(BaseModel):
    public: bool
    seats: tuple[int, ...] = ()  # 1-based seat numbers; 顺序无关，但保持元组以便 hash

    @field_validator("seats")
    @classmethod
    def _seats_in_range(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        for s in v:
            if not 1 <= s <= 8:
                raise ValueError(f"seat out of range: {s}")
        return tuple(sorted(set(v)))

class Event(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: EventId
    schema_version: Literal["1.0"] = "1.0"
    game_id: GameId
    seq: int
    phase: str            # FSM 子状态名（见 §5）
    day: int
    timestamp: datetime
    type: EventType
    actor: int | None     # seat number 或 None（系统事件）
    visibility: Visibility
    payload: dict[str, Any] = {}
```

### 4.4 `core/rng.py`

`DeterministicRNG` 必须支持「按 stream 派生独立子流」：

```python
class DeterministicRNG:
    """根据 (random_seed, stream_name) 派生独立 RNG；同一 stream + 同一 seed 必产生同一序列。"""

    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._streams: dict[str, random.Random] = {}

    def stream(self, name: str) -> random.Random:
        if name not in self._streams:
            digest = hashlib.sha256(f"{self._seed}::{name}".encode()).digest()
            self._streams[name] = random.Random(int.from_bytes(digest[:8], "big"))
        return self._streams[name]
```

约定 stream 名：`role_assignment`、`wolf_tie:day{N}`、`fallback:{phase}:seat{N}:retry{R}`、`first_speaker:day{N}`。每个随机事件 payload 必须落 `rng_stream`、`candidates`、`selected`、`reason` 四字段（架构契约 §9）。

### 4.5 `core/state.py`

```python
@dataclass(frozen=True, slots=True)
class PlayerState:
    seat: Seat
    role: Role
    alive: bool
    death_day: int | None
    death_phase: str | None

@dataclass(frozen=True, slots=True)
class GameState:
    game_id: GameId
    config_hash: str
    seed: str
    players: tuple[PlayerState, ...]   # 长度 8，按 seat 排序
    day: int                           # 1-based
    phase: str                         # 当前 FSM 子状态
    last_guard_target: Seat | None     # 守卫连守约束
    witch_antidote_used: bool
    witch_poison_used: bool
    pk_seats: tuple[Seat, ...]         # 当前在 PK 台上的 seats
    pk_round: int                      # 0=未进 PK；1=首轮；2=二次平票
    winner: Camp | None
```

`GameState` 强制不可变；`RuleEngine.apply` 返回新实例。

### 4.6 `core/actions.py`

每种 Agent 动作一个 dataclass：`GuardProtect(actor: Seat, target: Seat)`、`WolfChatMessage(actor: Seat, text: str)`、`WolfKillVote(actor: Seat, target: Seat)`、`SeerCheck(actor: Seat, target: Seat)`、`Speech(actor: Seat, text: str)`、`WitchAction(actor: Seat, action: Literal["save", "poison", "skip"], target: Seat | None)`、`Vote(actor: Seat, target: Seat)`、`PkVote(actor: Seat, target: Seat)`、`LastWords(actor: Seat, text: str)`。`Speech` / `LastWords` / `WolfChatMessage` 强制 `len(text) <= rule_set.speech.max_chars`，超长由 Referee 截断 + 记 `agent_invalid_action`（再触发 fallback）。

---

## 5. FSM 契约

### 5.1 子状态名

枚举严格对齐 `architecture.md` §7：

```
GAME_START
NIGHT_START NIGHT_GUARD NIGHT_WOLF_CHAT NIGHT_WOLF_VOTE NIGHT_WITCH NIGHT_SEER NIGHT_RESOLVE CHECK_WIN_NIGHT
DAY_ANNOUNCE DAY_LAST_WORDS DAY_SPEECH DAY_VOTE DAY_VOTE_PK DAY_EXILE CHECK_WIN_DAY
GAME_END
```

`NIGHT_WITCH` 是固定夜晚子状态，位于 `NIGHT_WOLF_VOTE` 之后、`NIGHT_SEER` 之前；仅女巫存活且至少有一瓶药可用时进入，否则由 FSM 跳过。

### 5.2 调用链

固定为 `architecture.md` §14 的链：

```
FSM.next_phase
  -> Referee.build_view(state, events, seat)
  -> PlayerInterface.decide(view) -> Action
  -> Pydantic 校验
  -> Referee.validate_action(state, action, rule_set) -> Ok | Reject
  -> 若 Reject: 重试上限内重新 build_view（在 prompt 末尾仅追加错误描述）
  -> 仍失败: fallback 表（rule_set.fallback.actions[phase]）→ 同步生成 agent_fallback_triggered
  -> RuleEngine.apply(state, action) -> (new_state, [Event])
  -> EventLog.append_all(events)
  -> 若 phase 在 rule_set.win_conditions.check_after：win_check
```

### 5.3 NIGHT_RESOLVE 顺序

按 `architecture.md` §8 顺序硬编码（不允许走第二种顺序）：

1. 取本晚 `guard_protect` 目标 G、`wolf_kill_decided` 目标 K、`witch_action` 动作 W。
2. 若 W 为 `save` 且解药目标为 K：当 `G == K` 时判定双奶死亡，K 死亡；否则 K 被救下。
3. 若 W 不是有效 `save`：`G == K` 时 K 被守护；`G != K` 时 K 死亡。
4. 若 W 为 `poison`：毒药目标死亡；守卫不挡毒。若毒药目标同时也是 K，只产生一个死亡事件，并按毒药参与死亡处理。
5. 逐个 emit `death_at_night`（公开，不暴露死因）；若无人死亡则 emit `no_death_tonight`。
6. 首夜狼刀死亡与首夜双奶死亡进入 `first_night_deaths`，后续触发遗言；毒药参与死亡永远不进入遗言队列。
7. **不在结算阶段做 seer_check**：`seer_check_result` 已在 `NIGHT_SEER` 结束时由 RuleEngine emit 私有事件。
8. 立即调 `WinCondition.check`，emit `win_check`。

### 5.4 平票 / PK / 平安日

- 首轮 `DAY_VOTE` 平票（最高票多人）→ 进入 `DAY_VOTE_PK`，`pk_seats = 平票 seats`，`pk_round = 1`。
- `DAY_VOTE_PK` 中：PK 台上玩家**不参与重投**；台下玩家只能投 `pk_seats` 内的目标；台下玩家若全部死亡或 fallback 命中 `random_pk_alive_player_by_non_pk_voter_or_peaceful_day` 时无台下玩家可投，则直接 `peaceful_day`。
- 二次平票 → emit `peaceful_day`，**不进入 `DAY_EXILE`**，直接进入 `NIGHT_START`。

### 5.5 女巫夜晚行动

女巫 Agent 只在 `NIGHT_WITCH` 被 FSM 询问一次。女巫视角由 Referee 暴露当晚狼刀目标、解药剩余状态、毒药剩余状态；其他玩家和 spectator 不可见。

1. 输出 `WitchAction(action="save" | "poison" | "skip", target=...)`。
2. Referee 校验：`save` 必须解药未用且目标等于狼刀目标；`poison` 必须毒药未用且目标为存活非自己玩家；`skip` 必须 `target=None`。
3. emit 私有 `witch_action`（仅女巫本人可见），记录动作和目标。
4. `save` 消耗解药，`poison` 消耗毒药，`skip` 不消耗药品。
5. 死亡统一在 `NIGHT_RESOLVE` 按 §5.3 结算。

### 5.6 Fallback

`rule_set.fallback.actions[phase]` 的字符串 token 在 `core/rule_engine.py` 中映射为纯函数；映射表本身允许硬编码在 Python 中（只要触发条件、参数、随机来源完全由 rule_set 决定）。`agent_fallback_triggered` 事件 payload 必须落 `phase`、`seat`、`reason`（`timeout` / `invalid_json` / `validation_failed:<rule>`）、`fallback_action`、`rng_stream`、`candidates`、`selected`。

---

## 6. Referee 契约

### 6.1 PlayerView 形状

```python
@dataclass(frozen=True, slots=True)
class PlayerView:
    seat: Seat               # spectator 视角时为特殊 Seat(0)？不行——见下
    perspective: Literal["player", "spectator"]
    seat_or_none: Seat | None  # spectator: None
    self_role: Role | None     # spectator: None
    teammates: tuple[Seat, ...]  # 仅狼人非空，其它角色与 spectator 均为 ()
    visible_events: tuple[Event, ...]
    rule_set_summary: dict[str, Any]   # 提供给 mock agent 决策用：max_chars / can_vote_self / ...
```

> 不重用 `Seat(0)` 作为 spectator 占位（`Seat` 已强制 1–8）。spectator 视角通过独立的 `perspective="spectator"` + `seat_or_none=None` 表达。

### 6.2 visibility 过滤规则

完全对齐 `architecture.md` §10：

| 事件 | 公开？ | 谁看得到 |
|---|---|---|
| `game_start`（脱敏 payload） | ✓ | 全员 + spectator（按本人/狼队/spectator 三套脱敏） |
| `phase_enter`/`phase_exit`/`day_announce`/`speech`/`vote_cast`/`vote_result`/`vote_pk_enter`/`peaceful_day`/`exile`/`death_at_night`/`no_death_tonight`/`last_words`/`win_check`/`game_end` | ✓ | 全员 + spectator |
| `wolf_chat_message` | ✗ | 狼队 seats + STEP-07 spectator 上帝视角 |
| `wolf_kill_vote`/`wolf_kill_decided`/`wolf_tie_random` | ✗ | 仅 `visibility.seats`（狼队 seats） |
| `guard_protect` | ✗ | 仅守卫本人 |
| `seer_check`/`seer_check_result` | ✗ | 仅预言家本人 |
| `witch_action` | ✗ | 仅女巫本人 |
| `agent_*`/`llm_call` | ✗ | 永不进 PlayerView，仅存储层 |

`game_start.payload.role_assignment` 是私有 metadata：spectator 视角下完全不出现在 PlayerView；玩家视角下 Referee 重写为「本人角色 + （仅狼人）狼队同伴」。

### 6.3 validate_action

`validate_action(state, action, rule_set) -> Ok | Reject(rule_id, message)`，纯函数。覆盖：

- `NIGHT_GUARD`：目标必须是存活玩家；`rule_set.guard.can_guard_self == True` 才允许自守；`rule_set.guard.can_guard_same_target_consecutive_nights == False` 时禁止 `target == state.last_guard_target`。
- `NIGHT_WOLF_VOTE`：目标必须是存活非狼；不允许刀狼队友、不允许自刀、不允许 `target=None`（`can_no_kill=False`）。
- `NIGHT_SEER`：不能查自己（`can_check_self=False`）；可以查死人（`can_check_dead=True`）。
- `DAY_VOTE`：目标必须是存活玩家；允许投自己（`can_vote_self=True`）；不允许投死人。
- `DAY_VOTE_PK`：投票者本人必须**不在** `state.pk_seats`；目标必须**在** `state.pk_seats` 且仍存活。
- `NIGHT_WITCH`：调用者活着且角色是 Witch；`save` 必须解药未用且目标等于当晚狼刀目标；`poison` 必须毒药未用且目标存活、不是自己；`skip` 必须 `target=None`。

`Reject` 不抛异常；FSM 用返回值决定走重试还是 fallback。

---

## 7. Mock Agent

### 7.1 PlayerInterface

```python
class PlayerInterface(Protocol):
    def decide_guard(self, view: PlayerView) -> GuardProtect: ...
    def decide_wolf_chat(self, view: PlayerView) -> WolfChatMessage: ...
    def decide_wolf_vote(self, view: PlayerView) -> WolfKillVote: ...
    def decide_seer(self, view: PlayerView) -> SeerCheck: ...
    def decide_speech(self, view: PlayerView) -> Speech: ...
    def decide_witch(self, view: PlayerView) -> WitchAction: ...
    def decide_vote(self, view: PlayerView) -> Vote: ...
    def decide_pk_vote(self, view: PlayerView) -> PkVote: ...
    def decide_last_words(self, view: PlayerView) -> LastWords: ...
```

### 7.2 DeterministicMockAgent

策略要求：

- 完全 deterministic：策略本体不持有 RNG；任何随机选择走 `view.rng_stream`（PlayerView 可暴露一个 stream-scoped Random，仅供 mock agent 使用，**不能**用于业务逻辑）。
- 守卫：第 1 晚守自己；第 N>1 晚在「合法目标 = 存活 - last_guard_target」中按 seat 升序选第一个；这样保证不会连守。
- 狼人夜聊：发送固定模板「(狼)我是 X 号，今晚刀 Y 号」（X 是自己，Y 是按 seat 升序的第一个存活非狼）。
- 狼人投刀：每个狼独立投「按 seat 升序的第一个存活非狼」——这样会确定性多数决，不会产生 `wolf_tie_random`。
- 预言家：按 seat 升序查第一个未被自己查过（含死人）且不是自己的目标。
- 发言：固定模板「我是 N 号好人」（N=自己 seat）。
- 女巫用药：进入 `NIGHT_WITCH` 时默认 `skip`；测试夹具可以在特定 seed 下让 mock 主动 `save` 或 `poison`（用于 golden）。
- 投票：按 seat 升序投存活第一个非自己玩家；自己若是最后一个存活则投自己（满足「允许投自己」+「不能弃票」）。
- PK 投票：按 seat 升序投 PK 台上第一个存活玩家。
- 遗言：固定模板「我没有遗言」。

> 这套策略保证：100 局都收敛到同一胜方（取决于 seed 决定的角色洗牌结果），事件流跨 run byte-identical。

### 7.3 HumanPlayer stub

`agents/human_stub.py` 内只定义 `class HumanPlayer(PlayerInterface): ...`，所有 `decide_*` 抛 `NotImplementedError("HumanPlayer is reserved for STEP-06+")`。本步骤不导出到 `__init__`。

---

## 8. CLI

### 8.1 `wolven_hunt/cli.py`

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wolven-hunt")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sim = sub.add_parser("simulate", help="run a deterministic simulation")
    p_sim.add_argument("--config", required=True)
    p_sim.add_argument("--seed", required=True)
    p_sim.add_argument("--out", default="-", help="path to write JSONL events; '-' for stdout")
    p_sim.add_argument("--perspective", default="spectator",
                       choices=["spectator", "seat:1", "seat:2", "seat:3", "seat:4",
                                "seat:5", "seat:6", "seat:7", "seat:8"])

    p_replay = sub.add_parser("replay", help="render a deterministic timeline from events")
    p_replay.add_argument("--events", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "simulate":
        return run_simulate(args)
    if args.cmd == "replay":
        return run_replay(args)
    return 2
```

`run_simulate` 输出事件按 spectator 视角脱敏（默认）；如需完整存储层视角，加 `--perspective seat:N` 拿到指定玩家视角；**不允许** `--perspective omniscient`（防止泄漏）。

### 8.2 stdout 格式

JSONL，每行一个事件 `model_dump_json()`。 进程退出码 0 表示正常 `game_end`，1 表示错误，2 表示参数非法。

---

## 9. 配置加载

### 9.1 `config/loader.py`

`load_game_config(path: Path) -> GameConfig`：

1. 解析 `classic_8.yaml`，按相对路径 join 出 `role_pack` / `rule_set` 实际文件，递归读取。
2. 用 pydantic 校验所有字段；任何缺失字段直接抛 `ConfigError`。
3. 计算 `config_hash`：把三份 YAML 序列化为 canonical JSON（key 排序、UTF-8、无空格），然后 `sha256(...).hexdigest()`。
4. 返回 `GameConfig(role_pack, rule_set, prompt_pack_root, model_roster_ref, seed_required=True, config_hash=...)`。

> 本步骤不解析 prompt 模板内容（无 LLM）；只校验目录存在 + 至少一份 `*.v1.md`，确保 STEP-06 接入时不返工。

### 9.2 `roster.yaml`

仅校验文件存在、字段类型、不报错；本步骤的 mock agent 不读 roster（model 信息无意义）。`game_start.payload.config_hash` 需基于 `role_pack + rule_set` 而非 roster 算，避免开发期改 roster 导致 golden 全失效。

---

## 10. 测试契约

### 10.1 `tests/conftest.py`

提供 fixture：

- `rule_set` / `role_pack` / `game_config`：从 `configs/games/classic_8.yaml` 加载。
- `seed = "wolven-hunt-test-seed-001"`（与 production seed 区分）。
- `initial_state`：基于 fixture seed 跑 `RuleEngine.apply(GAME_START, ...)` 后的状态。
- `mock_agents`：`DeterministicMockAgent` × 8。
- `event_log`：内存 EventLog 工厂。

### 10.2 unit 必须覆盖（按 `architecture.md` §16 + `plan.md` §10.1）

| 模块 | 用例（最少） |
|---|---|
| `events` | Event frozen、seq 单调、`Visibility.seats` 自动去重排序、unknown EventType 反序列化失败 |
| `state` | `PlayerState.alive` 转 `False` 后 `death_day` 必须非空 |
| `rng` | 同 seed 同 stream 必同序列；不同 stream 必互不影响；hash 派生稳定 |
| `win` | 三条规则各一组 minimal state（狼严格大于、屠城、狼全灭）；alive_wolves==alive_good 不算狼胜（严格 `>`） |
| `rule_engine_seer` | 查活人 / 查死人 / 重复查同一人 / 不能查自己 / 死亡后再调直接 reject |
| `rule_engine_guard` | 自守 / 第一晚可守 / 连守同一目标被 reject / 守目标==狼刀目标 → no_death_tonight |
| `rule_engine_wolf` | 多数决 / 平票走 wolf_tie_random（候选集 + selected 写入 payload）/ 自刀被 reject / 刀狼队友被 reject / 空刀被 reject |
| `rule_engine_witch` | 解药救狼刀目标 / 毒药击杀且守卫不挡 / 同夜狼刀+毒药双死 / 双奶死亡 / 同目标狼刀+毒药无遗言 / 第二次用同类药被 reject |
| `rule_engine_vote` | 投自己合法 / 投死人 reject / 平票进 PK / 单人最高票直接 exile |
| `rule_engine_pk` | PK 台上玩家不可投 / 台下玩家只能投 PK seats / 二次平票 → peaceful_day |
| `rule_engine_last_words` | 首夜被刀者有遗言 / 首夜双奶死亡有遗言 / 第二夜后夜死无遗言 / 毒药参与死亡无遗言 |
| `referee_validate` | 每个 phase 至少一组 Reject 用例，rule_id 字符串可读 |
| `referee_view` | spectator 视角不含私有事件；狼人视角含狼队事件；预言家视角含 seer_check_result |

### 10.3 integration

`test_fsm_full_loop.py`：

- 100 个不同 seed 各跑一局 mock，断言：
  - 必收敛到 `game_end`，存在 `win_check.payload.winner ∈ {"wolf", "good"}`。
  - 事件 seq 严格 +1 递增、无重复、无空洞。
  - 不变量：每个 phase_exit 后 `alive_wolves + alive_good == alive_total`。
  - `replay_deterministic(events)` 渲染出的事件 seq 与原 events 完全一致。
- 同一 seed 跑两次，事件流 byte-identical（`json.dumps(..., sort_keys=True)` 比较）。

### 10.4 leakage

`test_player_view_leakage.py`：

- 对每局事件流，取 8 个玩家视角 + 1 个 spectator 视角；对每个视角断言：
  - 不在 visibility 白名单内的事件 type **不可**出现。
  - `wolf_chat_message` 仅出现在狼队视角和 STEP-07 spectator 上帝视角。
  - `wolf_kill_vote` / `wolf_kill_decided` / `wolf_tie_random` 仅出现在狼队视角。
  - `seer_check_result` / `seer_check` 仅出现在预言家视角。
  - `guard_protect` 仅出现在守卫视角。
  - 任何视角中 `game_start.payload` 不含完整 `role_assignment`（spectator 完全没有；玩家视角只看到自己 + 狼队同伴）。
  - `agent_fallback_triggered` / `agent_invalid_action` / `agent_timeout` / `llm_call` 在所有 PlayerView 中均不出现。

### 10.5 golden

`tests/golden/test_classic_8_golden.py`：

- 用固定 seed `wolven-hunt-golden-seed-001` 跑一局，序列化所有事件到 `tests/golden/fixtures/classic_8_seed_001.events.jsonl`。
- 测试断言当前生成结果 == fixture 内容（line-by-line diff）。
- fixture 第一次运行通过后冻结；后续修改 RuleEngine / Referee / FSM 必须显式 `pytest tests/golden --update-golden` 才能更新（可用环境变量 `WOLVEN_HUNT_UPDATE_GOLDEN=1`）。
- fixture 体积建议 < 200KB；如超出，golden 仅保留事件 type + actor + payload 关键字段的窄影子文件 `events.shadow.jsonl`，事件原文留 sha256。

### 10.6 property

`test_invariants.py`（`@pytest.mark.property`，hypothesis）：

不变量集合：

1. `seq` 在事件日志中严格递增。
2. `alive_wolves + alive_good == alive_total` 在每个 phase_exit 后恒成立。
3. `len(state.players) == 8` 永远不变。
4. `state.witch_antidote_used` 和 `state.witch_poison_used` 一旦为 True 就不会被重置为 False。
5. `state.last_guard_target` 在第二晚开始时不允许等于第一晚的 target。
6. PlayerView.visible_events 是 EventLog 的子序列（保 seq 单调）。
7. 不存在两个 `game_end`。
8. spectator PlayerView 中所有事件必须是公开事件，或属于明确白名单（当前仅 `wolf_chat_message`）。

策略：用 `hypothesis.strategies.text(...)` 生成 seed，调 `simulate(seed) -> events`，再断言上述不变量。`max_examples=50`、`deadline=1500ms`。

### 10.7 不在测试范围

- LLM 网关 mock（STEP-06）。
- 公平性回归（`plan.md` §10.6，P3，需要真实 LLM）。
- token 预算测试（`plan.md` §10.7，P3）。
- replay_resimulate（无 raw response，跳过到 STEP-06）。

---

## 11. 修改清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `pyproject.toml` | 新建 | uv + ruff + mypy + pytest 配置 |
| `uv.lock` | 新建（uv lock 生成） | 依赖锁 |
| `Makefile` | 新建（可选） | install / lint / format / typecheck / test / cov / simulate |
| `README.md` | 修改 / 新建 | 加 Python 工程链一节：装 uv → `uv sync --extra dev` → `make test` → `make simulate` |
| `src/wolven_hunt/__init__.py` | 修改 | 显式导出 `__version__` |
| `src/wolven_hunt/cli.py` | 新建 | `simulate` / `replay` 子命令 |
| `src/wolven_hunt/core/{ids,seat,events,state,actions,rng,win,rule_engine}.py` | 新建 | 核心数据模型 + 纯函数 RuleEngine |
| `src/wolven_hunt/core/__init__.py` | 新建 | re-export |
| `src/wolven_hunt/referee/{visibility,view,validate}.py` | 新建 | Referee 三件套 |
| `src/wolven_hunt/referee/__init__.py` | 新建 | re-export |
| `src/wolven_hunt/orchestration/{phases,fsm}.py` | 新建 | FSM 编排 |
| `src/wolven_hunt/orchestration/__init__.py` | 新建 | re-export |
| `src/wolven_hunt/agents/{interface,deterministic_mock,human_stub}.py` | 新建 | mock agent + stub |
| `src/wolven_hunt/agents/__init__.py` | 新建 | 仅导出 `DeterministicMockAgent` 与 `PlayerInterface` |
| `src/wolven_hunt/storage/{event_log,jsonl,replay}.py` | 新建 | 内存 EventLog + JSONL + replay_deterministic |
| `src/wolven_hunt/storage/__init__.py` | 新建 | re-export |
| `src/wolven_hunt/config/{loader,schema}.py` | 新建 | YAML 加载 + GameConfig |
| `src/wolven_hunt/config/__init__.py` | 新建 | re-export |
| `src/wolven_hunt/llm/README.md` | 新建 | 占位文档：本目录留给 STEP-06 LiteLLM 网关 |
| `tests/conftest.py` | 新建 | 共享 fixture |
| `tests/unit/test_*.py` | 新建（13 个） | §10.2 表 |
| `tests/integration/test_fsm_full_loop.py` | 新建 | §10.3 |
| `tests/leakage/test_player_view_leakage.py` | 新建 | §10.4 |
| `tests/golden/test_classic_8_golden.py` | 新建 | §10.5 |
| `tests/golden/fixtures/classic_8_seed_001.events.jsonl` | 新建（首次跑通后冻结） | golden 黄金日志 |
| `tests/property/test_invariants.py` | 新建 | §10.6 |
| `docs/specs/STEP-05-engine-core-and-fsm.md` | 新建（本文件） | GPT 实施手册 + 验收指标 |

> **不修改**：`src/components/`、`src/hooks/`、`src/lib/`、`src/App.tsx`、`src/main.tsx`、`src/styles.css`、`public/`、`package.json`、`vite.config.ts`、`tsconfig*.json`、`scripts/`、`configs/`（配置已在 STEP-01 写定，本步骤只读）、`plan.md`、`architecture.md`、`AGENTS.md`、`.gitignore`、`.env.example`。

---

## 12. 实施顺序

1. **工程链**：写 `pyproject.toml`，跑 `uv lock` 生成 lock；`uv sync --extra dev`。
2. **数据模型**：`core/ids.py` → `core/seat.py` → `core/events.py` → `core/rng.py` → `core/state.py` → `core/actions.py`。每写完一个 module 配对 unit 测试当场跑通再继续。
3. **配置加载**：`config/schema.py` + `config/loader.py`，把 fixture seed 下的 `classic_8.yaml` 加载并断言 `config_hash` 稳定。
4. **WinCondition**：`core/win.py` + `tests/unit/test_win.py`。
5. **RuleEngine**：按角色拆 13 个 unit 文件之顺序逐角色实现 `apply` 分支：guard → wolf → seer → night_resolve → day_speech → witch → vote → pk → last_words。每实现一个分支跑对应 unit。
6. **Referee**：`visibility.py` → `view.py` → `validate.py` + 两个 unit。
7. **FSM**：`orchestration/phases.py` + `orchestration/fsm.py`。先跑通一局 mock + spectator 输出。
8. **Mock Agent**：`agents/deterministic_mock.py`。
9. **Storage**：`storage/event_log.py` + `storage/jsonl.py` + `storage/replay.py`。
10. **CLI**：`cli.py`，验证 `make simulate` 跑通，输出可被 `replay` 还原。
11. **集成 / 泄漏 / property 测试**：跑 100 局，修各种边界 bug。
12. **Golden**：跑出 fixture，提交，再跑一遍验证 byte-identical。
13. **质量门禁**：`make lint && make format && make typecheck && make test`，全部 0 error。
14. **README**：补一段 Python 上手说明。

---

## 13. 验收指标

### A. 工程链

| ID | 检查项 | 命令 |
|---|---|---|
| A1 | `pyproject.toml` 存在且包含 `[project]`、`[project.optional-dependencies].dev`、`[tool.ruff]`、`[tool.mypy]`、`[tool.pytest.ini_options]` | `cat pyproject.toml` |
| A2 | `uv sync --extra dev` 成功 | `uv sync --extra dev` |
| A3 | `uv.lock` 已提交 | `ls uv.lock` |
| A4 | `uv run ruff check src tests` 0 error | `uv run ruff check src tests` |
| A5 | `uv run ruff format --check src tests` 0 error | `uv run ruff format --check src tests` |
| A6 | `uv run mypy src/wolven_hunt` strict 0 error | `uv run mypy src/wolven_hunt` |
| A7 | `uv run pytest` 全绿 | `uv run pytest` |

### B. CLI

| ID | 检查项 |
|---|---|
| B1 | `uv run python -m wolven_hunt.cli simulate --config configs/games/classic_8.yaml --seed wolven-hunt-demo-seed-001` 退出码 0 |
| B2 | 同 seed 跑两次 stdout byte-identical（`diff <(...) <(...)` 无输出） |
| B3 | stdout 第一行事件 type 为 `game_start`，最后一行为 `game_end` |
| B4 | stdout 中所有事件 visibility.public 为 True（默认 spectator 视角） |
| B5 | `--out tmp.jsonl` 后 `--perspective seat:N` 跑出的输出包含相应私有事件（如 N==seer 的座位则包含 `seer_check_result`） |
| B6 | `replay --events tmp.jsonl` 退出码 0 且 stdout 中事件 seq、type 与输入一一对应 |

### C. 数据模型

| ID | 检查项 |
|---|---|
| C1 | `Seat(0)` 与 `Seat(9)` 抛 `ValueError` |
| C2 | `Event` 是 frozen，赋值 `evt.seq = 999` 抛 |
| C3 | `Visibility(seats=(2,1,2))` 自动归一为 `(1, 2)` |
| C4 | `EventType.VALUE` 解析未知字符串失败 |
| C5 | `DeterministicRNG("a").stream("x").randint(0,99) == DeterministicRNG("a").stream("x").randint(0,99)` |

### D. RuleEngine 行为

| ID | 检查项 |
|---|---|
| D1 | `apply(state, GuardProtect(target=last_guard_target))` 不直接报错而是返回 Reject（先经 Referee） |
| D2 | 守目标 == 狼刀目标 → 当晚 `no_death_tonight`，无 `death_at_night` |
| D3 | 狼刀平票 → emit `wolf_tie_random`，payload 含 `rng_stream`、`candidates`、`selected`、`reason` |
| D4 | 预言家查死人成功，结果只含 `camp` 不含 `role` |
| D5 | 女巫解药救狼刀目标；女巫毒药击杀目标且不被守卫阻挡；守卫和解药同救狼刀目标时双奶死亡 |
| D6 | 平票后 PK 仍平票 → `peaceful_day`，无 `exile` |
| D7 | 投自己合法；投死人 reject |

### E. Referee 边界

| ID | 检查项 |
|---|---|
| E1 | spectator 视角 PlayerView.visible_events 可以包含 `wolf_chat_message`，但不得包含 `wolf_kill_vote`/`wolf_kill_decided`/`wolf_tie_random`/`seer_check`/`seer_check_result`/`guard_protect`/`witch_action` |
| E2 | 玩家视角 PlayerView 中不出现 `agent_fallback_triggered`/`agent_invalid_action`/`agent_timeout`/`llm_call` |
| E3 | 玩家视角 game_start payload 仅含本人 role + 狼队同伴（仅当本人是狼）；spectator 上帝视角 game_start payload 可含 role_assignment，但不得含 RNG candidates/selected |
| E4 | `validate_action` 对未规则化的 phase 默认 reject 而非通过 |

### F. FSM 集成

| ID | 检查项 |
|---|---|
| F1 | 100 个不同 seed 全部收敛到 `game_end`（pytest 跑） |
| F2 | 每局 `seq` 严格 +1 递增 |
| F3 | 每局存在恰好一个 `game_end` |
| F4 | 每个 phase_exit 后 `alive_wolves + alive_good == alive_total` |
| F5 | `replay_deterministic(events)` 输出 byte-identical |
| F6 | 同一 seed 跑两次 events 列表完全一致（`pickle.dumps` 哈希相同） |

### G. 泄漏

| ID | 检查项 |
|---|---|
| G1 | 全部 5 类泄漏面在所有 100 局中均无命中 |
| G2 | `seer_check_result` 在非预言家视角 0 命中 |
| G3 | 狼队事件在非狼视角 0 命中 |
| G4 | `guard_protect` 在非守卫视角 0 命中 |

### H. Golden

| ID | 检查项 |
|---|---|
| H1 | `tests/golden/fixtures/classic_8_seed_001.events.jsonl` 存在 |
| H2 | `pytest tests/golden` 通过 |
| H3 | 故意改 `core/rule_engine.py` 任何分支 → golden 必然失败（手测） |
| H4 | `WOLVEN_HUNT_UPDATE_GOLDEN=1 pytest tests/golden` 重新生成 fixture，diff 可读 |

### I. Property

| ID | 检查项 |
|---|---|
| I1 | `pytest tests/property` 通过；hypothesis settings `max_examples >= 50`，`deadline >= 1500ms` |
| I2 | 任何不变量违反 → 测试失败并给出 minimal seed |

### J. 边界约束

| ID | 检查项 | 命令 |
|---|---|---|
| J1 | `src/wolven_hunt/` 不出现 `import openai` / `from litellm` / `fastapi` / `httpx` / `requests` | `grep -RInE "^(import\|from) (openai\|litellm\|fastapi\|httpx\|requests)" src/wolven_hunt` |
| J2 | `src/wolven_hunt/` 不出现 `random.SystemRandom`、`time.time()`（非 deterministic 来源）；`datetime.now()` 仅允许通过 `core/rng.py` 暴露的 frozen clock | `grep -RInE "SystemRandom\|time\(\)\|datetime\.now\(\)" src/wolven_hunt` 命中行需在白名单 |
| J3 | `tests/` 不读写真实网络 | 跑 pytest 时 `pytest -p no:cacheprovider --offline` 仍通过（自检） |
| J4 | `core/rule_engine.py` 不出现 `if config.role_pack ==` 等硬编码板子判断 | grep |
| J5 | 前端文件无变更（git diff `src/components` `src/hooks` `src/lib` `src/App.tsx` `src/main.tsx` `src/styles.css` `public/` `package.json` 全为空） | `git diff --stat -- src/components src/hooks src/lib src/App.tsx src/main.tsx src/styles.css public package.json` |
| J6 | `plan.md` / `architecture.md` 未被本步骤改动 | `git diff --stat plan.md architecture.md` 为空 |

### K. 文档

| ID | 检查项 |
|---|---|
| K1 | 本文件存在并覆盖 §1–§13 |
| K2 | `README.md` 包含 Python 上手段：`uv sync --extra dev` / `make test` / `make simulate` |
| K3 | `src/wolven_hunt/llm/README.md` 明示「STEP-06 实现 LiteLLM 网关」占位 |

---

## 14. 不在本步骤范围

- LLM 调用、LiteLLM 网关、prompt 渲染、structured output 解析、token / cost 记录。
- FastAPI、SSE、WebSocket、HTTP 路由。
- 持久化：SQLite、磁盘 events.jsonl 落盘到默认路径（CLI 可显式 `--out` 写文件，但运行时不写）。
- replay_resimulate（依赖 raw LLM response，留 STEP-06）。
- 公平性回归 / token 预算测试（依赖真模型，留 P3）。
- 前端 UI：倒计时、阶段音效、女巫夜晚行动状态、投票直方图、玩家高亮、死亡变灰——这些都属于 STEP-07+。
- 动作字符截断的细化策略（本步骤简单粗暴：超长 → reject → fallback 到模板）。

---

## 15. 风险登记

- **golden 体积**：100 局事件流可能膨胀 fixture。控制：单局 fixture 限定 1 个 seed；其它 seed 走 integration 不写 fixture。如单局 fixture > 200KB，启用 §10.5 的 `events.shadow.jsonl` 影子格式。
- **mock agent 永远不平票**：会让 `wolf_tie_random` 路径在 integration 中可能漏盖。对策：unit `test_rule_engine_wolf` 必须显式 inject 平票 action 序列触发 `wolf_tie_random`。
- **deterministic 假象**：Python `dict` ordering、`frozenset` 顺序、`datetime` 现在时间都可能破 deterministic。落地：所有事件的 `timestamp` 用 `core/clock.py` 提供的 `frozen_clock(seed)` 派生（`game_start.timestamp + seq * 1ms`），不读系统时钟。
- **配置 hash 漂移**：YAML 注释、key 排序、空格变化都会改 hash。落地：`config_hash` 算前先 `yaml.safe_load` → `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` → utf-8 bytes → sha256；这个流程在 unit `test_config_loader` 中冻结一组 expected hash。
- **mypy strict 误报**：pydantic v2 + dataclasses(frozen=True) + slots 偶尔与 mypy 冲突。落地：必要处用 `# type: ignore[<code>]` 标注并注明原因；不允许 `# type: ignore` 裸用。
