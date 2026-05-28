from __future__ import annotations

from wolven_hunt.storage import review_dossier as rd


def _events() -> tuple[dict[str, object], ...]:
    return (
        {
            "seq": 1,
            "day": 1,
            "phase": "DAY_SPEECH",
            "type": "speech",
            "actor": 2,
            "payload": {"text": "我怀疑5号"},
        },
        {
            "seq": 2,
            "day": 1,
            "phase": "DAY_SPEECH",
            "type": "speech",
            "actor": 5,
            "payload": {"text": "我是村民"},
        },
    )


def _reveal() -> dict[str, object]:
    return {
        "winner": "good",
        "seats": [
            {"seat": 2, "role": "villager", "alive": True},
            {"seat": 5, "role": "wolf", "alive": False},
        ],
    }


def test_build_dossiers_extracts_only_own_speeches() -> None:
    dossiers = rd.build_dossiers(
        events=_events(),
        narrative_rows=(),
        reveal=_reveal(),
        seat_presentation={
            2: {"nickname": "A", "icon_path": ""},
            5: {"nickname": "B", "icon_path": ""},
        },
        key_decisions=(),
    )

    assert len(dossiers) == 2
    seat2 = next(dossier for dossier in dossiers if dossier.seat == 2)
    seat5 = next(dossier for dossier in dossiers if dossier.seat == 5)
    assert [speech.text for speech in seat2.speeches] == ["我怀疑5号"]
    assert [speech.text for speech in seat5.speeches] == ["我是村民"]
    assert seat2.role == "villager" and seat5.role == "wolf"
    assert seat2.role_duty_label == "平民职责"
    assert seat5.role_duty_label == "狼队协同"


def test_dossier_ranking_reflects_speech_chars_and_received_votes() -> None:
    events = (
        {
            "seq": 1,
            "day": 1,
            "phase": "DAY_SPEECH",
            "type": "speech",
            "actor": 1,
            "payload": {"text": "短"},
        },
        {
            "seq": 2,
            "day": 1,
            "phase": "DAY_SPEECH",
            "type": "speech",
            "actor": 2,
            "payload": {"text": "我说很多很多很多很多很多很多话"},
        },
        {
            "seq": 3,
            "day": 1,
            "phase": "DAY_VOTE",
            "type": "vote_cast",
            "actor": 1,
            "payload": {"target": 2},
        },
        {
            "seq": 4,
            "day": 1,
            "phase": "DAY_VOTE",
            "type": "vote_cast",
            "actor": 2,
            "payload": {"target": 1},
        },
        {
            "seq": 5,
            "day": 1,
            "phase": "NIGHT_WOLF_CHAT",
            "type": "wolf_chat_message",
            "actor": 2,
            "payload": {"text": "刀1号"},
        },
    )
    reveal = {
        "winner": "wolf",
        "seats": [
            {"seat": 1, "role": "villager", "alive": False},
            {"seat": 2, "role": "wolf", "alive": True},
        ],
    }

    dossiers = rd.build_dossiers(
        events=events,
        narrative_rows=(),
        reveal=reveal,
        seat_presentation={},
        key_decisions=(),
    )

    seat1 = next(dossier for dossier in dossiers if dossier.seat == 1)
    seat2 = next(dossier for dossier in dossiers if dossier.seat == 2)
    assert seat2.ranking.speech_char_rank == 1
    assert seat1.ranking.speech_char_rank == 2
    assert seat1.ranking.received_votes_rank == 1
    assert seat2.is_winner is True and seat1.is_winner is False
    assert len(seat2.wolf_chat_messages) == 1
    assert len(seat1.wolf_chat_messages) == 0
    assert len(seat1.votes_cast) == 1
    assert seat1.votes_cast[0].target == 2


def test_dossier_seer_witch_guard_correctness_against_reveal() -> None:
    events = (
        {
            "seq": 1,
            "day": 1,
            "phase": "NIGHT_SEER",
            "type": "seer_check_result",
            "actor": 4,
            "payload": {"target": 1, "result": "wolf"},
        },
        {
            "seq": 2,
            "day": 1,
            "phase": "NIGHT_WITCH",
            "type": "witch_action",
            "actor": 5,
            "payload": {"action": "save", "target": 7},
        },
        {
            "seq": 3,
            "day": 2,
            "phase": "NIGHT_WITCH",
            "type": "witch_action",
            "actor": 5,
            "payload": {"action": "poison", "target": 2},
        },
        {
            "seq": 4,
            "day": 1,
            "phase": "NIGHT_GUARD",
            "type": "guard_protect",
            "actor": 6,
            "payload": {"target": 7},
        },
        {
            "seq": 5,
            "day": 1,
            "phase": "NIGHT_WOLF",
            "type": "wolf_kill_decision",
            "actor": 1,
            "payload": {"target": 7},
        },
    )
    reveal = {
        "winner": "good",
        "seats": [
            {"seat": 1, "role": "wolf", "alive": False},
            {"seat": 2, "role": "wolf", "alive": False},
            {"seat": 4, "role": "seer", "alive": True},
            {"seat": 5, "role": "witch", "alive": True},
            {"seat": 6, "role": "guard", "alive": True},
            {"seat": 7, "role": "villager", "alive": True},
        ],
    }

    dossiers = rd.build_dossiers(
        events=events,
        narrative_rows=(),
        reveal=reveal,
        seat_presentation={},
        key_decisions=(),
    )

    seer = next(dossier for dossier in dossiers if dossier.seat == 4)
    witch = next(dossier for dossier in dossiers if dossier.seat == 5)
    guard = next(dossier for dossier in dossiers if dossier.seat == 6)
    assert seer.seer_checks[0].target_actual_role == "wolf"
    assert witch.witch_actions[0].action == "save"
    assert witch.witch_actions[0].correct is True
    assert witch.witch_actions[1].action == "poison"
    assert witch.witch_actions[1].correct is True
    assert guard.guard_protections[0].blocked_kill is True


def test_dossier_key_decision_involvement_uses_actors_involved_field() -> None:
    decisions = (
        {
            "day": 1,
            "phase": "DAY_VOTE",
            "title": "公开票型收束",
            "analysis": "票分散",
            "actors_involved": {"actor": [3], "target": [1], "voter": [2, 4]},
        },
    )
    reveal = {
        "winner": "good",
        "seats": [
            {"seat": 1, "role": "wolf", "alive": False},
            {"seat": 2, "role": "villager", "alive": True},
            {"seat": 3, "role": "seer", "alive": True},
            {"seat": 4, "role": "villager", "alive": True},
        ],
    }

    dossiers = rd.build_dossiers(
        events=(),
        narrative_rows=(),
        reveal=reveal,
        seat_presentation={},
        key_decisions=decisions,
    )

    by_seat = {dossier.seat: dossier for dossier in dossiers}
    assert by_seat[1].key_decision_involvement[0].role_in_decision == "target"
    assert by_seat[2].key_decision_involvement[0].role_in_decision == "voter"
    assert by_seat[3].key_decision_involvement[0].role_in_decision == "actor"
    assert by_seat[4].key_decision_involvement[0].role_in_decision == "voter"
