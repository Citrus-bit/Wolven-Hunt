from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from wolven_hunt.core.events import Event
from wolven_hunt.storage.narrative import event_to_narrative


def test_narrative_fixture_cases_match_templates() -> None:
    cases = json.loads(Path("tests/fixtures/narrative_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        event = Event.model_validate(case["event"])
        row = event_to_narrative(event)
        assert row is not None
        assert row.to_dict() == cast(dict[str, object], case["expected"])
