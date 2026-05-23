import type { GameEvent } from './gameApi';

export type DaySpeechProgress = {
  nextSpeakerSeat: number | null;
  complete: boolean;
};

export function deriveDaySpeechProgress(
  events: GameEvent[],
  currentPhase: string | null,
): DaySpeechProgress {
  if (currentPhase !== 'DAY_SPEECH') {
    return { nextSpeakerSeat: null, complete: false };
  }
  const phaseEnter = [...events]
    .reverse()
    .find((event) => event.type === 'phase_enter' && phaseName(event) === 'DAY_SPEECH');
  if (!phaseEnter) {
    return { nextSpeakerSeat: null, complete: false };
  }
  const day = phaseEnter.day;
  const phaseExited = events.some(
    (event) =>
      event.seq > phaseEnter.seq &&
      event.day === day &&
      event.type === 'phase_exit' &&
      phaseName(event) === 'DAY_SPEECH',
  );
  if (phaseExited) {
    return { nextSpeakerSeat: null, complete: true };
  }

  const order = daySpeechOrder(events, day);
  const spoken = new Set(
    events
      .filter(
        (event) =>
          event.day === day &&
          event.type === 'speech' &&
          event.phase === 'DAY_SPEECH' &&
          typeof event.actor === 'number',
      )
      .map((event) => Number(event.actor)),
  );
  const nextSpeakerSeat = order.find((seat) => !spoken.has(seat)) ?? null;
  return { nextSpeakerSeat, complete: nextSpeakerSeat === null };
}

function daySpeechOrder(events: GameEvent[], day: number) {
  const seats = seatNumbers(events);
  const dead = deadSeatsBeforeOrDuringDay(events, day);
  const alive = seats.filter((seat) => !dead.has(seat));
  const nightDeaths = events
    .filter((event) => event.day === day && event.type === 'death_at_night')
    .map((event) => Number(event.payload.seat))
    .filter(Number.isFinite);
  const startNumber = nightDeaths.length > 0 ? Math.max(...nightDeaths) + 1 : 1;
  return [
    ...alive.filter((seat) => seat >= startNumber),
    ...alive.filter((seat) => seat < startNumber),
  ];
}

function seatNumbers(events: GameEvent[]) {
  const gameStart = events.find((event) => event.type === 'game_start');
  const seatRange = gameStart?.payload.seat_range;
  if (isRecord(seatRange)) {
    const start = Number(seatRange.start);
    const end = Number(seatRange.end);
    if (Number.isInteger(start) && Number.isInteger(end) && start <= end) {
      return range(start, end);
    }
  }
  const assignment = gameStart?.payload.role_assignment;
  if (isRecord(assignment)) {
    const seats = Object.keys(assignment)
      .map(Number)
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (seats.length > 0) {
      return seats;
    }
  }
  return range(1, 10);
}

function deadSeatsBeforeOrDuringDay(events: GameEvent[], day: number) {
  const dead = new Set<number>();
  for (const event of events) {
    if (event.day > day) {
      continue;
    }
    if (event.type === 'death_at_night' || event.type === 'exile') {
      const seat = Number(event.payload.seat);
      if (Number.isFinite(seat)) {
        dead.add(seat);
      }
    }
  }
  return dead;
}

function phaseName(event: GameEvent) {
  return String(event.payload.phase ?? event.phase);
}

function range(start: number, end: number) {
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
