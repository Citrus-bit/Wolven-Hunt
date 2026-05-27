import type { GameEvent } from './gameApi';
import type { GameAudioKey } from './audioAssets';

export const DEAD_GOD_AUDIO_SETTLE_MS = 5000;

export type GamePhaseAudioPlan = {
  phase: string;
  ackEvent: string;
  sequence: GameAudioKey[];
  gapMs: number;
  settleMs: number;
};

export type DayAnnounceAudioPlan = {
  sequence: GameAudioKey[];
  gapMs: number;
};

export type HostAudioPlan = {
  sequence: GameAudioKey[];
  gapMs: number;
};

type GodRole = 'guard' | 'witch' | 'seer';

const HOST_AUDIO_GAP_MS = 350;

const GOD_AUDIO_PHASES: Record<string, GodRole> = {
  NIGHT_GUARD: 'guard',
  NIGHT_WITCH: 'witch',
  NIGHT_SEER: 'seer',
};

export function phaseAudioPlan(
  event: GameEvent,
  events: GameEvent[],
): GamePhaseAudioPlan | null {
  if (event.type !== 'phase_enter') {
    return null;
  }
  const phase = String(event.payload.phase ?? event.phase);
  const settleMs = deadGodSettleMs(phase, events);
  if (phase === 'NIGHT_START') {
    return {
      phase,
      ackEvent: 'night_intro_done',
      sequence: ['wolf_howl'],
      gapMs: 1000,
      settleMs,
    };
  }
  if (phase === 'NIGHT_GUARD') {
    return {
      phase,
      ackEvent: 'night_guard_done',
      sequence: ['night_guard'],
      gapMs: 1000,
      settleMs,
    };
  }
  if (phase === 'NIGHT_WOLF_CHAT') {
    return {
      phase,
      ackEvent: 'night_wolves_done',
      sequence: ['night_wolves'],
      gapMs: 1000,
      settleMs,
    };
  }
  if (phase === 'NIGHT_WITCH') {
    return {
      phase,
      ackEvent: 'night_witch_done',
      sequence: ['night_witch'],
      gapMs: 1000,
      settleMs,
    };
  }
  if (phase === 'NIGHT_SEER') {
    return {
      phase,
      ackEvent: 'night_seer_done',
      sequence: ['night_seer'],
      gapMs: 1000,
      settleMs,
    };
  }
  if (phase === 'DAY_ANNOUNCE') {
    return {
      phase,
      ackEvent: 'day_intro_done',
      sequence: ['day_rooster', 'day_dawn'],
      gapMs: 250,
      settleMs,
    };
  }
  return null;
}

export function dayAnnounceAudioPlan(
  event: GameEvent,
): DayAnnounceAudioPlan | null {
  if (event.type !== 'day_announce') {
    return null;
  }
  const deaths = event.payload.deaths;
  const hasDeath = Array.isArray(deaths) && deaths.length > 0;
  return {
    sequence: [hasDeath ? 'day_death' : 'day_peaceful'],
    gapMs: 0,
  };
}

export function hostAudioPlan(event: GameEvent): HostAudioPlan | null {
  if (event.type === 'phase_enter') {
    const phase = String(event.payload.phase ?? event.phase);
    if (phase === 'DAY_VOTE' || phase === 'DAY_VOTE_PK') {
      return { sequence: ['day_vote_start'], gapMs: HOST_AUDIO_GAP_MS };
    }
    if (phase === 'DAY_LAST_WORDS') {
      return { sequence: ['day_last_words_start'], gapMs: HOST_AUDIO_GAP_MS };
    }
    return null;
  }

  if (
    event.type === 'speech' &&
    event.phase === 'DAY_SPEECH' &&
    typeof event.actor === 'number'
  ) {
    const key = speechSeatAudioKey(event.actor);
    return key === null ? null : { sequence: [key], gapMs: HOST_AUDIO_GAP_MS };
  }

  return null;
}

export function deadGodSettleMs(phase: string, events: GameEvent[]) {
  const role = GOD_AUDIO_PHASES[phase];
  if (!role) {
    return 0;
  }
  const seat = roleSeat(events, role);
  if (seat === null) {
    return 0;
  }
  return eliminatedSeats(events).has(seat) ? DEAD_GOD_AUDIO_SETTLE_MS : 0;
}

function roleSeat(events: GameEvent[], role: GodRole): number | null {
  for (const event of events) {
    if (event.type !== 'game_start') {
      continue;
    }
    const assignment = event.payload.role_assignment;
    if (!assignment || typeof assignment !== 'object' || Array.isArray(assignment)) {
      continue;
    }
    for (const [seat, assignedRole] of Object.entries(
      assignment as Record<string, unknown>,
    )) {
      if (assignedRole === role) {
        const parsed = Number(seat);
        return Number.isFinite(parsed) ? parsed : null;
      }
    }
  }
  return null;
}

function eliminatedSeats(events: GameEvent[]) {
  const seats = new Set<number>();
  for (const event of events) {
    if (event.type !== 'death_at_night' && event.type !== 'exile') {
      continue;
    }
    const seat = Number(event.payload.seat);
    if (Number.isFinite(seat)) {
      seats.add(seat);
    }
  }
  return seats;
}

function speechSeatAudioKey(seat: number): GameAudioKey | null {
  if (!Number.isInteger(seat) || seat < 1 || seat > 10) {
    return null;
  }
  return `speech_seat_${seat}` as GameAudioKey;
}
