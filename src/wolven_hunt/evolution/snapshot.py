from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path

from wolven_hunt.config.loader import ensure_prompt_version
from wolven_hunt.config.prompts import DEFAULT_PROMPT_VERSION

from .axes import EvolutionAxis

VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")
ROLES = ("guard", "seer", "villager", "witch", "wolf")
KINDS = ("last_words", "night_action", "speech", "vote")


def version_number(version: str) -> int:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise ValueError(f"invalid prompt version: {version}")
    return int(match.group(1))


def next_version_from_files(prompt_root: Path, minimum: int = 7) -> int:
    highest = minimum - 1
    for path in prompt_root.rglob("*.v*.md"):
        stem = path.stem
        version = stem.rsplit(".", 1)[-1]
        try:
            highest = max(highest, version_number(version))
        except ValueError:
            continue
    return highest + 1


def prompt_file(prompt_root: Path, role: str, kind: str, version: str) -> Path:
    return prompt_root / role / f"{kind}.{version}.md"


def system_file(prompt_root: Path, version: str) -> Path:
    return prompt_root / f"system.{version}.md"


def seed_char_cap(prompt_root: Path, axis: EvolutionAxis, ratio: float) -> int:
    seed_path = prompt_file(prompt_root, axis.role.value, axis.prompt_kind, DEFAULT_PROMPT_VERSION)
    return math.ceil(len(seed_path.read_text(encoding="utf-8")) * ratio)


def create_snapshot(
    *,
    prompt_root: Path,
    source_version: str,
    target_version: str,
    axis: EvolutionAxis,
    replacement_text: str,
) -> None:
    ensure_prompt_version(prompt_root, source_version)
    with tempfile.TemporaryDirectory(prefix=f"prompt-{target_version}.") as tmp_name:
        tmp_root = Path(tmp_name)
        _write_tmp_snapshot(
            tmp_root=tmp_root,
            prompt_root=prompt_root,
            source_version=source_version,
            target_version=target_version,
            axis=axis,
            replacement_text=replacement_text,
        )
        _install_tmp_snapshot(tmp_root=tmp_root, prompt_root=prompt_root, target_version=target_version)
    ensure_prompt_version(prompt_root, target_version)


def create_snapshot_in_dir(
    *,
    output_root: Path,
    prompt_root: Path,
    source_version: str,
    target_version: str,
    axis: EvolutionAxis,
    replacement_text: str,
) -> Path:
    ensure_prompt_version(prompt_root, source_version)
    output_root.mkdir(parents=True, exist_ok=True)
    _write_tmp_snapshot(
        tmp_root=output_root,
        prompt_root=prompt_root,
        source_version=source_version,
        target_version=target_version,
        axis=axis,
        replacement_text=replacement_text,
    )
    ensure_prompt_version(output_root, target_version)
    return output_root


def _write_tmp_snapshot(
    *,
    tmp_root: Path,
    prompt_root: Path,
    source_version: str,
    target_version: str,
    axis: EvolutionAxis,
    replacement_text: str,
) -> None:
    tmp_root.mkdir(parents=True, exist_ok=True)
    system_file(tmp_root, target_version).write_text(
        system_file(prompt_root, source_version).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for role in ROLES:
        (tmp_root / role).mkdir(parents=True, exist_ok=True)
        for kind in KINDS:
            text = (
                replacement_text
                if role == axis.role.value and kind == axis.prompt_kind
                else prompt_file(prompt_root, role, kind, source_version).read_text(encoding="utf-8")
            )
            prompt_file(tmp_root, role, kind, target_version).write_text(text, encoding="utf-8")


def _install_tmp_snapshot(*, tmp_root: Path, prompt_root: Path, target_version: str) -> None:
    destination = system_file(prompt_root, target_version)
    if destination.exists():
        raise FileExistsError(f"prompt version already exists: {target_version}")
    destination.write_text(system_file(tmp_root, target_version).read_text(encoding="utf-8"), encoding="utf-8")
    for role in ROLES:
        (prompt_root / role).mkdir(parents=True, exist_ok=True)
        for kind in KINDS:
            dest = prompt_file(prompt_root, role, kind, target_version)
            if dest.exists():
                raise FileExistsError(f"prompt file already exists: {dest}")
            dest.write_text(
                prompt_file(tmp_root, role, kind, target_version).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
