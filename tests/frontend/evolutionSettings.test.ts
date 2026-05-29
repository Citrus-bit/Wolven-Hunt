import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  PROMPT_EVOLUTION_STORAGE_KEY,
  readPromptEvolutionEnabled,
} from '../../src/lib/evolutionSettings';

describe('evolutionSettings', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the prompt evolution toggle from localStorage', () => {
    const storage = new Map<string, string>();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
      },
    });

    expect(readPromptEvolutionEnabled()).toBe(false);
    storage.set(PROMPT_EVOLUTION_STORAGE_KEY, 'true');
    expect(readPromptEvolutionEnabled()).toBe(true);
  });
});
