import { useCallback, useSyncExternalStore } from 'react';
import { gameAudioPath, type GameAudioKey } from './audioAssets';

export type GameAudioSnapshot = {
  muted: boolean;
  unlocked: boolean;
  volume: number;
  playError: string | null;
};

export interface AudioController {
  play(key: GameAudioKey): Promise<void>;
  playSequence(keys: GameAudioKey[], gapMs: number): Promise<void>;
  stopAll(): void;
  setMuted(muted: boolean): void;
  setVolume(v0to1: number): void;
  unlock(): Promise<boolean>;
  preload(): void;
}

type StorageLike = {
  getItem(key: string): string | null;
};

export const GAME_AUDIO_MUTED_KEY = 'wolven_hunt.game.muted';
export const GAME_AUDIO_VOLUME_KEY = 'wolven_hunt.game.volume';

const DEFAULT_SNAPSHOT: GameAudioSnapshot = {
  muted: false,
  unlocked: false,
  volume: 0.8,
  playError: null,
};
const ALL_GAME_AUDIO: GameAudioKey[] = [
  'wolf_howl',
  'night_guard',
  'night_wolves',
  'night_witch',
  'night_seer',
  'day_rooster',
  'day_dawn',
  'day_death',
  'day_peaceful',
];
const PLAY_BLOCKED_MESSAGE = '浏览器阻止了游戏语音，请点击右上角声音按钮';
const listeners = new Set<() => void>();

export function readInitialGameAudioSnapshot(
  storage: StorageLike | null | undefined,
): GameAudioSnapshot {
  const snapshot = { ...DEFAULT_SNAPSHOT };
  if (!storage) {
    return snapshot;
  }
  try {
    const muted = storage.getItem(GAME_AUDIO_MUTED_KEY);
    const volume = storage.getItem(GAME_AUDIO_VOLUME_KEY);
    if (muted !== null) {
      snapshot.muted = muted === 'true';
    }
    if (volume !== null) {
      const parsed = Number(volume);
      if (Number.isFinite(parsed)) {
        snapshot.volume = clampVolume(parsed > 1 ? parsed / 100 : parsed);
      }
    }
  } catch (error) {
    console.warn('[game-audio] failed to read localStorage', error);
  }
  return snapshot;
}

function readBrowserSnapshot() {
  return readInitialGameAudioSnapshot(
    typeof window === 'undefined' ? null : window.localStorage,
  );
}

function writeStoredValue(key: string, value: string) {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn(`[game-audio] failed to write localStorage key=${key}`, error);
  }
}

function clampVolume(value: number) {
  if (!Number.isFinite(value)) {
    return DEFAULT_SNAPSHOT.volume;
  }
  return Math.max(0, Math.min(1, value));
}

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

class BrowserAudioController implements AudioController {
  private elements = new Map<GameAudioKey, HTMLAudioElement>();
  private snapshot = readBrowserSnapshot();

  subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  getSnapshot = () => this.snapshot;

  async unlock(): Promise<boolean> {
    if (typeof window === 'undefined') {
      return true;
    }
    this.preload();
    if (this.snapshot.muted) {
      this.setSnapshot({ unlocked: true, playError: null });
      return true;
    }

    const element = this.elementFor('wolf_howl');
    const previousMuted = element.muted;
    const previousVolume = element.volume;
    element.muted = true;
    element.volume = 0;
    try {
      await element.play();
      element.pause();
      element.currentTime = 0;
      element.muted = this.snapshot.muted;
      element.volume = this.snapshot.volume;
      this.setSnapshot({ unlocked: true, playError: null });
      return true;
    } catch (error) {
      element.muted = previousMuted;
      element.volume = previousVolume;
      this.setSnapshot({ unlocked: false, playError: PLAY_BLOCKED_MESSAGE });
      console.warn('[game-audio] unlock failed', error);
      return false;
    }
  }

  async play(key: GameAudioKey): Promise<void> {
    if (typeof window === 'undefined' || this.snapshot.muted) {
      return;
    }
    const element = this.elementFor(key);
    element.pause();
    element.currentTime = 0;
    element.muted = false;
    element.volume = this.snapshot.volume;

    await new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        element.removeEventListener('ended', done);
        element.removeEventListener('pause', done);
        element.removeEventListener('error', fail);
      };
      const done = () => {
        cleanup();
        this.setSnapshot({ unlocked: true, playError: null });
        resolve();
      };
      const fail = (error?: unknown) => {
        cleanup();
        const reason = error instanceof Error ? error : new Error(PLAY_BLOCKED_MESSAGE);
        this.setSnapshot({ unlocked: false, playError: PLAY_BLOCKED_MESSAGE });
        console.warn(`[game-audio] playback failed key=${key}`, reason);
        reject(reason);
      };
      element.addEventListener('ended', done, { once: true });
      element.addEventListener('pause', done, { once: true });
      element.addEventListener('error', fail, { once: true });
      element.play().catch(fail);
    });
  }

  async playSequence(keys: GameAudioKey[], gapMs: number): Promise<void> {
    for (const key of keys) {
      await this.play(key);
      if (gapMs > 0 && !this.snapshot.muted) {
        await new Promise((resolve) => window.setTimeout(resolve, gapMs));
      }
    }
  }

  stopAll(): void {
    for (const element of this.elements.values()) {
      element.pause();
      element.currentTime = 0;
    }
  }

  setMuted(muted: boolean): void {
    writeStoredValue(GAME_AUDIO_MUTED_KEY, String(muted));
    for (const element of this.elements.values()) {
      element.muted = muted;
      if (muted) {
        element.pause();
        element.currentTime = 0;
      }
    }
    this.setSnapshot({
      muted,
      playError: muted ? null : this.snapshot.playError,
    });
  }

  setVolume(v0to1: number): void {
    const volume = clampVolume(v0to1);
    writeStoredValue(GAME_AUDIO_VOLUME_KEY, String(Math.round(volume * 100)));
    for (const element of this.elements.values()) {
      element.volume = volume;
    }
    this.setSnapshot({ volume });
  }

  preload(): void {
    if (typeof window === 'undefined') {
      return;
    }
    for (const key of ALL_GAME_AUDIO) {
      this.elementFor(key).load();
    }
  }

  private setSnapshot(next: Partial<GameAudioSnapshot>) {
    this.snapshot = {
      ...this.snapshot,
      ...next,
    };
    emit();
  }

  private elementFor(key: GameAudioKey): HTMLAudioElement {
    const existing = this.elements.get(key);
    if (existing) {
      return existing;
    }
    const element = new Audio(gameAudioPath(key));
    element.preload = 'auto';
    element.muted = this.snapshot.muted;
    element.volume = this.snapshot.volume;
    this.elements.set(key, element);
    return element;
  }
}

export const gameAudio = new BrowserAudioController();

export function useGameAudioControls() {
  const snapshot = useSyncExternalStore(
    gameAudio.subscribe,
    gameAudio.getSnapshot,
    gameAudio.getSnapshot,
  );

  const toggleMuted = useCallback(() => {
    const nextMuted = !gameAudio.getSnapshot().muted;
    gameAudio.setMuted(nextMuted);
    if (!nextMuted) {
      void gameAudio.unlock();
    }
  }, []);

  const unlock = useCallback(() => gameAudio.unlock(), []);

  return {
    ...snapshot,
    toggleMuted,
    unlock,
  };
}
