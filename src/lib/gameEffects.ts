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
export type EffectAnnouncement = {
  id: string;
  seq: number;
  kind: SpectatorEffect['kind'];
  assetKey: string;
  text: string;
  targetSeat: number;
};
export type RecentSpectatorEffect = {
  id: string;
  effect: SpectatorEffect;
  seenAtMs: number;
};

type BuildSeatEffectOptions = {
  currentDay?: number | null;
  nowMs?: number;
  seenAtByKey?: EffectSeenAtMap;
};

const GUARD_SETTLE_GRACE_MS = 3000;
const WOLF_ATTACK_MS = 4000;
const SEER_VISION_MS = 3500;
const POTION_EFFECT_MS = 3000;
const EFFECT_ANNOUNCEMENT_MS = 8000;

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
  const terminal = isTerminalEffectPhase(currentPhase);
  for (const effect of effects) {
    const seatState = (map[effect.target_seat] ??= {});
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    if (effect.kind === 'death_reveal') {
      seatState.outBadge = true;
      seatState.outBadgeSeq = Math.max(seatState.outBadgeSeq ?? 0, effect.seq);
    } else if (terminal) {
      continue;
    } else if (effect.kind === 'guard_shield') {
      if (isGuardShieldActive(effect, currentPhase, currentDay, ageMs, options.seenAtByKey)) {
        seatState.guardShield = true;
        seatState.guardShieldSeq = effect.seq;
      }
    } else if (effect.kind === 'wolf_attack') {
      const blocked = effect.meta.blocked_by_guard === true;
      const durationMs = effectDisplayDurationMs(effect);
      if (
        isShortEffectActive(
          effect,
          currentPhase,
          currentDay,
          ageMs,
          durationMs,
          options.seenAtByKey,
        )
      ) {
        seatState.wolfAttack = true;
        seatState.wolfAttackSeq = effect.seq;
        seatState.wolfAttackBlocked = blocked;
      }
    } else if (effect.kind === 'seer_vision') {
      const durationMs = effectDisplayDurationMs(effect);
      if (
        isShortEffectActive(
          effect,
          currentPhase,
          currentDay,
          ageMs,
          durationMs,
          options.seenAtByKey,
        )
      ) {
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
  if (isTerminalEffectPhase(currentPhase)) {
    return [];
  }
  return effects.filter((effect) => {
    if (effect.kind !== 'witch_potion' || !isWitchPotionAction(effect)) {
      return false;
    }
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    const durationMs = effectDisplayDurationMs(effect);
    return isShortEffectActive(
      effect,
      currentPhase,
      currentDay,
      ageMs,
      durationMs,
      options.seenAtByKey,
    );
  });
}

export function activeEffectAnnouncements(
  effects: SpectatorEffect[],
  currentPhase: string | null,
  options: BuildSeatEffectOptions = {},
): EffectAnnouncement[] {
  const currentDay = options.currentDay ?? latestEffectDay(effects);
  const nowMs = options.nowMs ?? Number.POSITIVE_INFINITY;
  if (isTerminalEffectPhase(currentPhase)) {
    return [];
  }
  const announcements: EffectAnnouncement[] = [];
  for (const effect of effects) {
    const label = effectAnnouncementText(effect);
    if (!label) {
      continue;
    }
    const ageMs = effectAgeMs(effect, options.seenAtByKey, nowMs);
    const active = isEffectAnnouncementActive(
      effect,
      currentPhase,
      currentDay,
      ageMs,
      options.seenAtByKey,
    );
    if (!active) {
      continue;
    }
    announcements.push({
      id: effectIdentity(effect),
      seq: effect.seq,
      kind: effect.kind,
      assetKey: effect.asset_key,
      text: label,
      targetSeat: effect.target_seat,
    });
  }
  return announcements;
}

export function seedExpiredEffectSeenAt(
  effects: SpectatorEffect[],
  seenAtByKey: EffectSeenAtMap,
  nowMs: number,
) {
  for (const effect of effects) {
    if (effect.kind === 'death_reveal') {
      continue;
    }
    const key = effectIdentity(effect);
    if (!(key in seenAtByKey)) {
      seenAtByKey[key] =
        nowMs -
        Math.max(effectDisplayDurationMs(effect), effectAnnouncementDurationMs(effect)) -
        1;
    }
  }
}

export function expireTransientEffectSeenAt(
  effects: SpectatorEffect[],
  seenAtByKey: EffectSeenAtMap,
  nowMs: number,
) {
  for (const effect of effects) {
    if (effect.kind === 'death_reveal') {
      continue;
    }
    seenAtByKey[effectIdentity(effect)] =
      nowMs -
      Math.max(effectDisplayDurationMs(effect), effectAnnouncementDurationMs(effect)) -
      1;
  }
}

export function appendUniqueSpectatorEffects(
  current: SpectatorEffect[],
  incoming: SpectatorEffect[],
) {
  if (incoming.length === 0) {
    return current;
  }
  const seen = new Set(current.map(effectIdentity));
  const next = [...current];
  for (const effect of incoming) {
    const key = effectIdentity(effect);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    next.push(effect);
  }
  return next.length === current.length ? current : next;
}

export function appendRecentSpectatorEffects(
  current: RecentSpectatorEffect[],
  incoming: SpectatorEffect[],
  nowMs: number,
) {
  if (incoming.length === 0) {
    return current;
  }
  const next = pruneRecentSpectatorEffects(current, nowMs);
  const seen = new Set(next.map((item) => item.id));
  for (const effect of incoming) {
    if (effect.kind === 'death_reveal' || !effectAnnouncementText(effect)) {
      continue;
    }
    const id = effectIdentity(effect);
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    next.push({ id, effect, seenAtMs: nowMs });
  }
  const limited = next.slice(-24);
  return limited.length === current.length &&
    limited.every((item, index) => item === current[index])
    ? current
    : limited;
}

export function pruneRecentSpectatorEffects(
  current: RecentSpectatorEffect[],
  nowMs: number,
) {
  return current.filter((item) =>
    within(nowMs - item.seenAtMs, effectAnnouncementDurationMs(item.effect)),
  );
}

export function activeRecentEffectAnnouncements(
  recentEffects: RecentSpectatorEffect[],
  nowMs: number,
  options: { terminal?: boolean } = {},
): EffectAnnouncement[] {
  if (options.terminal) {
    return [];
  }
  const announcements: EffectAnnouncement[] = [];
  for (const item of recentEffects) {
    const label = effectAnnouncementText(item.effect);
    if (!label) {
      continue;
    }
    if (!within(nowMs - item.seenAtMs, effectAnnouncementDurationMs(item.effect))) {
      continue;
    }
    announcements.push({
      id: item.id,
      seq: item.effect.seq,
      kind: item.effect.kind,
      assetKey: item.effect.asset_key,
      text: label,
      targetSeat: item.effect.target_seat,
    });
  }
  return announcements;
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
  seenAtByKey?: EffectSeenAtMap,
) {
  if (!isSameDay(effect, currentDay)) {
    return hasEffectSeenAt(effect, seenAtByKey)
      ? within(ageMs, effectDisplayDurationMs(effect))
      : false;
  }
  const currentOrder = phaseOrder(currentPhase);
  if (currentOrder === null) {
    return hasEffectSeenAt(effect, seenAtByKey)
      ? within(ageMs, effectDisplayDurationMs(effect))
      : false;
  }
  const effectOrder = phaseOrder(effect.phase) ?? PHASE_ORDER.NIGHT_GUARD;
  if (currentOrder >= effectOrder && currentOrder <= PHASE_ORDER.NIGHT_RESOLVE) {
    return true;
  }
  if (hasEffectSeenAt(effect, seenAtByKey)) {
    return within(ageMs, effectDisplayDurationMs(effect));
  }
  return false;
}

function isShortEffectActive(
  effect: SpectatorEffect,
  currentPhase: string | null,
  currentDay: number | null,
  ageMs: number,
  durationMs: number,
  seenAtByKey?: EffectSeenAtMap,
) {
  if (!within(ageMs, durationMs)) {
    return false;
  }
  if (hasEffectSeenAt(effect, seenAtByKey)) {
    return true;
  }
  if (!isSameDay(effect, currentDay)) {
    return false;
  }
  const currentOrder = phaseOrder(currentPhase);
  if (currentOrder === null) {
    return true;
  }
  const effectOrder = phaseOrder(effect.phase) ?? currentOrder;
  return currentOrder >= effectOrder;
}

export function effectDisplayDurationMs(effect: SpectatorEffect) {
  if (effect.kind === 'guard_shield') {
    return Math.max(GUARD_SETTLE_GRACE_MS, effect.duration_ms || 0);
  }
  if (effect.kind === 'wolf_attack') {
    return Math.max(WOLF_ATTACK_MS, effect.duration_ms || 0);
  }
  if (effect.kind === 'seer_vision') {
    return Math.max(SEER_VISION_MS, effect.duration_ms || 0);
  }
  if (effect.kind === 'witch_potion') {
    return Math.max(POTION_EFFECT_MS, effect.duration_ms || 0);
  }
  return 0;
}

export function effectAnnouncementDurationMs(effect: SpectatorEffect) {
  if (effect.kind === 'death_reveal') {
    return 0;
  }
  return Math.max(EFFECT_ANNOUNCEMENT_MS, effectDisplayDurationMs(effect));
}

function isEffectAnnouncementActive(
  effect: SpectatorEffect,
  currentPhase: string | null,
  currentDay: number | null,
  ageMs: number,
  seenAtByKey?: EffectSeenAtMap,
) {
  if (effect.kind === 'death_reveal') {
    return false;
  }
  const durationMs = effectAnnouncementDurationMs(effect);
  if (hasEffectSeenAt(effect, seenAtByKey)) {
    return within(ageMs, durationMs);
  }
  if (effect.kind === 'guard_shield') {
    return isGuardShieldActive(effect, currentPhase, currentDay, ageMs, seenAtByKey);
  }
  return isShortEffectActive(
    effect,
    currentPhase,
    currentDay,
    ageMs,
    durationMs,
    seenAtByKey,
  );
}

function effectAnnouncementText(effect: SpectatorEffect) {
  if (effect.kind === 'guard_shield') {
    return `守卫护盾：${effect.target_seat}号`;
  }
  if (effect.kind === 'wolf_attack') {
    return `狼人袭击：${effect.target_seat}号`;
  }
  if (effect.kind === 'seer_vision') {
    return `预言查验：${effect.target_seat}号`;
  }
  if (effect.kind === 'witch_potion') {
    if (isWitchPotionAction(effect) && effect.meta.action === 'save') {
      return `女巫解药：${effect.target_seat}号`;
    }
    if (isWitchPotionAction(effect) && effect.meta.action === 'poison') {
      return `女巫毒药：${effect.target_seat}号`;
    }
  }
  return '';
}

function isWitchPotionAction(effect: SpectatorEffect) {
  return effect.meta.action === 'save' || effect.meta.action === 'poison';
}

function hasEffectSeenAt(
  effect: SpectatorEffect,
  seenAtByKey: EffectSeenAtMap | undefined,
) {
  return seenAtByKey !== undefined && effectIdentity(effect) in seenAtByKey;
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

function isTerminalEffectPhase(phase: string | null) {
  return phase === 'GAME_END';
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
