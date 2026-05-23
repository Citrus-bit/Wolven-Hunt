import { describe, expect, it } from 'vitest';
import {
  GAME_AUDIO_MUTED_KEY,
  GAME_AUDIO_VOLUME_KEY,
  readInitialGameAudioSnapshot,
} from '../../src/lib/gameAudio';

describe('gameAudio', () => {
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
});
