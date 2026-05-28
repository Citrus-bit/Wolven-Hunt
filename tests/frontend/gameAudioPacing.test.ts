import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createGameAudioPacingRuntime } from '../../src/hooks/useGameAudioPacing';
import { gameAudio } from '../../src/lib/gameAudio';
import type { GameEvent } from '../../src/lib/gameApi';

describe('game audio pacing runtime', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('does not replay events at or before the restored stream cursor', async () => {
    const playSequence = vi
      .spyOn(gameAudio, 'playSequence')
      .mockResolvedValue(undefined);
    vi.spyOn(gameAudio, 'stopAll').mockImplementation(() => undefined);
    const runtime = createGameAudioPacingRuntime({
      gameId: 'game-1',
      eventsRef: { current: [] },
      audioDayRef: { current: 1 },
      terminalRef: { current: false },
      initialStreamCursorRef: { current: 10 },
    });

    runtime.enqueueAudioTrigger(dayAnnounce(10));
    runtime.enqueueAudioTrigger(dayAnnounce(11));
    await flushPromises();

    expect(playSequence).toHaveBeenCalledTimes(1);
    expect(playSequence).toHaveBeenCalledWith(['day_peaceful'], 0);
  });

  it('dedupes live event audio and seeds reset with already-played seqs', async () => {
    const playSequence = vi
      .spyOn(gameAudio, 'playSequence')
      .mockResolvedValue(undefined);
    vi.spyOn(gameAudio, 'stopAll').mockImplementation(() => undefined);
    const runtime = createGameAudioPacingRuntime({
      gameId: 'game-1',
      eventsRef: { current: [] },
      audioDayRef: { current: 1 },
      terminalRef: { current: false },
      initialStreamCursorRef: { current: 0 },
    });

    runtime.resetAudioPacing(3);
    runtime.enqueueAudioTrigger(dayAnnounce(3));
    runtime.enqueueAudioTrigger(dayAnnounce(4));
    runtime.enqueueAudioTrigger(dayAnnounce(4));
    await flushPromises();

    expect(playSequence).toHaveBeenCalledTimes(1);
    expect(playSequence).toHaveBeenCalledWith(['day_peaceful'], 0);
  });

  it('sends phase ack immediately when game audio is muted', async () => {
    const sendAck = vi.fn().mockResolvedValue({ ok: true });
    const playSequence = vi
      .spyOn(gameAudio, 'playSequence')
      .mockResolvedValue(undefined);
    vi.spyOn(gameAudio, 'stopAll').mockImplementation(() => undefined);
    vi.spyOn(gameAudio, 'getSnapshot').mockReturnValue({
      muted: true,
      unlocked: true,
      volume: 0.8,
      playError: null,
    });
    const runtime = createGameAudioPacingRuntime({
      gameId: 'game-1',
      eventsRef: { current: [] },
      audioDayRef: { current: 1 },
      terminalRef: { current: false },
      initialStreamCursorRef: { current: 0 },
      sendAck,
    });

    runtime.enqueueAudioTrigger(phaseEnter(2, 'NIGHT_GUARD'));
    await flushPromises();

    expect(playSequence).not.toHaveBeenCalled();
    expect(sendAck).toHaveBeenCalledWith('game-1', 'NIGHT_GUARD', 'night_guard_done');
  });

  it('sends phase ack after audio playback failure', async () => {
    const sendAck = vi.fn().mockResolvedValue({ ok: true });
    vi.spyOn(gameAudio, 'playSequence').mockRejectedValue(new Error('blocked'));
    vi.spyOn(gameAudio, 'stopAll').mockImplementation(() => undefined);
    vi.spyOn(gameAudio, 'getSnapshot').mockReturnValue({
      muted: false,
      unlocked: false,
      volume: 0.8,
      playError: 'blocked',
    });
    const runtime = createGameAudioPacingRuntime({
      gameId: 'game-1',
      eventsRef: { current: [] },
      audioDayRef: { current: 1 },
      terminalRef: { current: false },
      initialStreamCursorRef: { current: 0 },
      sendAck,
    });

    runtime.enqueueAudioTrigger(phaseEnter(2, 'NIGHT_GUARD'));
    await flushPromises();

    expect(sendAck).toHaveBeenCalledWith('game-1', 'NIGHT_GUARD', 'night_guard_done');
  });
});

function dayAnnounce(seq: number): GameEvent {
  return {
    seq,
    day: 1,
    phase: 'DAY_ANNOUNCE',
    type: 'day_announce',
    actor: null,
    payload: { deaths: [], message: '昨晚是平安夜' },
  };
}

function phaseEnter(seq: number, phase: string): GameEvent {
  return {
    seq,
    day: 1,
    phase,
    type: 'phase_enter',
    actor: null,
    payload: { phase },
  };
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}
