from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from wolven_hunt.config.prompts import DEFAULT_PROMPT_VERSION
from wolven_hunt.config.schema import GameConfig, RolePack, RuleSet


class ConfigError(RuntimeError):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"config is not a mapping: {path}")
    return data


def _canonical_hash(parts: tuple[dict[str, Any], ...]) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def load_game_config(path: str | Path) -> GameConfig:
    config_path = Path(path).resolve()
    root = config_path.parent
    raw = _read_yaml(config_path)

    role_pack_ref = str(raw["role_pack"])
    rule_set_ref = str(raw["rule_set"])
    model_roster_ref = str(raw["model_roster"])
    prompt_pack_raw = raw["prompt_pack"]

    role_pack_path = (root / role_pack_ref).resolve()
    rule_set_path = (root / rule_set_ref).resolve()
    model_roster_path = (root / model_roster_ref).resolve()
    prompt_pack_root = (root / str(prompt_pack_raw["root"])).resolve()

    role_pack_raw = _read_yaml(role_pack_path)
    rule_set_raw = _read_yaml(rule_set_path)
    _read_yaml(model_roster_path)

    if not prompt_pack_root.exists():
        raise ConfigError(f"missing prompt pack root: {prompt_pack_root}")
    missing_templates = missing_prompt_templates(prompt_pack_root, DEFAULT_PROMPT_VERSION)
    if missing_templates:
        missing = ", ".join(missing_templates)
        raise ConfigError(
            f"prompt pack root is missing current {DEFAULT_PROMPT_VERSION} templates: {missing}"
        )

    role_pack = RolePack.model_validate(role_pack_raw)
    rule_set = RuleSet.model_validate(rule_set_raw)
    if role_pack.seat_count != raw["seat_range"]["end"] - raw["seat_range"]["start"] + 1:
        raise ConfigError("role_pack.seat_count does not match seat_range")
    if sum(role.count for role in role_pack.roles.values()) != role_pack.seat_count:
        raise ConfigError("role counts do not sum to seat_count")

    config_hash = _canonical_hash((role_pack_raw, rule_set_raw))
    return GameConfig.model_validate(
        {
            "schema_version": raw["schema_version"],
            "name": raw["name"],
            "description": raw["description"],
            "seat_range": raw["seat_range"],
            "role_pack_ref": role_pack_ref,
            "rule_set_ref": rule_set_ref,
            "model_roster_ref": model_roster_ref,
            "prompt_pack": prompt_pack_raw,
            "random_seed": raw["random_seed"],
            "metadata": raw["metadata"],
            "role_pack": role_pack,
            "rule_set": rule_set,
            "config_hash": config_hash,
            "path": config_path,
            "prompt_pack_root": prompt_pack_root,
            "model_roster_path": model_roster_path,
        }
    )


def missing_prompt_templates(prompt_pack_root: Path, version: str) -> list[str]:
    expected_paths = [prompt_pack_root / f"system.{version}.md"]
    for role_name in ("guard", "seer", "villager", "witch", "wolf"):
        for kind in ("last_words", "night_action", "speech", "vote"):
            expected_paths.append(prompt_pack_root / role_name / f"{kind}.{version}.md")
    return [
        str(path.relative_to(prompt_pack_root))
        for path in expected_paths
        if not path.exists()
    ]


def ensure_prompt_version(prompt_pack_root: Path, version: str) -> None:
    missing_prompt_templates = missing_prompt_templates_for_error(prompt_pack_root, version)
    if missing_prompt_templates:
        missing = ", ".join(missing_prompt_templates)
        raise ConfigError(f"prompt pack root is missing {version} templates: {missing}")


def missing_prompt_templates_for_error(prompt_pack_root: Path, version: str) -> list[str]:
    return missing_prompt_templates(prompt_pack_root, version)
