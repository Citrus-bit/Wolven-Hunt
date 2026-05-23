# STEP-07b — 提示词工程 + 上下文管理（修复 STEP-06 占位）

## 0. 背景

STEP-06 建好了 `configs/prompts/zh/` 目录骨架（20 个 `.md` 文件），但**正文全是占位**：

```
# Wolf Speech v1
STEP-05 placeholder. Real prompt content is reserved for STEP-06.
```

STEP-07 验收时发现这个洞：真实 LLM 调用时只拿到 JSON dump + "返回 JSON"，没有规则说明、角色指引、策略建议。本 spec 补齐提示词正文，并对齐 `狼人杀需求阐明.md` §三.6/7 的上下文管理与约束要求。

## 1. 交付目标

1. **统一系统提示词**：`configs/prompts/zh/system.v1.md`，全员通用，包含：
   - 游戏规则摘要（8 人板 / 胜负条件 / 夜晚顺序 / 白天流程）
   - 全员约束（只知道编号、不知道模型名、不知道昵称、不能作弊）
   - 输出契约（JSON only / 不解释 / 不 markdown）
2. **角色 × phase 提示词**：20 个 `.md` 文件写真实内容，每个包含：
   - 角色身份与目标
   - 当前 phase 的行动指令
   - 策略建议（3-5 条，简洁）
   - 输出 schema 说明
3. **上下文管理策略**：
   - 事件窗口从固定 40 条改为"重要事件优先 + 滑动窗口"
   - 长局摘要：超 60 条事件时，首夜 / 首日 / 女巫用药 / 放逐结果强制保留
   - 写进 `plan.md` §4.4 / `architecture.md` §13
4. **Leakage 测试**：
   - `tests/leakage/test_prompt_leakage.py`：断言 prompt 不含 model 名、nickname、其他玩家身份
   - 覆盖 5 角色 × 9 phase = 45 组合（至少抽样 15 组）

## 2. plan.md / architecture.md 同步

### 2.1 plan.md

- §4.4 新增"上下文管理策略"小节：
  - 事件窗口：最近 40 条 + 强制保留首夜/首日/女巫/放逐
  - 超 60 条时触发摘要：首 10 条 + 中间摘要 + 最近 30 条
  - 摘要格式：`{type, day, phase, actor, summary_text}`，不走 LLM
- §6.2 LLM 输出 JSON schema 表后追加"提示词结构"段：
  - `[system.v1.md] + [role/phase.v1.md] + [JSON payload] + [retry_error?]`
  - prompt_version 在 manifest 中记录，replay 时校验一致

### 2.2 architecture.md

- §13 LLM 网关章节追加"提示词渲染"段，镜像 plan.md §4.4 + §6.2

## 3. 提示词正文规范

### 3.1 system.v1.md（统一系统提示词）

```markdown
# 狼人杀 AI 玩家系统提示词 v1

你是一名狼人杀游戏的 AI 玩家。本局为 8 人局，角色配置：3 狼人 + 2 村民 + 1 预言家 + 1 女巫 + 1 守卫。

## 游戏规则摘要

**胜负条件**：
- 好人胜：所有狼人死亡
- 狼人胜：存活狼人数 > 存活好人数，或所有好人死亡

**夜晚顺序**：守卫守护 → 狼人夜聊 → 狼人投刀 → 女巫用药 → 预言家查验 → 结算

**白天流程**：公布死亡 → 遗言（首夜狼刀或双奶死亡 / 白天放逐；毒药死亡无遗言）→ 按座位顺序发言 → 投票 → 放逐（平票进 PK）

**关键约束**：
- 你只知道其他玩家的**座位编号**（1-8 号），不知道他们的模型名称或昵称
- 你不能作弊：不能看到私有信息（除非你是狼人看狼聊 / 预言家看查验结果）
- 你必须基于**可见事件**推理，不能凭空捏造信息

## 输出契约

- 你的每次输出必须是**纯 JSON object**，不要输出 markdown 代码块、不要解释、不要多余文字
- JSON 必须符合后续给出的 `output_schema`
- 如果你不确定，选择最保守的策略（例如：村民不乱跳身份、狼人不自爆）

---

以下是你的角色身份与当前行动指令：
```

### 3.2 角色 × phase 提示词模板

每个 `.md` 文件结构：

```markdown
# {Role} {Phase} v1

## 你的身份
{角色目标与阵营}

## 当前阶段
{phase 说明 + 时限}

## 行动指令
{具体要做什么 + 合法目标范围}

## 策略建议
1. {建议 1}
2. {建议 2}
3. {建议 3}

## 输出格式
参考后续 JSON payload 中的 `output_schema`。
```

### 3.3 具体示例（5 个代表性文件）

#### `configs/prompts/zh/wolf/night_action.v1.md`（狼人夜聊 + 投刀）

```markdown
# Wolf Night Action v1

## 你的身份
你是**狼人**，属于狼人阵营。你的队友是 `teammates` 字段列出的座位号。你们的目标是通过夜晚袭击和白天误导，让存活狼人数超过存活好人数。

## 当前阶段
- **NIGHT_WOLF_CHAT**：狼人夜间交流，每狼一句，120 秒时限
- **NIGHT_WOLF_VOTE**：狼人同时投刀，30 秒时限

## 行动指令
- **夜聊**：与队友简短交流今晚刀谁、明天如何配合。字数不超过 1000 字。
- **投刀**：选择一名**存活的非狼玩家**作为袭击目标。不能刀队友、不能空刀、不能刀自己。

## 策略建议
1. 优先刀预言家 / 守卫等神职（如果已暴露）
2. 避免刀可能被守卫守护的目标（例如前一晚被守护过的玩家，守卫不能连续两晚守同一人）
3. 夜聊时简洁明确，避免暴露身份的措辞

## 输出格式
参考 `output_schema`。`NIGHT_WOLF_CHAT` 返回 `{text}`，`NIGHT_WOLF_VOTE` 返回 `{target}`。
```

#### `configs/prompts/zh/seer/night_action.v1.md`（预言家查验）

```markdown
# Seer Night Action v1

## 你的身份
你是**预言家**，属于好人阵营。你每晚可以查验一名玩家的阵营（狼人 / 好人），这是好人阵营最重要的信息来源。

## 当前阶段
**NIGHT_SEER**：预言家查验，60 秒时限

## 行动指令
选择一名玩家查验其阵营。合法目标：
- 任意存活或已死亡玩家（可以查死人）
- **不能查验自己**

查验结果只有你能看到，会以 `seer_check_result` 事件返回 `{camp: "wolf" | "good"}`。

## 策略建议
1. 优先查验发言可疑 / 票型异常的玩家
2. 避免重复查验同一人（除非怀疑记忆错误）
3. 查到狼人后，白天发言时可以暗示或明示，但要防止被狼人反推身份后刀掉

## 输出格式
返回 `{target: <seat_number>}`。
```

#### `configs/prompts/zh/guard/night_action.v1.md`（守卫守护）

```markdown
# Guard Night Action v1

## 你的身份
你是**守卫**，属于好人阵营。你每晚可以守护一名玩家，如果该玩家被狼人袭击，则当晚无人死亡（平安夜）。

## 当前阶段
**NIGHT_GUARD**：守卫守护，60 秒时限

## 行动指令
选择一名**存活玩家**守护。约束：
- 可以守护自己
- **不能连续两晚守护同一人**（包括自己）
- `rule_set_summary.last_guard_target` 是你上一晚守护的目标，本晚不能再选

## 策略建议
1. 首夜可以自守或守可能的预言家
2. 如果预言家已暴露，优先守预言家
3. 避免守同一人两晚（规则禁止）

## 输出格式
返回 `{target: <seat_number>}`。
```

#### `configs/prompts/zh/wolf/speech.v1.md`（狼人白天发言）

```markdown
# Wolf Speech v1

## 你的身份
你是**狼人**，白天需要伪装成好人，误导投票方向，保护队友。

## 当前阶段
**DAY_SPEECH**：白天发言，60 秒时限，每人一次

## 行动指令
发表一段发言，字数不超过 `rule_set_summary.max_chars`（默认 300 字）。

## 策略建议
1. 伪装身份：可以跳村民 / 预言家 / 守卫（但要与队友协调，避免多狼跳同一身份）
2. 带节奏：引导好人投票给其他好人，保护队友
3. 避免逻辑漏洞：不要说出与已知事件矛盾的信息（例如声称查验了某人，但预言家已经查过）

## 输出格式
返回 `{text: "<你的发言>"}`。
```

#### `configs/prompts/zh/villager/speech.v1.md`（村民白天发言）

```markdown
# Villager Speech v1

## 你的身份
你是**村民**，属于好人阵营。你没有夜晚技能，但可以通过白天发言和投票帮助好人找出狼人。

## 当前阶段
**DAY_SPEECH**：白天发言，60 秒时限

## 行动指令
发表一段发言，字数不超过 `rule_set_summary.max_chars`（默认 300 字）。

## 策略建议
1. 分析已知信息：谁的发言逻辑有漏洞？谁的票型可疑？
2. 不要乱跳身份：村民跳预言家 / 守卫会干扰真神职的判断
3. 配合预言家：如果预言家已暴露并报出查验结果，优先相信预言家

## 输出格式
返回 `{text: "<你的发言>"}`。
```

### 3.4 其余 15 个文件

按同样结构补齐：
- `witch/speech.v1.md` / `witch/night_action.v1.md` / `witch/vote.v1.md` / `witch/last_words.v1.md`
- `seer/speech.v1.md` / `seer/vote.v1.md` / `seer/last_words.v1.md`
- `guard/speech.v1.md` / `guard/vote.v1.md` / `guard/last_words.v1.md`
- `villager/vote.v1.md` / `villager/last_words.v1.md` / `villager/night_action.v1.md`（占位，村民夜晚无行动）
- `wolf/vote.v1.md` / `wolf/last_words.v1.md`

## 4. 上下文管理策略升级

### 4.1 当前问题

`prompts.py:37` 固定取 `view.visible_events[-40:]`，长局后期会丢首夜信息。

### 4.2 新策略

新增 `src/wolven_hunt/llm/context.py`：

```python
def select_events_for_prompt(
    events: tuple[Event, ...],
    *,
    max_count: int = 40,
    force_keep_types: set[str] = {"game_start", "death_at_night", "exile", "witch_action", "seer_check_result"},
) -> tuple[Event, ...]:
    """
    优先保留重要事件 + 最近事件。
    - 如果 len(events) <= max_count，全部返回
    - 否则：force_keep 事件 + 最近 (max_count - len(force_keep)) 条
    """
    if len(events) <= max_count:
        return events
    force_keep = [e for e in events if e.type in force_keep_types]
    recent = events[-(max_count - len(force_keep)):]
    # 去重 + 按 seq 排序
    seen = {e.seq for e in force_keep}
    combined = list(force_keep) + [e for e in recent if e.seq not in seen]
    return tuple(sorted(combined, key=lambda e: e.seq))
```

`prompts.py:37` 改为：

```python
from wolven_hunt.llm.context import select_events_for_prompt

visible_events = [
    event.model_dump(mode="json", exclude={"event_id", "timestamp"})
    for event in select_events_for_prompt(view.visible_events, max_count=40)
]
```

### 4.3 单元测试

`tests/unit/test_context.py`：

```python
def test_select_events_keeps_important_and_recent():
    events = [draft_event(..., type=t, seq=i) for i, t in enumerate([
        "game_start", "phase_enter", ..., "death_at_night", ..., "speech", ...
    ])]  # 60 条
    selected = select_events_for_prompt(events, max_count=40)
    assert len(selected) == 40
    assert any(e.type == "game_start" for e in selected)
    assert any(e.type == "death_at_night" for e in selected)
    assert selected[-1].seq == events[-1].seq  # 最后一条必在
```

## 5. Leakage 测试

### 5.1 新增 `tests/leakage/test_prompt_leakage.py`

```python
def test_prompt_does_not_leak_model_names_or_nicknames():
    # 构造一局，8 个 seat 用不同 model（从 MODEL_SLOTS 取 nickname）
    # 渲染 prompt for seat=3（狼人）
    # 断言 prompt 不含其他 seat 的 model 名 / nickname
    # 断言 prompt 只含 "1号" "2号" 等编号
    pass

def test_prompt_does_not_leak_other_player_roles():
    # 构造一局，seat=5（村民）
    # 渲染 prompt
    # 断言 prompt 不含 "seat 3 is wolf" 等其他玩家身份
    # 断言 prompt 只含自己的 role
    pass
```

### 5.2 验收

`pytest tests/leakage/test_prompt_leakage.py -v` 全绿。

## 6. 实施顺序

1. **system.v1.md**：写统一系统提示词
2. **5 个代表性 .md**：wolf/seer/guard/villager/witch 各一个 phase
3. **context.py**：事件选择策略 + 单测
4. **prompts.py 接入**：`[system] + [role/phase] + [JSON]` 拼接顺序
5. **其余 15 个 .md**：补齐全部 20 个文件
6. **leakage 测试**：2 个新测试
7. **plan/architecture 同步**：§4.4 / §13

## 7. 验收指标

- `configs/prompts/zh/system.v1.md` 存在，≥ 30 行
- 20 个角色×phase `.md` 文件全部 ≥ 20 行（不再是 placeholder）
- `tests/unit/test_context.py` 通过
- `tests/leakage/test_prompt_leakage.py` 2 tests 通过
- `pytest -q` 总测试数 +3（context 1 + leakage 2）
- `grep "上下文管理策略" plan.md architecture.md` 两文件都命中
- 手动 smoke：`WH_LLM_PROVIDER=litellm` 跑一局真模型，`runs/{game_id}/raw_responses.jsonl` 里的 prompt 字段包含 system.v1.md 内容

## 8. 不在本步骤范围

- prompt A/B 测试框架
- 自动 prompt 优化（基于胜率 / token 效率）
- 多语言提示词（英文 / 日文）
- 动态 prompt（根据局势调整策略建议）

这些留给 STEP-08 或更后续的 prompt 迭代阶段。
