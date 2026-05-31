import { describe, expect, it } from 'vitest';
import type { GameEvent } from '../../src/lib/gameApi';
import {
  deriveSeatIdentityBadges,
  deriveSeerCampLocks,
  deriveSelfRoleInfo,
  normalizeHumanIdentityMarks,
} from '../../src/lib/identityMarks';

describe('identityMarks', () => {
  it('normalizes only legal seat role marks', () => {
    expect(
      normalizeHumanIdentityMarks({
        0: 'wolf',
        1: 'wolf',
        4: 'seer',
        11: 'witch',
        bad: 'guard',
        6: 'unknown',
      }),
    ).toEqual({
      1: 'wolf',
      4: 'seer',
    });
  });

  it('derives self role and wolf teammates from sanitized player game_start', () => {
    expect(
      deriveSelfRoleInfo([
        event(1, 'game_start', {
          self_role: 'wolf',
          teammates: [2, '7', null, 'bad'],
        }),
      ]),
    ).toEqual({
      role: 'wolf',
      teammates: [2, 7],
    });
  });

  it('derives seer camp locks from current and legacy result payloads', () => {
    expect(
      deriveSeerCampLocks([
        event(7, 'seer_check_result', { target: 2, camp: 'wolf' }),
        event(9, 'seer_check_result', { target: 4, result: 'good' }),
        event(11, 'seer_check_result', { target: 5, camp: 'seer' }),
      ]),
    ).toEqual({
      2: 'wolf',
      4: 'good',
    });
  });

  it('prioritizes true role, self role, seer camp lock, then manual guess', () => {
    const badges = deriveSeatIdentityBadges({
      humanSeat: 1,
      humanIdentityMarks: {
        2: 'guard',
        3: 'wolf',
        4: 'witch',
      },
      events: [
        event(1, 'game_start', { self_role: 'seer', teammates: [] }),
        event(7, 'seer_check_result', { target: 2, camp: 'wolf' }),
        event(9, 'seer_check_result', { target: 3, result: 'good' }),
      ],
    });

    expect(badges).toEqual({
      1: { kind: 'role', role: 'seer', source: 'true' },
      2: { kind: 'camp', camp: 'wolf', source: 'seer' },
      3: { kind: 'camp', camp: 'good', source: 'seer' },
      4: { kind: 'role', role: 'witch', source: 'guess' },
    });
  });

  it('lets terminal role reveal override seer locks and guesses', () => {
    const badges = deriveSeatIdentityBadges({
      humanSeat: 1,
      humanIdentityMarks: {
        2: 'wolf',
      },
      events: [
        event(1, 'game_start', { self_role: 'seer', teammates: [] }),
        event(7, 'seer_check_result', { target: 2, camp: 'wolf' }),
        event(20, 'role_reveal', {
          seats: [{ seat: 2, role: 'villager', alive: true }],
        }),
      ],
    });

    expect(badges[2]).toEqual({
      kind: 'role',
      role: 'villager',
      source: 'true',
    });
  });
});

function event(
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): GameEvent {
  return {
    seq,
    day: 1,
    phase: type === 'role_reveal' ? 'GAME_END' : 'NIGHT_SEER',
    type,
    actor: null,
    payload,
  };
}
