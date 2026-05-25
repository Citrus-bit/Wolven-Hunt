import { afterEach, describe, expect, it, vi } from 'vitest';
import { createGame, runGame } from '../../src/lib/gameApi';

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
});

function jsonResponse(data: unknown) {
  return {
    ok: true,
    json: async () => data,
  } as Response;
}
