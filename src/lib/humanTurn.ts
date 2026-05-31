import type { TurnRequest } from './gameApi';

export function parseWitchWolfKillTarget(turn: TurnRequest | null) {
  if (!turn || turn.kind !== 'witch') {
    return null;
  }

  const rawTarget = turn.constraints.wolf_kill_target;
  if (rawTarget === null || rawTarget === undefined || rawTarget === '') {
    return null;
  }

  const target = Number(rawTarget);
  if (!Number.isInteger(target) || target <= 0) {
    return null;
  }

  if (!Array.isArray(turn.valid_targets) || !turn.valid_targets.includes(target)) {
    return null;
  }

  return target;
}
