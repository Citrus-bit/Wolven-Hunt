import { describe, expect, it } from 'vitest';
import type { TurnRequest } from '../../src/lib/gameApi';
import { parseWitchWolfKillTarget } from '../../src/lib/humanTurn';

describe('humanTurn', () => {
  it('parses the witch wolf kill target from a valid turn request', () => {
    expect(parseWitchWolfKillTarget(witchTurn({ wolf_kill_target: 4 }))).toBe(4);
  });

  it('returns null when the witch wolf kill target is missing or invalid', () => {
    expect(parseWitchWolfKillTarget(null)).toBeNull();
    expect(parseWitchWolfKillTarget({ ...witchTurn({}), constraints: {} })).toBeNull();
    expect(parseWitchWolfKillTarget(witchTurn({ wolf_kill_target: null }))).toBeNull();
    expect(parseWitchWolfKillTarget(witchTurn({ wolf_kill_target: 'bad' }))).toBeNull();
    expect(parseWitchWolfKillTarget(witchTurn({ wolf_kill_target: 12 }))).toBeNull();
    expect(
      parseWitchWolfKillTarget({ ...witchTurn({ wolf_kill_target: 4 }), kind: 'guard' }),
    ).toBeNull();
  });
});

function witchTurn(constraints: Record<string, unknown>): TurnRequest {
  return {
    seat: 3,
    kind: 'witch',
    deadline_ts: 1,
    timeout_seconds: 20,
    valid_targets: [1, 2, 3, 4, 5],
    constraints,
    phase: 'NIGHT_WITCH',
    day: 1,
  };
}
