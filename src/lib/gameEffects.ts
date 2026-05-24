import type { GameEvent, SpectatorEffect } from './gameApi';

export type SeatEffectState = {
  guardShield?: boolean;
  guardShieldSeq?: number;
  wolfAttack?: boolean;
  wolfAttackSeq?: number;
  wolfAttackBlocked?: boolean;
  seerVisionSeq?: number;
  outBadge?: boolean;
  outBadgeSeq?: number;
};

export type SeatEffectMap = Record<number, SeatEffectState>;
export type EffectSeenAtMap = Record<string, number>;

type BuildSeatEffectOptions = {
  currentDay?: number | null;
  nowMs?: number;
  seenAtByKey?: EffectSeenAtMap;
};

const GUARD_SETTLE_GRACE_MS = 900;
const WOLF_ATTACK_MS = 2600;
const SEER_VISION_MS = 2200;
const POTION_EFFECT_MS = 1800;

const PHASE_ORDER: Record<string, number> = {
  GAME_START: 0,
  NIGHT_START: 10,
  NIGHT_GUARD: 20,
  NIGHT_WOLF_CHAT: 30,
  NIGHT_WOLF_VOTE: 40,
  NIGHT_WITCH: 50,
  NIGHT_SEER: 60,
  NIGHT_RESOLVE: 70,
  CHECK_WIN_NIGHT: 80,
  DAY_ANNOUNCE: 90,
  DAY_LAST_WORDS: 100,
  DAY_SPEECH: 110,
  DAY_VOTE: 120,
  DAY_VOTE_PK: 130,
  DAY_EXILE: 140,
  CHECK_WIN_DAY: 150,
  GAME_END: 160,
};

export function buildSeatEffectMap(
  effects: SpectatorEffect[],
  currentPhase: string | null,
  options: BuildSeatEffectOptions = {},
): SeatEffectMap {
  const map: SeatEffectMap = {};
  const currentDay = options.currentDay ?? latestEffectDay(effects);
  const nowMs = options.nowMs ?? Number.POSITIVE_INFINITY;
  for (const effect of effects) {
    const seatState = (map[effect.target_seat] ??= {});
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    if (effect.kind === 'death_reveal') {
      seatState.outBadge = true;
      seatState.outBadgeSeq = Math.max(seatState.outBadgeSeq ?? 0, effect.seq);
    } else if (effect.kind === 'guard_shield') {
      if (isGuardShieldActive(effect, currentPhase, currentDay, ageMs)) {
        seatState.guardShield = true;
        seatState.guardShieldSeq = effect.seq;
      }
    } else if (effect.kind === 'wolf_attack') {
      const blocked = effect.meta.blocked_by_guard === true;
      const durationMs = Math.max(1200, effect.duration_ms || WOLF_ATTACK_MS);
      if (isShortEffectActive(effect, currentPhase, currentDay, ageMs, durationMs)) {
        seatState.wolfAttack = true;
        seatState.wolfAttackSeq = effect.seq;
        seatState.wolfAttackBlocked = blocked;
      }
    } else if (effect.kind === 'seer_vision') {
      const durationMs = Math.max(1200, effect.duration_ms || SEER_VISION_MS);
      if (isShortEffectActive(effect, currentPhase, currentDay, ageMs, durationMs)) {
        seatState.seerVisionSeq = effect.seq;
      }
    }
  }
  return map;
}

export function activePotionEffects(
  effects: SpectatorEffect[],
  currentPhase: string | null,
  options: BuildSeatEffectOptions = {},
) {
  const currentDay = options.currentDay ?? latestEffectDay(effects);
  const nowMs = options.nowMs ?? Number.POSITIVE_INFINITY;
  return effects.filter((effect) => {
    if (effect.kind !== 'witch_potion') {
      return false;
    }
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    const durationMs = Math.max(900, effect.duration_ms || POTION_EFFECT_MS);
    return isShortEffectActive(effect, currentPhase, currentDay, ageMs, durationMs);
  });
}

export function effectIdentity(effect: SpectatorEffect) {
  return [
    effect.seq,
    effect.kind,
    effect.source_seat ?? 'none',
    effect.target_seat,
    effect.asset_key,
  ].join(':');
}

export function seedEffectSeenAt(
  effects: SpectatorEffect[],
  seenAtByKey: EffectSeenAtMap,
  nowMs: number,
) {
  for (const effect of effects) {
    const key = effectIdentity(effect);
    if (!(key in seenAtByKey)) {
      seenAtByKey[key] = nowMs;
    }
  }
}

export function deathRevealSeats(effects: SpectatorEffect[]) {
  const dead = new Set<number>();
  for (const effect of effects) {
    if (effect.kind === 'death_reveal') {
      dead.add(effect.target_seat);
    }
  }
  return dead;
}

export function publicEliminatedSeats(
  events: GameEvent[],
  effects: SpectatorEffect[],
) {
  const dead = deathRevealSeats(effects);
  for (const event of events) {
    if (event.type === 'death_at_night' || event.type === 'exile') {
      addFiniteSeat(dead, event.payload.seat);
    }
    if (event.type === 'role_reveal' && Array.isArray(event.payload.seats)) {
      for (const seatInfo of event.payload.seats) {
        if (
          typeof seatInfo === 'object' &&
          seatInfo !== null &&
          'seat' in seatInfo &&
          'alive' in seatInfo &&
          !seatInfo.alive
        ) {
          addFiniteSeat(dead, seatInfo.seat);
        }
      }
    }
  }
  return dead;
}

function effectAgeMs(
  effect: SpectatorEffect,
  seenAtByKey: EffectSeenAtMap | undefined,
  nowMs: number,
) {
  if (!seenAtByKey) {
    return 0;
  }
  const seenAt = seenAtByKey[effectIdentity(effect)];
  if (seenAt === undefined) {
    return 0;
  }
  return Math.max(0, nowMs - seenAt);
}

function within(ageMs: number, durationMs: number) {
  return ageMs <= durationMs;
}

function isGuardShieldActive(
  effect: SpectatorEffect,
  currentPhase: string | null,
  currentDay: number | null,
  ageMs: number,
) {
  if (!isSameDay(effect, currentDay)) {
    return false;
  }
  const currentOrder = phaseOrder(currentPhase);
  if (currentOrder === null) {
    return within(ageMs, GUARD_SETTLE_GRACE_MS);
  }
  const effectOrder = phaseOrder(effect.phase) ?? PHASE_ORDER.NIGHT_GUARD;
  return currentOrder >= effectOrder && currentOrder <= PHASE_ORDER.NIGHT_RESOLVE;
}

function isShortEffectActive(
  effect: SpectatorEffect,
  currentPhase: string | null,
  currentDay: number | null,
  ageMs: number,
  durationMs: number,
) {
  if (!isSameDay(effect, currentDay) || !within(ageMs, durationMs)) {
    return false;
  }
  const currentOrder = phaseOrder(currentPhase);
  if (currentOrder === null) {
    return true;
  }
  const effectOrder = phaseOrder(effect.phase) ?? currentOrder;
  return currentOrder >= effectOrder && currentOrder <= PHASE_ORDER.DAY_ANNOUNCE;
}

function isSameDay(effect: SpectatorEffect, currentDay: number | null) {
  return currentDay === null || effect.day === currentDay;
}

function phaseOrder(phase: string | null) {
  if (!phase) {
    return null;
  }
  return PHASE_ORDER[phase] ?? null;
}

function latestEffectDay(effects: SpectatorEffect[]) {
  return effects.reduce<number | null>(
    (day, effect) => (day === null || effect.day > day ? effect.day : day),
    null,
  );
}

function addFiniteSeat(seats: Set<number>, value: unknown) {
  const seat = Number(value);
  if (Number.isFinite(seat)) {
    seats.add(seat);
  }
}
