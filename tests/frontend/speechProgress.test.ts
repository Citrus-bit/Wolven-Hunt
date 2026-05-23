import { describe, expect, it } from 'vitest';
import type { GameEvent } from '../../src/lib/gameApi';
import { deriveDaySpeechProgress } from '../../src/lib/speechProgress';

describe('deriveDaySpeechProgress', () => {
  it('starts with the first live seat when day speech begins without night deaths', () => {
    const events = [
      gameStart(1, 4),
      phaseEnter(2, 1, 'DAY_SPEECH'),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: 1,
      complete: false,
    });
  });

  it('moves to the next seat immediately after a speech event', () => {
    const events = [
      gameStart(1, 4),
      phaseEnter(2, 1, 'DAY_SPEECH'),
      speech(3, 1, 1),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: 2,
      complete: false,
    });
  });

  it('anchors after the largest night death and skips dead players', () => {
    const events = [
      gameStart(1, 5),
      deathAtNight(2, 1, 2),
      deathAtNight(3, 1, 5),
      phaseEnter(4, 1, 'DAY_SPEECH'),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: 1,
      complete: false,
    });
  });

  it('skips players exiled before the current day', () => {
    const events = [
      gameStart(1, 5),
      phaseEnter(2, 1, 'DAY_SPEECH'),
      speech(3, 1, 1),
      phaseEnter(4, 1, 'DAY_VOTE'),
      exile(5, 1, 2),
      phaseEnter(6, 2, 'DAY_SPEECH'),
      speech(7, 2, 1),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: 3,
      complete: false,
    });
  });

  it('returns complete when all live speakers have spoken', () => {
    const events = [
      gameStart(1, 3),
      deathAtNight(2, 1, 2),
      phaseEnter(3, 1, 'DAY_SPEECH'),
      speech(4, 1, 3),
      speech(5, 1, 1),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: null,
      complete: true,
    });
  });

  it('returns complete after the day speech phase exits', () => {
    const events = [
      gameStart(1, 3),
      phaseEnter(2, 1, 'DAY_SPEECH'),
      phaseExit(3, 1, 'DAY_SPEECH'),
    ];

    expect(deriveDaySpeechProgress(events, 'DAY_SPEECH')).toEqual({
      nextSpeakerSeat: null,
      complete: true,
    });
  });
});

function gameStart(start: number, end: number): GameEvent {
  return {
    seq: 1,
    day: 1,
    phase: 'GAME_START',
    type: 'game_start',
    actor: null,
    payload: {
      seat_range: { start, end },
      role_assignment: Object.fromEntries(
        Array.from({ length: end - start + 1 }, (_, index) => [
          String(start + index),
          'villager',
        ]),
      ),
    },
  };
}

function phaseEnter(seq: number, day: number, phase: string): GameEvent {
  return phaseEvent(seq, day, phase, 'phase_enter');
}

function phaseExit(seq: number, day: number, phase: string): GameEvent {
  return phaseEvent(seq, day, phase, 'phase_exit');
}

function phaseEvent(seq: number, day: number, phase: string, type: string): GameEvent {
  return {
    seq,
    day,
    phase,
    type,
    actor: null,
    payload: { phase },
  };
}

function speech(seq: number, day: number, actor: number): GameEvent {
  return {
    seq,
    day,
    phase: 'DAY_SPEECH',
    type: 'speech',
    actor,
    payload: { text: `${actor}号发言` },
  };
}

function deathAtNight(seq: number, day: number, seat: number): GameEvent {
  return {
    seq,
    day,
    phase: 'NIGHT_RESOLVE',
    type: 'death_at_night',
    actor: null,
    payload: { seat },
  };
}

function exile(seq: number, day: number, seat: number): GameEvent {
  return {
    seq,
    day,
    phase: 'DAY_EXILE',
    type: 'exile',
    actor: null,
    payload: { seat },
  };
}
