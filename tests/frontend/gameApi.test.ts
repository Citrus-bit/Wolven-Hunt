import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  checkHealth,
  createGame,
  generateReviewReport,
  getReviewReport,
  parseEventSourceCursor,
  pauseGame,
  runGame,
  subscribeGameEvents,
} from '../../src/lib/gameApi';

describe('gameApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates live spectator games paused until the stream is mounted', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ game_id: 'game-1' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      createGame({
        agents: { 1: 'llm:mock' },
        pacing: 'live',
        startPaused: true,
      }),
    ).resolves.toEqual({ game_id: 'game-1' });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/games');
    expect(JSON.parse(String(init.body))).toMatchObject({
      pacing: 'live',
      start_paused: true,
      agents: { 1: 'llm:mock' },
      evolution_enabled: false,
    });
  });

  it('sends prompt evolution preference when creating games', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ game_id: 'game-1' }));
    vi.stubGlobal('fetch', fetchMock);

    await createGame({ evolutionEnabled: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      evolution_enabled: true,
    });
  });

  it('checks backend health without throwing on unavailable service', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ ok: false }))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(checkHealth()).resolves.toBe(true);
    await expect(checkHealth()).resolves.toBe(false);
    await expect(checkHealth()).resolves.toBe(false);

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/healthz', {
      method: 'GET',
      cache: 'no-store',
    });
  });

  it('starts a paused game through the run endpoint', async () => {
    const summary = {
      game_id: 'game-1',
      status: 'running',
      winner: null,
      day: 1,
      phase: 'NIGHT_START',
      event_count: 1,
      timings: {},
      seat_presentation: {},
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(summary));
    vi.stubGlobal('fetch', fetchMock);

    await expect(runGame('game-1')).resolves.toEqual(summary);

    expect(fetchMock).toHaveBeenCalledWith('/games/game-1/run', { method: 'POST' });
  });

  it('notifies stream readiness from EventSource open and stream_ready frames', () => {
    const sourceClass = fakeEventSourceClass();
    vi.stubGlobal('EventSource', sourceClass);
    const onOpen = vi.fn();
    const onReady = vi.fn();
    const onEvent = vi.fn();
    const onError = vi.fn();

    subscribeGameEvents('game-1', onOpen, onReady, onEvent, onError);
    const source = sourceClass.instances[0];
    source.onopen?.();
    source.emit('stream_ready', '{}');
    source.emit(
      'game_event',
      JSON.stringify({
        seq: 1,
        day: 1,
        phase: 'GAME_START',
        type: 'game_start',
        actor: null,
        payload: {},
      }),
    );

    expect(source.url).toBe('/games/game-1/stream');
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onReady).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenCalledWith(
      {
        seq: 1,
        day: 1,
        phase: 'GAME_START',
        type: 'game_start',
        actor: null,
        payload: {},
      },
      null,
    );
  });

  it('passes EventSource lastEventId as the raw stream cursor for projections', () => {
    const sourceClass = fakeEventSourceClass();
    vi.stubGlobal('EventSource', sourceClass);
    const onEvent = vi.fn();
    const onNarrative = vi.fn();
    const onEffect = vi.fn();

    subscribeGameEvents(
      'game-1',
      vi.fn(),
      vi.fn(),
      onEvent,
      vi.fn(),
      onNarrative,
      onEffect,
      5,
    );
    const source = sourceClass.instances[0];

    expect(source.url).toBe('/games/game-1/stream?last_event_id=5');
    source.emit(
      'narrative_row',
      JSON.stringify({
        seq: 8,
        day: 1,
        phase: 'NIGHT_GUARD',
        kind: 'action',
        text: '守卫行动',
        actor: 4,
        icon: null,
      }),
      '7',
    );
    source.emit(
      'spectator_effect',
      JSON.stringify({
        seq: 9,
        day: 1,
        phase: 'NIGHT_GUARD',
        kind: 'guard_shield',
        actor: 4,
        source_seat: 4,
        target_seat: 2,
        asset_key: 'guard_shield',
        duration_ms: 1000,
        meta: {},
      }),
      '9',
    );

    expect(onNarrative).toHaveBeenCalledWith(expect.objectContaining({ seq: 8 }), 7);
    expect(onEffect).toHaveBeenCalledWith(expect.objectContaining({ seq: 9 }), 9);
  });

  it('parses only positive integer EventSource cursors', () => {
    expect(parseEventSourceCursor('12')).toBe(12);
    expect(parseEventSourceCursor('')).toBeNull();
    expect(parseEventSourceCursor('0')).toBeNull();
    expect(parseEventSourceCursor('abc')).toBeNull();
  });

  it('pauses a live game through the pause endpoint', async () => {
    const summary = {
      game_id: 'game-1',
      status: 'paused',
      winner: null,
      day: 1,
      phase: 'NIGHT_START',
      event_count: 1,
      timings: {},
      seat_presentation: {},
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(summary));
    vi.stubGlobal('fetch', fetchMock);

    await expect(pauseGame('game-1')).resolves.toEqual(summary);

    expect(fetchMock).toHaveBeenCalledWith('/games/game-1/pause', { method: 'POST' });
  });

  it('uses review report endpoints for reading and generation', async () => {
    const report = {
      schema_version: '1.1',
      game_id: 'game-1',
      generated_at: '2026-01-01T00:00:00Z',
      generation_mode: 'offline_mock',
      summary: {
        winner: 'good',
        verdict: '好人胜利',
        turning_points: [],
        overall_assessment: '公开信息复盘。',
      },
      leaderboard: [],
      players: [],
      key_decisions: [],
      counterfactuals: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(report));
    vi.stubGlobal('fetch', fetchMock);

    await expect(getReviewReport('game-1')).resolves.toEqual(report);
    await expect(generateReviewReport('game-1')).resolves.toEqual(report);

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/games/game-1/review-report');
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/games/game-1/review-report', {
      method: 'POST',
    });
  });
});

function jsonResponse(data: unknown) {
  return {
    ok: true,
    json: async () => data,
  } as Response;
}

function fakeEventSourceClass() {
  class FakeEventSource {
    static instances: FakeEventSource[] = [];
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private listeners = new Map<string, ((message: MessageEvent<string>) => void)[]>();

    constructor(public url: string) {
      FakeEventSource.instances.push(this);
    }

    addEventListener(
      event: string,
      listener: (message: MessageEvent<string>) => void,
    ) {
      this.listeners.set(event, [...(this.listeners.get(event) ?? []), listener]);
    }

    emit(event: string, data: string, lastEventId = '') {
      for (const listener of this.listeners.get(event) ?? []) {
        listener({ data, lastEventId } as MessageEvent<string>);
      }
    }

    close() {
      return undefined;
    }
  }

  return FakeEventSource;
}
