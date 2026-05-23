import type { SpectatorEffect } from './gameApi';

export type SeatEffectState = {
  guardShield?: boolean;
  wolfAttack?: boolean;
  wolfAttackBlocked?: boolean;
  seerVisionSeq?: number;
  outBadge?: boolean;
};

export type SeatEffectMap = Record<number, SeatEffectState>;
export type EffectSeenAtMap = Record<string, number>;

type BuildSeatEffectOptions = {
  nowMs?: number;
  seenAtByKey?: EffectSeenAtMap;
};

const FAST_PHASE_GRACE_MS = 5000;

export function buildSeatEffectMap(
  effects: SpectatorEffect[],
  currentPhase: string | null,
  options: BuildSeatEffectOptions = {},
): SeatEffectMap {
  const map: SeatEffectMap = {};
  const showNightEffects = currentPhase?.startsWith('NIGHT') ?? false;
  const nowMs = options.nowMs ?? Number.POSITIVE_INFINITY;
  for (const effect of effects) {
    const seatState = (map[effect.target_seat] ??= {});
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    if (effect.kind === 'guard_shield') {
      seatState.guardShield = showNightEffects || within(ageMs, FAST_PHASE_GRACE_MS);
    } else if (effect.kind === 'wolf_attack') {
      const blocked = effect.meta.blocked_by_guard === true;
      const durationMs = Math.max(300, effect.duration_ms || 3000);
      seatState.wolfAttack = blocked
        ? within(ageMs, durationMs + 250)
        : showNightEffects || within(ageMs, FAST_PHASE_GRACE_MS);
      seatState.wolfAttackBlocked = blocked;
    } else if (effect.kind === 'seer_vision') {
      const durationMs = Math.max(300, effect.duration_ms || 1800);
      if (within(ageMs, durationMs)) {
        seatState.seerVisionSeq = effect.seq;
      }
    } else if (effect.kind === 'death_reveal') {
      seatState.outBadge = true;
    }
  }
  return map;
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
