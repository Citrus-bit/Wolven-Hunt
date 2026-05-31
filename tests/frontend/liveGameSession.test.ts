import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  LIVE_GAME_SESSION_KEY,
  clearLiveGameSession,
  readLiveGameSession,
  writeLiveGameSession,
} from '../../src/lib/liveGameSession';
import type { SpectatorEffect } from '../../src/lib/gameApi';

describe('liveGameSession', () => {
  let storage: MemoryStorage;

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('round-trips a running live game snapshot', () => {
    storage = new MemoryStorage();
    vi.spyOn(Date, 'now').mockReturnValue(12345);

    writeLiveGameSession({
      gameId: 'game-1',
      assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
      seatPresentation: {
        1: { nickname: '海瑟音', icon_path: '/assets/lobby/model_icon_haiseyin.png' },
      },
      launchState: 'running',
      streamCursor: 23,
      effectSeq: 23,
      recentEffects: [
        {
          id: '23:wolf_attack:none:4:wolf_attack',
          effect: effect(23, 'wolf_attack', 4, 'wolf_attack'),
          seenAtMs: 12000,
        },
      ],
    }, storage);

    expect(readLiveGameSession(storage)).toEqual({
      gameId: 'game-1',
      assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
      seatPresentation: {
        1: { nickname: '海瑟音', icon_path: '/assets/lobby/model_icon_haiseyin.png' },
      },
      launchState: 'running',
      streamCursor: 23,
      effectSeq: 23,
      recentEffects: [
        {
          id: '23:wolf_attack:none:4:wolf_attack',
          effect: effect(23, 'wolf_attack', 4, 'wolf_attack'),
          seenAtMs: 12000,
        },
      ],
      humanSeat: null,
      playerToken: null,
      humanRole: 'random',
      humanIdentityMarks: {},
      savedAtMs: 12345,
    });
  });

  it('round-trips human seat stream credentials in the live snapshot', () => {
    storage = new MemoryStorage();

    writeLiveGameSession({
      gameId: 'game-human',
      assignments: [0, 1, null, 3, 4, 5, 6, 7, 8, 9],
      seatPresentation: {
        3: { nickname: '你自己', icon_path: '/assets/lobby/human_player.png' },
      },
      launchState: 'running',
      streamCursor: 12,
      effectSeq: 12,
      recentEffects: [],
      humanSeat: 3,
      playerToken: 'token-123',
      humanRole: 'witch',
      humanIdentityMarks: {
        1: 'wolf',
        6: 'seer',
      },
    }, storage);

    expect(readLiveGameSession(storage)).toMatchObject({
      gameId: 'game-human',
      humanSeat: 3,
      playerToken: 'token-123',
      humanRole: 'witch',
      humanIdentityMarks: {
        1: 'wolf',
        6: 'seer',
      },
    });
  });

  it('filters malformed human identity marks from restored snapshots', () => {
    storage = new MemoryStorage();
    storage.setItem(
      LIVE_GAME_SESSION_KEY,
      JSON.stringify({
        gameId: 'game-human',
        assignments: [0, 1, null, 3, 4, 5, 6, 7, 8, 9],
        seatPresentation: {},
        launchState: 'running',
        humanIdentityMarks: {
          0: 'wolf',
          1: 'wolf',
          4: 'seer',
          11: 'witch',
          bad: 'guard',
          6: 'unknown',
        },
      }),
    );

    expect(readLiveGameSession(storage)?.humanIdentityMarks).toEqual({
      1: 'wolf',
      4: 'seer',
    });
  });

  it('clears only the matching active game snapshot', () => {
    storage = new MemoryStorage();
    writeLiveGameSession({
      gameId: 'game-1',
      assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
      seatPresentation: {},
      launchState: 'running',
      streamCursor: 0,
      effectSeq: 0,
      recentEffects: [],
    }, storage);

    clearLiveGameSession('other-game', storage);
    expect(storage.getItem(LIVE_GAME_SESSION_KEY)).not.toBeNull();

    clearLiveGameSession('game-1', storage);
    expect(storage.getItem(LIVE_GAME_SESSION_KEY)).toBeNull();
  });

  it('does not restore a live game after it has been explicitly cleared', () => {
    storage = new MemoryStorage();
    writeLiveGameSession(snapshot('game-1'), storage);

    clearLiveGameSession('game-1', storage);
    writeLiveGameSession(snapshot('game-1', { streamCursor: 12 }), storage);

    expect(readLiveGameSession(storage)).toBeNull();

    writeLiveGameSession(snapshot('game-2'), storage);
    expect(readLiveGameSession(storage)?.gameId).toBe('game-2');
  });

  it('hydrates old snapshots without cursor or recent effect fields', () => {
    storage = new MemoryStorage();
    storage.setItem(
      LIVE_GAME_SESSION_KEY,
      JSON.stringify({
        gameId: 'game-1',
        assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        seatPresentation: {},
        launchState: 'running',
        savedAtMs: 987,
      }),
    );

    expect(readLiveGameSession(storage)).toMatchObject({
      gameId: 'game-1',
      streamCursor: 0,
      effectSeq: 0,
      recentEffects: [],
      humanSeat: null,
      playerToken: null,
      humanRole: 'random',
      humanIdentityMarks: {},
      savedAtMs: 987,
    });
  });

  it('drops malformed recent effect snapshots', () => {
    storage = new MemoryStorage();
    storage.setItem(
      LIVE_GAME_SESSION_KEY,
      JSON.stringify({
        gameId: 'game-1',
        assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        seatPresentation: {},
        launchState: 'running',
        recentEffects: [
          { id: 'bad', seenAtMs: 0, effect: { seq: 'wrong' } },
          {
            id: 'ok',
            seenAtMs: 1200,
            effect: effect(6, 'guard_shield', 8, 'guard_shield'),
          },
        ],
      }),
    );

    expect(readLiveGameSession(storage)?.recentEffects).toEqual([
      {
        id: 'ok',
        seenAtMs: 1200,
        effect: effect(6, 'guard_shield', 8, 'guard_shield'),
      },
    ]);
  });
});

function effect(
  seq: number,
  kind: SpectatorEffect['kind'],
  target: number,
  assetKey: string,
): SpectatorEffect {
  return {
    seq,
    day: 1,
    phase: 'NIGHT_WOLF_VOTE',
    kind,
    actor: null,
    source_seat: null,
    target_seat: target,
    asset_key: assetKey,
    duration_ms: 0,
    meta: {},
  };
}

function snapshot(
  gameId: string,
  overrides: Partial<Parameters<typeof writeLiveGameSession>[0]> = {},
): Parameters<typeof writeLiveGameSession>[0] {
  return {
    gameId,
    assignments: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    seatPresentation: {},
    launchState: 'running',
    streamCursor: 0,
    effectSeq: 0,
    recentEffects: [],
    ...overrides,
  };
}

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  removeItem(key: string) {
    this.values.delete(key);
  }
}
