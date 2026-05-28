from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from wolven_hunt.core.seat import ROLE_TO_CAMP, Role


class SeatSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    phase: str
    text: str
    char_count: int


class SeatVoteCast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    target: int | None
    abstained: bool


class SeatVoteReceived(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    voter_seat: int


class SeatLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alive_at_end: bool
    exiled_day: int | None
    night_death_day: int | None
    last_words: str | None


class GlobalRanking(BaseModel):
    """Per-seat global comparison signals for personalized review prompts."""

    model_config = ConfigDict(extra="forbid")

    speech_char_rank: int
    speech_char_total: int
    speech_char_pct: float
    received_votes_rank: int
    received_votes_total: int
    role_peers: tuple[int, ...]
    is_first_to_die: bool
    is_first_to_be_exiled: bool


class SeerCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    target: int
    result: str
    target_actual_role: str | None


class WitchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    action: str
    target: int | None
    correct: bool | None


class GuardProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    day: int
    target: int
    blocked_kill: bool


class KeyDecisionInvolvement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int
    phase: str
    title: str
    role_in_decision: Literal["actor", "target", "voter", "bystander"]


class PerSeatDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: int
    nickname: str
    role: str
    camp: str
    role_duty_label: str
    winner: str
    is_winner: bool
    lifecycle: SeatLifecycle
    speeches: tuple[SeatSpeech, ...]
    votes_cast: tuple[SeatVoteCast, ...]
    votes_received: tuple[SeatVoteReceived, ...]
    wolf_chat_messages: tuple[SeatSpeech, ...]
    seer_checks: tuple[SeerCheck, ...]
    witch_actions: tuple[WitchAction, ...]
    guard_protections: tuple[GuardProtection, ...]
    ranking: GlobalRanking
    key_decision_involvement: tuple[KeyDecisionInvolvement, ...]


ROLE_DUTY_LABELS = {
    Role.WOLF.value: "狼队协同",
    Role.VILLAGER.value: "平民职责",
    Role.SEER.value: "查验价值",
    Role.WITCH.value: "药水决策",
    Role.GUARD.value: "守护判断",
}


def build_dossiers(
    *,
    events: tuple[dict[str, Any], ...],
    narrative_rows: tuple[dict[str, Any], ...],
    reveal: dict[str, Any],
    seat_presentation: dict[int, dict[str, str]],
    key_decisions: tuple[dict[str, Any], ...],
) -> tuple[PerSeatDossier, ...]:
    del narrative_rows
    seats_meta = {
        seat: seat_meta
        for seat_meta in reveal.get("seats", ())
        if isinstance(seat_meta, dict)
        for seat in (_int_or_none(seat_meta.get("seat")),)
        if seat is not None
    }
    winner = str(reveal.get("winner") or "unknown")
    raw: dict[int, dict[str, Any]] = {
        seat: {
            "speeches": [],
            "votes_cast": [],
            "votes_received": [],
            "wolf_chat": [],
            "seer_checks": [],
            "witch_actions": [],
            "guard_protections": [],
            "exiled_day": None,
            "night_death_day": None,
            "last_words": None,
        }
        for seat in seats_meta
    }

    for event in events:
        actor = _int_or_none(event.get("actor"))
        payload = _payload(event)
        event_type = str(event.get("type") or "")
        day = _int_or_none(event.get("day")) or 0
        seq = _int_or_none(event.get("seq")) or 0
        phase = str(event.get("phase") or "")
        if event_type == "speech" and actor in raw:
            text = _strip_actor_prefix(str(payload.get("text") or ""), actor)
            raw[actor]["speeches"].append(
                SeatSpeech(seq=seq, day=day, phase=phase, text=text, char_count=len(text))
            )
        elif event_type == "wolf_chat_message" and actor in raw:
            text = _strip_actor_prefix(str(payload.get("text") or ""), actor)
            raw[actor]["wolf_chat"].append(
                SeatSpeech(seq=seq, day=day, phase=phase, text=text, char_count=len(text))
            )
        elif event_type == "vote_cast" and actor in raw:
            target = _int_or_none(payload.get("target"))
            abstained = bool(payload.get("abstain")) or target is None
            raw[actor]["votes_cast"].append(
                SeatVoteCast(seq=seq, day=day, target=target, abstained=abstained)
            )
            if target in raw and not abstained:
                raw[target]["votes_received"].append(
                    SeatVoteReceived(seq=seq, day=day, voter_seat=actor)
                )
        elif event_type == "exile":
            seat = _int_or_none(payload.get("seat"))
            if seat in raw:
                raw[seat]["exiled_day"] = day
        elif event_type == "death_at_night":
            seat = _int_or_none(payload.get("seat"))
            if seat in raw:
                raw[seat]["night_death_day"] = day
        elif event_type == "last_words" and actor in raw:
            raw[actor]["last_words"] = str(payload.get("text") or "")
        elif event_type == "seer_check_result" and actor in raw:
            target = _int_or_none(payload.get("target"))
            if target is not None:
                raw[actor]["seer_checks"].append(
                    SeerCheck(
                        seq=seq,
                        day=day,
                        target=target,
                        result=str(payload.get("result") or ""),
                        target_actual_role=None,
                    )
                )
        elif event_type == "witch_action" and actor in raw:
            raw[actor]["witch_actions"].append(
                WitchAction(
                    seq=seq,
                    day=day,
                    action=str(payload.get("action") or "skip"),
                    target=_int_or_none(payload.get("target")),
                    correct=None,
                )
            )
        elif event_type == "guard_protect" and actor in raw:
            target = _int_or_none(payload.get("target"))
            if target is not None:
                raw[actor]["guard_protections"].append(
                    GuardProtection(seq=seq, day=day, target=target, blocked_kill=False)
                )

    char_totals = {
        seat: sum(speech.char_count for speech in rows["speeches"]) for seat, rows in raw.items()
    }
    received_totals = {seat: len(rows["votes_received"]) for seat, rows in raw.items()}
    char_rank = _rank_desc(char_totals)
    received_rank = _rank_desc(received_totals)
    first_exiled_seat = _first_seat_by_day(
        (seat, rows["exiled_day"]) for seat, rows in raw.items()
    )
    first_night_dead_seat = _first_seat_by_day(
        (seat, rows["night_death_day"]) for seat, rows in raw.items()
    )
    first_to_die = _first_lifecycle_seat(
        first_exiled=(first_exiled_seat, raw[first_exiled_seat]["exiled_day"])
        if first_exiled_seat is not None
        else None,
        first_night_dead=(first_night_dead_seat, raw[first_night_dead_seat]["night_death_day"])
        if first_night_dead_seat is not None
        else None,
    )

    role_by_seat = {
        seat: _valid_role(str(meta.get("role") or Role.VILLAGER.value)) for seat, meta in seats_meta.items()
    }
    wolf_kill_targets_by_day: dict[int, set[int]] = {}
    for event in events:
        if str(event.get("type") or "") not in {"wolf_kill_decided", "wolf_kill_decision"}:
            continue
        day = _int_or_none(event.get("day")) or 0
        target = _int_or_none(_payload(event).get("target"))
        if target is not None:
            wolf_kill_targets_by_day.setdefault(day, set()).add(target)

    for rows in raw.values():
        for index, guard_protection in enumerate(rows["guard_protections"]):
            blocked = guard_protection.target in wolf_kill_targets_by_day.get(
                guard_protection.day, set()
            )
            rows["guard_protections"][index] = guard_protection.model_copy(
                update={"blocked_kill": blocked}
            )
        for index, witch_action in enumerate(rows["witch_actions"]):
            correct = _witch_action_correctness(witch_action, role_by_seat)
            rows["witch_actions"][index] = witch_action.model_copy(update={"correct": correct})
        for index, seer_check in enumerate(rows["seer_checks"]):
            rows["seer_checks"][index] = seer_check.model_copy(
                update={"target_actual_role": role_by_seat.get(seer_check.target)}
            )

    total_chars = sum(char_totals.values()) or 1
    dossiers: list[PerSeatDossier] = []
    for seat, meta in sorted(seats_meta.items()):
        role = role_by_seat[seat]
        camp = _camp_for_role(role)
        rows = raw[seat]
        role_peers = tuple(
            peer
            for peer, peer_role in sorted(role_by_seat.items())
            if peer != seat and peer_role == role
        )
        nickname = (seat_presentation.get(seat) or {}).get("nickname") or f"{seat}号"
        dossiers.append(
            PerSeatDossier(
                seat=seat,
                nickname=nickname,
                role=role,
                camp=camp,
                role_duty_label=ROLE_DUTY_LABELS.get(role, "角色职责"),
                winner=winner,
                is_winner=camp == winner,
                lifecycle=SeatLifecycle(
                    alive_at_end=bool(meta.get("alive")),
                    exiled_day=rows["exiled_day"],
                    night_death_day=rows["night_death_day"],
                    last_words=rows["last_words"],
                ),
                speeches=tuple(rows["speeches"]),
                votes_cast=tuple(rows["votes_cast"]),
                votes_received=tuple(rows["votes_received"]),
                wolf_chat_messages=tuple(rows["wolf_chat"]),
                seer_checks=tuple(rows["seer_checks"]),
                witch_actions=tuple(rows["witch_actions"]),
                guard_protections=tuple(rows["guard_protections"]),
                ranking=GlobalRanking(
                    speech_char_rank=char_rank[seat],
                    speech_char_total=char_totals[seat],
                    speech_char_pct=char_totals[seat] / total_chars,
                    received_votes_rank=received_rank[seat],
                    received_votes_total=received_totals[seat],
                    role_peers=role_peers,
                    is_first_to_die=first_to_die == seat,
                    is_first_to_be_exiled=first_exiled_seat == seat,
                ),
                key_decision_involvement=_filter_decisions_for_seat(key_decisions, seat),
            )
        )
    return tuple(dossiers)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _strip_actor_prefix(text: str, actor: int) -> str:
    normalized = " ".join(text.split())
    for prefix in (f"{actor}号\uff1a", f"{actor}号:", f"{actor}:"):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _rank_desc(values: dict[int, int]) -> dict[int, int]:
    return {
        seat: index + 1
        for index, (seat, _value) in enumerate(
            sorted(values.items(), key=lambda item: (-item[1], item[0]))
        )
    }


def _first_seat_by_day(values: Iterable[tuple[int, Any]]) -> int | None:
    normalized: list[tuple[int, int]] = [
        (seat, day)
        for seat, day in values
        if isinstance(seat, int) and isinstance(day, int) and day > 0
    ]
    if not normalized:
        return None
    return min(normalized, key=lambda item: (item[1], item[0]))[0]


def _first_lifecycle_seat(
    *,
    first_exiled: tuple[int, int | None] | None,
    first_night_dead: tuple[int, int | None] | None,
) -> int | None:
    candidates: list[tuple[int, int, int]] = []
    if first_night_dead is not None and first_night_dead[1] is not None:
        candidates.append((first_night_dead[1], 0, first_night_dead[0]))
    if first_exiled is not None and first_exiled[1] is not None:
        candidates.append((first_exiled[1], 1, first_exiled[0]))
    if not candidates:
        return None
    return min(candidates)[2]


def _valid_role(value: str) -> str:
    try:
        return Role(value).value
    except ValueError:
        return Role.VILLAGER.value


def _camp_for_role(role: str) -> str:
    try:
        return ROLE_TO_CAMP[Role(role)].value
    except ValueError:
        return "unknown"


def _witch_action_correctness(
    action: WitchAction, role_by_seat: dict[int, str]
) -> bool | None:
    if action.action == "skip" or action.target is None:
        return None
    target_role = role_by_seat.get(action.target)
    if target_role is None:
        return None
    target_camp = _camp_for_role(target_role)
    if action.action == "save":
        return target_camp == "good"
    if action.action == "poison":
        return target_camp == "wolf"
    return None


def _filter_decisions_for_seat(
    decisions: tuple[dict[str, Any], ...], seat: int
) -> tuple[KeyDecisionInvolvement, ...]:
    matched: list[KeyDecisionInvolvement] = []
    for decision in decisions:
        role_in_decision: Literal["actor", "target", "voter", "bystander"] | None = (
            _role_in_decision(decision.get("actors_involved"), seat)
        )
        if role_in_decision is None:
            title = str(decision.get("title") or "")
            analysis = str(decision.get("analysis") or "")
            if f"{seat}号" in title or f"{seat}号" in analysis:
                role_in_decision = "bystander"
        if role_in_decision is None:
            continue
        matched.append(
            KeyDecisionInvolvement(
                day=_int_or_none(decision.get("day")) or 0,
                phase=str(decision.get("phase") or ""),
                title=str(decision.get("title") or ""),
                role_in_decision=role_in_decision,
            )
        )
    return tuple(matched)


def _role_in_decision(
    actors_involved: object, seat: int
) -> Literal["actor", "target", "voter"] | None:
    if not isinstance(actors_involved, dict):
        return None
    for key in ("actor", "target", "voter"):
        seats = actors_involved.get(key)
        if isinstance(seats, list | tuple | set) and seat in {
            value for item in seats if (value := _int_or_none(item)) is not None
        }:
            if key == "actor":
                return "actor"
            if key == "target":
                return "target"
            return "voter"
    return None
