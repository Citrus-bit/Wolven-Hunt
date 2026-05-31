import type { LaunchState } from './gameLaunchState';
import type { HumanRole, SpectatorEffect } from './gameApi';
import type { RecentSpectatorEffect } from './gameEffects';
import {
  normalizeHumanIdentityMarks,
  type HumanIdentityMarks,
} from './identityMarks';
import type { SeatPresentationMap } from './seatPresentation';

export const LIVE_GAME_SESSION_KEY = 'wolven_hunt.live_session';
const BLOCKED_LIVE_GAME_IDS_KEY = 'wolven_hunt.live_session.blocked_ids';
const MAX_BLOCKED_LIVE_GAME_IDS = 24;

export type LiveGameSessionSnapshot = {
  gameId: string;
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  launchState: LaunchState;
  streamCursor: number;
  effectSeq: number;
  recentEffects: RecentSpectatorEffect[];
  humanSeat?: number | null;
  playerToken?: string | null;
  humanRole?: HumanRole;
  humanIdentityMarks?: HumanIdentityMarks;
  savedAtMs: number;
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function readLiveGameSession(
  storage = browserStorage(),
): LiveGameSessionSnapshot | null {
  if (!storage) {
    return null;
  }
  try {
    const raw = storage.getItem(LIVE_GAME_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const snapshot = parseLiveGameSession(raw);
    if (snapshot && isLiveGameSessionBlocked(snapshot.gameId, storage)) {
      storage.removeItem(LIVE_GAME_SESSION_KEY);
      return null;
    }
    return snapshot;
  } catch (error) {
    console.warn('[game] failed to read live session snapshot', error);
    return null;
  }
}

export function writeLiveGameSession(
  snapshot: Omit<LiveGameSessionSnapshot, 'savedAtMs'>,
  storage = browserStorage(),
) {
  if (!storage) {
    return;
  }
  try {
    if (isLiveGameSessionBlocked(snapshot.gameId, storage)) {
      return;
    }
    storage.setItem(
      LIVE_GAME_SESSION_KEY,
      JSON.stringify({ ...snapshot, savedAtMs: Date.now() }),
    );
  } catch (error) {
    console.warn('[game] failed to write live session snapshot', error);
  }
}

export function clearLiveGameSession(
  gameId?: string | null,
  storage = browserStorage(),
) {
  if (!storage) {
    return;
  }
  try {
    if (!gameId) {
      storage.removeItem(LIVE_GAME_SESSION_KEY);
      return;
    }
    const snapshot = readLiveGameSession(storage);
    if (!snapshot || snapshot.gameId === gameId) {
      storage.removeItem(LIVE_GAME_SESSION_KEY);
      blockLiveGameSession(gameId, storage);
    }
  } catch (error) {
    console.warn('[game] failed to clear live session snapshot', error);
  }
}

function blockLiveGameSession(gameId: string, storage: StorageLike) {
  const blocked = [
    gameId,
    ...readBlockedLiveGameIds(storage).filter((item) => item !== gameId),
  ].slice(0, MAX_BLOCKED_LIVE_GAME_IDS);
  storage.setItem(BLOCKED_LIVE_GAME_IDS_KEY, JSON.stringify(blocked));
}

function isLiveGameSessionBlocked(gameId: string, storage: StorageLike) {
  return readBlockedLiveGameIds(storage).includes(gameId);
}

function readBlockedLiveGameIds(storage: StorageLike): string[] {
  try {
    const raw = storage.getItem(BLOCKED_LIVE_GAME_IDS_KEY);
    if (!raw) {
      return [];
    }
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) {
      return [];
    }
    return value.filter((item): item is string => typeof item === 'string');
  } catch {
    return [];
  }
}

function parseLiveGameSession(raw: string): LiveGameSessionSnapshot | null {
  const value = JSON.parse(raw) as Partial<LiveGameSessionSnapshot>;
  if (
    typeof value.gameId !== 'string' ||
    !Array.isArray(value.assignments) ||
    value.assignments.length !== 10 ||
    !isLaunchState(value.launchState)
  ) {
    return null;
  }
  const assignments = value.assignments.map((item) =>
    Number.isInteger(item) && Number(item) >= 0 && Number(item) < 10
      ? Number(item)
      : null,
  );
  return {
    gameId: value.gameId,
    assignments,
    seatPresentation: normalizeSeatPresentation(value.seatPresentation),
    launchState: value.launchState,
    streamCursor: normalizeNonNegativeInt(value.streamCursor),
    effectSeq: normalizeNonNegativeInt(value.effectSeq),
    recentEffects: normalizeRecentEffects(value.recentEffects),
    humanSeat: normalizeSeat(value.humanSeat),
    playerToken: typeof value.playerToken === 'string' ? value.playerToken : null,
    humanRole: isHumanRole(value.humanRole) ? value.humanRole : 'random',
    humanIdentityMarks: normalizeHumanIdentityMarks(value.humanIdentityMarks),
    savedAtMs: Number(value.savedAtMs) || 0,
  };
}

function normalizeSeat(value: unknown) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 1 && number <= 10 ? number : null;
}

function normalizeNonNegativeInt(value: unknown) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : 0;
}

function normalizeRecentEffects(value: unknown): RecentSpectatorEffect[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const effects: RecentSpectatorEffect[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      continue;
    }
    const id = 'id' in item ? item.id : null;
    const rawSeenAtMs = 'seenAtMs' in item ? Number(item.seenAtMs) : NaN;
    const effect = 'effect' in item ? normalizeSpectatorEffect(item.effect) : null;
    if (
      typeof id !== 'string' ||
      !Number.isFinite(rawSeenAtMs) ||
      rawSeenAtMs <= 0 ||
      !effect
    ) {
      continue;
    }
    effects.push({ id, effect, seenAtMs: rawSeenAtMs });
  }
  return effects.slice(-24);
}

function normalizeSpectatorEffect(value: unknown): SpectatorEffect | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Partial<SpectatorEffect>;
  if (
    !Number.isInteger(record.seq) ||
    !Number.isInteger(record.day) ||
    typeof record.phase !== 'string' ||
    !isSpectatorEffectKind(record.kind) ||
    !Number.isInteger(record.target_seat) ||
    typeof record.asset_key !== 'string'
  ) {
    return null;
  }
  const seq = Number(record.seq);
  const day = Number(record.day);
  const targetSeat = Number(record.target_seat);
  const actor = record.actor === null || Number.isInteger(record.actor)
    ? record.actor ?? null
    : null;
  const sourceSeat =
    record.source_seat === null || Number.isInteger(record.source_seat)
      ? record.source_seat ?? null
      : null;
  return {
    seq,
    day,
    phase: record.phase,
    kind: record.kind,
    actor,
    source_seat: sourceSeat,
    target_seat: targetSeat,
    asset_key: record.asset_key,
    duration_ms: Number(record.duration_ms) || 0,
    meta:
      record.meta && typeof record.meta === 'object' && !Array.isArray(record.meta)
        ? record.meta
        : {},
  };
}

function normalizeSeatPresentation(value: unknown): SeatPresentationMap {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  const presentation: SeatPresentationMap = {};
  for (const [seat, item] of Object.entries(value)) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      continue;
    }
    const nickname = 'nickname' in item ? item.nickname : null;
    const iconPath = 'icon_path' in item ? item.icon_path : null;
    if (typeof nickname === 'string' && typeof iconPath === 'string') {
      presentation[Number(seat)] = { nickname, icon_path: iconPath };
    }
  }
  return presentation;
}

function isLaunchState(value: unknown): value is LaunchState {
  return (
    value === 'idle' ||
    value === 'connecting_service' ||
    value === 'creating' ||
    value === 'connecting_stream' ||
    value === 'starting_backend' ||
    value === 'running' ||
    value === 'failed'
  );
}

function isSpectatorEffectKind(value: unknown): value is SpectatorEffect['kind'] {
  return (
    value === 'guard_shield' ||
    value === 'wolf_attack' ||
    value === 'seer_vision' ||
    value === 'witch_potion' ||
    value === 'death_reveal'
  );
}

function isHumanRole(value: unknown): value is HumanRole {
  return (
    value === 'villager' ||
    value === 'witch' ||
    value === 'seer' ||
    value === 'guard' ||
    value === 'wolf' ||
    value === 'random'
  );
}

function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}
