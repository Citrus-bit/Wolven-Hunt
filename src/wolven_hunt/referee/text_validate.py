from __future__ import annotations

import re

from wolven_hunt.config.schema import RuleSet
from wolven_hunt.core.actions import Action, LastWords, Speech
from wolven_hunt.core.events import Event, EventType
from wolven_hunt.core.seat import Role, Seat
from wolven_hunt.core.state import GameState
from wolven_hunt.referee.validate import Reject, ValidationResult

_NUMBER_TEXT = "一二三四五六七八九十"
_SEAT_TEXT = rf"(?:[0-9]+|[{_NUMBER_TEXT}]+)号"
_SELF_TEXT = r"(?:自己|本人|我自己)"
_TARGET_TEXT = rf"(?:{_SELF_TEXT}|{_SEAT_TEXT})"
_GUARD_VERB = r"(?:守护|守了|守|保|保护)"
_RULE_NEGATION_MARKERS = (
    "不能",
    "不可",
    "不允许",
    "禁止",
    "规则",
    "别",
    "不要",
    "不该",
)
_UNCERTAINTY_MARKERS = (
    "可能",
    "也许",
    "或许",
    "大概",
    "应该",
    "不确定",
    "不能确定",
    "未确认",
    "不代表",
    "不一定",
    "疑似",
    "如果",
)
_CONSECUTIVE_GUARD_PATTERNS = (
    re.compile(
        rf"(?:连续(?:两|2)晚|连着(?:两|2)晚|两晚都|连守).{{0,14}}{_GUARD_VERB}.{{0,10}}(?:同一|同一个|{_TARGET_TEXT})"
    ),
    re.compile(
        rf"{_GUARD_VERB}.{{0,10}}(?:同一|同一个|{_TARGET_TEXT}).{{0,14}}(?:连续(?:两|2)晚|连着(?:两|2)晚|两晚都|连守)"
    ),
)
_GUARD_SUCCESS_PATTERNS = (
    re.compile(r"(?:守护|守|保护|保).{0,12}成功"),
    re.compile(r"(?:守住|挡住|防住).{0,6}(?:刀|狼刀|袭击)"),
    re.compile(r"(?:挡刀|防守成功|守对刀口)"),
)
_GUARD_NIGHT_TARGET_RE = re.compile(
    rf"(?P<night>首夜|首晚|第?(?:[0-9]+|[{_NUMBER_TEXT}]+)(?:晚|夜)).{{0,12}}"
    rf"{_GUARD_VERB}.{{0,4}}(?P<target>{_TARGET_TEXT})"
)
_PRIVATE_SCHEMA_TERMS = (
    "raw_response",
    "raw response",
    "provider",
    "base_url",
    "api_key",
    "llm_call",
    "wolf_private_context",
    "guard_protect",
    "seer_check_result",
    "wolf_kill_vote",
    "wolf_kill_decided",
    "wolf_tie_random",
    "witch_action",
    "模型供应商",
    "模型名称",
    "模型名",
    "供应商",
)
_WOLF_PRIVATE_PATTERNS = (
    re.compile(r"(?:狼聊|狼人夜聊|狼队夜聊).{0,12}(?:说|讨论|商量|决定|安排)"),
    re.compile(r"(?:狼刀目标|刀口).{0,4}(?:是|为|=).{0,4}" + _SEAT_TEXT),
)


def validate_text_consistency(
    state: GameState,
    action: Action,
    rule_set: RuleSet,
    events: tuple[Event, ...],
) -> ValidationResult:
    del rule_set
    if not isinstance(action, (Speech, LastWords)):
        return None
    text = _compact_text(action.text)
    if not text:
        return None
    actor = state.player(action.actor)

    guard_rejection = _validate_guard_text(state, action.actor, actor.role, text, events)
    if guard_rejection is not None:
        return guard_rejection
    private_rejection = _validate_private_fact_text(state, text)
    if private_rejection is not None:
        return private_rejection
    return None


def _validate_guard_text(
    state: GameState,
    actor: Seat,
    role: Role,
    text: str,
    events: tuple[Event, ...],
) -> ValidationResult:
    for pattern in _CONSECUTIVE_GUARD_PATTERNS:
        for match in pattern.finditer(text):
            if _is_rule_statement(text, match.start(), match.end()):
                continue
            return Reject(
                "text.guard_consecutive_claim",
                "guard cannot claim consecutive protection of the same target",
            )

    if role is not Role.GUARD:
        return None

    history = _guard_targets_by_day(events, actor)
    for match in _GUARD_NIGHT_TARGET_RE.finditer(text):
        day = _parse_night_label(match.group("night"))
        target = _parse_target_label(match.group("target"), actor)
        if day is None or target is None:
            continue
        actual = history.get(day)
        if actual is None:
            if day < state.day:
                return Reject(
                    "text.guard_history_missing",
                    f"guard has no recorded protection for night {day}",
                )
            continue
        if actual != target:
            return Reject(
                "text.guard_history_mismatch",
                f"guard night {day} target was {actual.number}, not {target.number}",
            )

    for pattern in _GUARD_SUCCESS_PATTERNS:
        for match in pattern.finditer(text):
            if _has_uncertainty(text, match.start(), match.end()):
                continue
            return Reject(
                "text.guard_success_claim",
                "guard cannot claim confirmed protection success",
            )
    return None


def _validate_private_fact_text(state: GameState, text: str) -> ValidationResult:
    lowered = text.lower()
    for term in _PRIVATE_SCHEMA_TERMS:
        if term.lower() in lowered:
            return Reject(
                "text.private_fact_claim",
                f"text references private runtime detail: {term}",
            )
    if state.phase not in {"DAY_SPEECH", "DAY_LAST_WORDS"}:
        return None
    for pattern in _WOLF_PRIVATE_PATTERNS:
        for match in pattern.finditer(text):
            if _has_uncertainty(text, match.start(), match.end()):
                continue
            return Reject(
                "text.private_fact_claim",
                "text claims unauthorized wolf private information as fact",
            )
    return None


def _guard_targets_by_day(events: tuple[Event, ...], actor: Seat) -> dict[int, Seat]:
    targets: dict[int, Seat] = {}
    for event in events:
        if event.type is not EventType.GUARD_PROTECT or event.actor != actor.number:
            continue
        target = event.payload.get("target")
        if isinstance(target, bool):
            continue
        if isinstance(target, int):
            targets[event.day] = Seat(target)
        elif isinstance(target, str) and target.isdigit():
            targets[event.day] = Seat(int(target))
    return targets


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _is_rule_statement(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 8) : min(len(text), end + 8)]
    return any(marker in window for marker in _RULE_NEGATION_MARKERS)


def _has_uncertainty(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 10) : min(len(text), end + 10)]
    return any(marker in window for marker in _UNCERTAINTY_MARKERS)


def _parse_night_label(label: str) -> int | None:
    if label in {"首夜", "首晚"}:
        return 1
    value = label.removeprefix("第").removesuffix("晚").removesuffix("夜")
    return _parse_positive_int(value)


def _parse_target_label(label: str, actor: Seat) -> Seat | None:
    if label in {"自己", "本人", "我自己"}:
        return actor
    value = label.removesuffix("号")
    number = _parse_positive_int(value)
    if number is None:
        return None
    return Seat(number)


def _parse_positive_int(value: str) -> int | None:
    if value.isdigit():
        number = int(value)
        return number if number > 0 else None
    if value == "十":
        return 10
    if value.startswith("十"):
        tail = value[1:]
        tail_digit = _chinese_digit(tail)
        return 10 + tail_digit if tail_digit is not None else None
    if value.endswith("十"):
        head = value[:-1]
        digit = _chinese_digit(head)
        return None if digit is None else digit * 10
    if "十" in value:
        head, tail = value.split("十", 1)
        head_digit = 1 if head == "" else _chinese_digit(head)
        tail_digit = 0 if tail == "" else _chinese_digit(tail)
        if head_digit is None or tail_digit is None:
            return None
        return head_digit * 10 + tail_digit
    return _chinese_digit(value)


def _chinese_digit(value: str) -> int | None:
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    return digits.get(value)
