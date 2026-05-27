import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GAME_AUDIO_MUTED_KEY,
  GAME_AUDIO_VOLUME_KEY,
  gameAudio,
  readInitialGameAudioSnapshot,
} from '../../src/lib/gameAudio';

describe('gameAudio', () => {
  beforeEach(() => {
    resetGameAudioElements();
  });

  afterEach(() => {
    gameAudio.stopAll();
    resetGameAudioElements();
    vi.unstubAllGlobals();
  });

  it('defaults game voice to audible and independent from lobby muted state', () => {
    const snapshot = readInitialGameAudioSnapshot({
      getItem: (key) => (key === 'wolven_hunt.lobby.muted' ? 'true' : null),
    });

    expect(snapshot.muted).toBe(false);
    expect(snapshot.volume).toBe(0.8);
  });

  it('hydrates the dedicated game audio localStorage keys', () => {
    const snapshot = readInitialGameAudioSnapshot({
      getItem: (key) => {
        if (key === GAME_AUDIO_MUTED_KEY) {
          return 'true';
        }
        if (key === GAME_AUDIO_VOLUME_KEY) {
          return '35';
        }
        return null;
      },
    });

    expect(snapshot.muted).toBe(true);
    expect(snapshot.volume).toBe(0.35);
  });

  it('stops only the requested audio keys', () => {
    const elements: FakeAudioElement[] = [];
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => null,
        setItem: () => undefined,
      },
    });
    vi.stubGlobal(
      'Audio',
      class extends FakeAudioElement {
        constructor(src: string) {
          super(src);
          elements.push(this);
        }
      },
    );

    gameAudio.preload();
    const death = elements.find((element) => element.src.includes('day_death'));
    const peaceful = elements.find((element) =>
      element.src.includes('day_peaceful'),
    );
    const dawn = elements.find((element) => element.src.includes('day_dawn'));

    expect(death).toBeDefined();
    expect(peaceful).toBeDefined();
    expect(dawn).toBeDefined();

    for (const element of [death, peaceful, dawn]) {
      element!.paused = false;
      element!.currentTime = 12;
    }

    gameAudio.stopKeys(['day_death', 'day_peaceful']);

    expect(death!.paused).toBe(true);
    expect(death!.currentTime).toBe(0);
    expect(peaceful!.paused).toBe(true);
    expect(peaceful!.currentTime).toBe(0);
    expect(dawn!.paused).toBe(false);
    expect(dawn!.currentTime).toBe(12);
  });

  it('preloads host speech, vote, and last words voices', () => {
    const elements: FakeAudioElement[] = [];
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => null,
        setItem: () => undefined,
      },
    });
    vi.stubGlobal(
      'Audio',
      class extends FakeAudioElement {
        constructor(src: string) {
          super(src);
          elements.push(this);
        }
      },
    );

    gameAudio.preload();

    expect(elements.some((element) => element.src.includes('speech_seat_1'))).toBe(true);
    expect(elements.some((element) => element.src.includes('speech_seat_10'))).toBe(true);
    expect(elements.some((element) => element.src.includes('day_vote_start'))).toBe(true);
    expect(elements.some((element) =>
      element.src.includes('day_last_words_start'),
    )).toBe(true);
  });

  it('waits for one audio element to end before starting the next sequence item', async () => {
    const elements: ControllableAudioElement[] = [];
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => null,
        setItem: () => undefined,
      },
      setTimeout: () => 1,
      clearTimeout: () => undefined,
    });
    vi.stubGlobal(
      'Audio',
      class extends ControllableAudioElement {
        constructor(src: string) {
          super(src);
          elements.push(this);
        }
      },
    );

    const playing = gameAudio.playSequence(
      ['speech_seat_1', 'day_vote_start'],
      0,
    );
    await Promise.resolve();

    const speech = elements.find((element) =>
      element.src.includes('speech_seat_1'),
    );

    expect(speech?.playCalls).toBe(1);
    expect(elements.some((element) =>
      element.src.includes('day_vote_start'),
    )).toBe(false);

    speech?.emit('ended');
    await flushPromises();

    const vote = elements.find((element) =>
      element.src.includes('day_vote_start'),
    );
    expect(vote?.playCalls).toBe(1);

    vote?.emit('ended');
    await expect(playing).resolves.toBeUndefined();
  });
});

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}

function resetGameAudioElements() {
  (gameAudio as unknown as { elements: Map<string, unknown> }).elements.clear();
}

class FakeAudioElement {
  currentTime = 0;
  muted = false;
  paused = true;
  preload = '';
  volume = 0.8;

  constructor(readonly src: string) {}

  load() {}

  pause() {
    this.paused = true;
  }

  play() {
    this.paused = false;
    return Promise.resolve();
  }

  addEventListener() {}

  removeEventListener() {}
}

class ControllableAudioElement extends FakeAudioElement {
  playCalls = 0;
  private listeners = new Map<string, Set<() => void>>();

  override play() {
    this.playCalls += 1;
    this.paused = false;
    return Promise.resolve();
  }

  override addEventListener(type: string, listener: () => void) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  override removeEventListener(type: string, listener: () => void) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener();
    }
  }
}
