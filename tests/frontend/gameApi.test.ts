import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  checkHealth,
  createGame,
  generateReviewReport,
  getReviewReport,
  runGame,
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
