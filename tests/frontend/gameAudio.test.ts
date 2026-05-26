import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  GAME_AUDIO_MUTED_KEY,
  GAME_AUDIO_VOLUME_KEY,
  gameAudio,
  readInitialGameAudioSnapshot,
} from '../../src/lib/gameAudio';

describe('gameAudio', () => {
  afterEach(() => {
    gameAudio.stopAll();
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
});

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
