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
_FUTURE_SPEAKER_NEGATIVE_PATTERNS = (
    re.compile(r"(?:不|没|未).{0,4}(?:报|说|给).{0,8}(?:查验|验人|验|金水|查杀)"),
    re.compile(r"(?:查验|验人|金水|查杀).{0,8}(?:不报|没报|未报|没给|不给|没说|未说)"),
    re.compile(r"(?:不|没|未).{0,4}(?:回应|回复|解释|发言|说话|表态|开口)"),
    re.compile(r"(?:沉默|划水|不活跃|发言少|藏身份|装死|闭麦)"),
)
_NIGHT_RESULT_CLAIM_PATTERNS = (
    re.compile(r"(?:昨晚|昨夜|昨天夜里|今晚|今夜).{0,8}(?:平安夜|无人死亡|没人死|没死人)"),
    re.compile(r"(?:昨晚|昨夜|昨天夜里|今晚|今夜).{0,8}(?:死|倒).{0,8}(?:[0-9一二三四五六七八九十]+|两|二)个"),
    re.compile(r"(?:平安夜|无人死亡|没人死|没死人).{0,8}(?:坐实|确定|必然|已经)"),
)
_WITCH_CERTAINTY_PATTERNS = (
    re.compile(r"女巫.{0,8}(?:还有|有|没了|没有|无).{0,4}毒"),
    re.compile(r"女巫.{0,8}(?:已经|肯定|必然|一定|确定).{0,8}(?:用|用了|开|开了).{0,4}毒"),
    re.compile(r"毒药.{0,8}(?:已经|肯定|必然|一定|确定).{0,8}(?:用|用了|没了|还在|还留着|还没用)"),
    re.compile(r"(?:还有毒|没毒了|毒还在|毒没了|开毒|用了毒|用毒了)"),
)
_DOUBLE_DEATH_POISON_PATTERNS = (
    re.compile(r"(?:双死|死了两|死两|两个.{0,4}倒).{0,16}(?:必然|一定|肯定|确定|坐实).{0,8}(?:毒|女巫)"),
    re.compile(r"(?:必然|一定|肯定|确定|坐实).{0,8}(?:毒|女巫).{0,16}(?:双死|死了两|死两|两个.{0,4}倒)"),
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
    witch_rejection = _validate_witch_fact_text(state, actor.role, text)
    if witch_rejection is not None:
        return witch_rejection
    night_result_rejection = _validate_night_result_text(state, text, events)
    if night_result_rejection is not None:
        return night_result_rejection
    future_speaker_rejection = _validate_future_speaker_text(state, action, text, events)
    if future_speaker_rejection is not None:
        return future_speaker_rejection
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


def _validate_night_result_text(
    state: GameState,
    text: str,
    events: tuple[Event, ...],
) -> ValidationResult:
    for pattern in _NIGHT_RESULT_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            if _has_claim_uncertainty(text, match.start(), match.end()):
                continue
            if _has_public_night_announcement(state, events):
                continue
            return Reject(
                "text.night_result_unannounced",
                "night result cannot be claimed before public announcement",
            )
    return None


def _validate_witch_fact_text(
    state: GameState,
    actor_role: Role,
    text: str,
) -> ValidationResult:
    if state.phase not in {"DAY_SPEECH", "DAY_LAST_WORDS"}:
        return None
    for pattern in _DOUBLE_DEATH_POISON_PATTERNS:
        for match in pattern.finditer(text):
            if _has_uncertainty(text, match.start(), match.end()):
                continue
            return Reject(
                "text.witch_poison_inferred_from_deaths",
                "double death alone does not publicly prove witch poison status",
            )
    for pattern in _WITCH_CERTAINTY_PATTERNS:
        for match in pattern.finditer(text):
            if _has_uncertainty(text, match.start(), match.end()):
                continue
            if actor_role is Role.WITCH:
                continue
            return Reject(
                "text.witch_private_fact_claim",
                "non-witch cannot claim witch poison status as confirmed fact",
            )
    return None


def _validate_future_speaker_text(
    state: GameState,
    action: Action,
    text: str,
    events: tuple[Event, ...],
) -> ValidationResult:
    if state.phase != "DAY_SPEECH" or not isinstance(action, Speech):
        return None
    already_spoken = {
        event.actor
        for event in events
        if event.type is EventType.SPEECH
        and event.phase == "DAY_SPEECH"
        and event.day == state.day
        and event.actor is not None
    }
    current_seat = action.actor.number
    future_speakers = {
        player.seat.number
        for player in state.alive_players()
        if player.seat.number != current_seat and player.seat.number not in already_spoken
    }
    for seat_number in future_speakers:
        for match in _seat_mentions(text, seat_number):
            window = text[match.start() : min(len(text), match.end() + 18)]
            if any(pattern.search(window) for pattern in _FUTURE_SPEAKER_NEGATIVE_PATTERNS):
                return Reject(
                    "text.future_speaker_claim",
                    f"seat {seat_number} has not spoken in current day speech order",
                )
    return None


def _has_public_night_announcement(state: GameState, events: tuple[Event, ...]) -> bool:
    return any(
        event.visibility.public
        and event.day == state.day
        and event.type
        in {
            EventType.DAY_ANNOUNCE,
            EventType.NO_DEATH_TONIGHT,
            EventType.DEATH_AT_NIGHT,
        }
        for event in events
    )


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


def _has_claim_uncertainty(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 6) : end]
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


def _seat_mentions(text: str, seat_number: int) -> tuple[re.Match[str], ...]:
    labels = {f"{seat_number}号"}
    chinese = _int_to_chinese(seat_number)
    if chinese is not None:
        labels.add(f"{chinese}号")
    pattern = re.compile("|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True)))
    return tuple(pattern.finditer(text))


def _int_to_chinese(value: int) -> str | None:
    if value <= 0 or value > 99:
        return None
    digits = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
    }
    if value <= 9:
        return digits[value]
    if value == 10:
        return "十"
    if value < 20:
        return f"十{digits[value - 10]}"
    tens, ones = divmod(value, 10)
    suffix = "" if ones == 0 else digits[ones]
    return f"{digits[tens]}十{suffix}"
