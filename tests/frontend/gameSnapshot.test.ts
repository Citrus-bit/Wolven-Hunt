import { describe, expect, it } from 'vitest';
import {
  deriveLastPlayablePhase,
  deriveStageFromEvents,
  isGameFinished,
} from '../../src/lib/gameSnapshot';
import type { GameEvent } from '../../src/lib/gameApi';

describe('gameSnapshot', () => {
  it('detects finished games from terminal events', () => {
    expect(isGameFinished([event(1, 'game_end', 'CHECK_WIN_DAY')])).toBe(true);
    expect(isGameFinished([event(1, 'role_reveal', 'GAME_END')])).toBe(true);
    expect(isGameFinished([event(1, 'speech', 'DAY_SPEECH')])).toBe(false);
  });

  it('freezes on the last playable phase instead of GAME_END', () => {
    const events = [
      phaseEnter(1, 1, 'NIGHT_START'),
      phaseEnter(2, 1, 'NIGHT_RESOLVE'),
      event(3, 'game_end', 'GAME_END'),
      event(4, 'role_reveal', 'GAME_END'),
    ];

    expect(deriveLastPlayablePhase(events)).toBe('NIGHT_RESOLVE');
    expect(
      deriveStageFromEvents(events, { dayNumber: 1, phase: 'day' }),
    ).toEqual({ dayNumber: 1, phase: 'night' });
  });
});

function phaseEnter(seq: number, day: number, phase: string): GameEvent {
  return {
    seq,
    day,
    phase,
    type: 'phase_enter',
    actor: null,
    payload: { phase },
  };
}

function event(seq: number, type: string, phase: string): GameEvent {
  return {
    seq,
    day: 1,
    phase,
    type,
    actor: null,
    payload: {},
  };
}
