import type { GameEvent } from './gameApi';
import type { GameStage } from './gameStage';

export function isGameFinished(events: GameEvent[]) {
  return events.some((event) => event.type === 'game_end' || event.type === 'role_reveal');
}

export function deriveLastPlayablePhase(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const phase = String(
      event.type === 'phase_enter'
        ? event.payload.phase ?? event.phase
        : event.phase,
    );
    if (phase.startsWith('NIGHT') || phase.startsWith('DAY')) {
      return phase;
    }
  }
  return null;
}

export function deriveStageFromEvents(
  events: GameEvent[],
  fallback: GameStage,
): GameStage {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const phase = String(
      event.type === 'phase_enter'
        ? event.payload.phase ?? event.phase
        : event.phase,
    );
    if (phase.startsWith('NIGHT')) {
      return { dayNumber: event.day, phase: 'night' };
    }
    if (phase.startsWith('DAY')) {
      return { dayNumber: event.day, phase: 'day' };
    }
  }
  return fallback;
}
