import { describe, expect, it } from 'vitest';
import {
  DEAD_GOD_AUDIO_SETTLE_MS,
  dayAnnounceAudioPlan,
  deadGodSettleMs,
  phaseAudioPlan,
} from '../../src/lib/gamePhaseAudio';
import type { GameEvent } from '../../src/lib/gameApi';

describe('gamePhaseAudio', () => {
  it('plays night start howl without guard audio', () => {
    const event = phaseEnter(2, 'NIGHT_START');

    expect(phaseAudioPlan(event, [gameStart(), event])).toMatchObject({
      ackEvent: 'night_intro_done',
      sequence: ['wolf_howl'],
      settleMs: 0,
    });
  });

  it('adds a five second settle delay for dead god phases', () => {
    const events = [
      gameStart(),
      death(4),
      phaseEnter(3, 'NIGHT_GUARD'),
      exile(3),
      phaseEnter(5, 'NIGHT_WITCH'),
      death(1),
      phaseEnter(7, 'NIGHT_SEER'),
    ];

    expect(deadGodSettleMs('NIGHT_GUARD', events)).toBe(DEAD_GOD_AUDIO_SETTLE_MS);
    expect(deadGodSettleMs('NIGHT_WITCH', events)).toBe(DEAD_GOD_AUDIO_SETTLE_MS);
    expect(deadGodSettleMs('NIGHT_SEER', events)).toBe(DEAD_GOD_AUDIO_SETTLE_MS);
  });

  it('does not settle for living gods or wolf audio', () => {
    const events = [gameStart(), death(6), phaseEnter(3, 'NIGHT_GUARD')];

    expect(deadGodSettleMs('NIGHT_GUARD', events)).toBe(0);
    expect(deadGodSettleMs('NIGHT_WOLF_CHAT', events)).toBe(0);
    expect(phaseAudioPlan(phaseEnter(4, 'NIGHT_WOLF_CHAT'), events)).toMatchObject({
      ackEvent: 'night_wolves_done',
      sequence: ['night_wolves'],
      settleMs: 0,
    });
  });

  it('uses the guard audio ack for the guard phase', () => {
    const event = phaseEnter(2, 'NIGHT_GUARD');

    expect(phaseAudioPlan(event, [gameStart(), event])).toMatchObject({
      ackEvent: 'night_guard_done',
      sequence: ['night_guard'],
      settleMs: 0,
    });
  });

  it('plays only dawn intro audio on day announce phase enter', () => {
    const event = phaseEnter(7, 'DAY_ANNOUNCE');
    const events = [gameStart(), event, death(10, 2)];

    expect(phaseAudioPlan(event, events)).toMatchObject({
      ackEvent: 'day_intro_done',
      sequence: ['day_rooster', 'day_dawn'],
      settleMs: 0,
    });
  });

  it('uses day_announce deaths to play peaceful result audio', () => {
    expect(dayAnnounceAudioPlan(dayAnnounce(8, 2, []))).toEqual({
      sequence: ['day_peaceful'],
      gapMs: 0,
    });
  });

  it('uses day_announce deaths to play death result audio', () => {
    expect(dayAnnounceAudioPlan(dayAnnounce(8, 2, [10]))).toEqual({
      sequence: ['day_death'],
      gapMs: 0,
    });
  });

  it('does not need local death_at_night history to play death result audio', () => {
    const event = dayAnnounce(8, 3, [10]);

    expect(dayAnnounceAudioPlan(event)).toEqual({
      sequence: ['day_death'],
      gapMs: 0,
    });
  });

  it('ignores prior peaceful nights when current day announce has deaths', () => {
    const previousPeaceful = noDeathTonight(6, 2);
    const currentAnnounce = dayAnnounce(12, 3, [10]);

    expect(dayAnnounceAudioPlan(previousPeaceful)).toBeNull();
    expect(dayAnnounceAudioPlan(currentAnnounce)).toEqual({
      sequence: ['day_death'],
      gapMs: 0,
    });
  });
});

function gameStart(): GameEvent {
  return {
    seq: 1,
    day: 1,
    phase: 'GAME_START',
    type: 'game_start',
    actor: null,
    payload: {
      role_assignment: {
        '1': 'seer',
        '2': 'wolf',
        '3': 'witch',
        '4': 'guard',
        '5': 'villager',
        '6': 'villager',
        '7': 'villager',
        '8': 'wolf',
        '9': 'villager',
        '10': 'wolf',
      },
    },
  };
}

function phaseEnter(seq: number, phase: string, day = 2): GameEvent {
  return {
    seq,
    day,
    phase,
    type: 'phase_enter',
    actor: null,
    payload: { phase },
  };
}

function death(seat: number, day = 1): GameEvent {
  return {
    seq: 20 + seat,
    day,
    phase: 'NIGHT_RESOLVE',
    type: 'death_at_night',
    actor: null,
    payload: { seat },
  };
}

function dayAnnounce(seq: number, day: number, deaths: number[]): GameEvent {
  return {
    seq,
    day,
    phase: 'DAY_ANNOUNCE',
    type: 'day_announce',
    actor: null,
    payload: {
      deaths,
      message:
        deaths.length === 0
          ? '昨晚是平安夜'
          : `昨晚死亡玩家: ${deaths.join(', ')}`,
    },
  };
}

function noDeathTonight(seq: number, day: number): GameEvent {
  return {
    seq,
    day,
    phase: 'NIGHT_RESOLVE',
    type: 'no_death_tonight',
    actor: null,
    payload: { message: '昨晚是平安夜' },
  };
}

function exile(seat: number): GameEvent {
  return {
    seq: 30 + seat,
    day: 1,
    phase: 'DAY_EXILE',
    type: 'exile',
    actor: null,
    payload: { seat },
  };
}
