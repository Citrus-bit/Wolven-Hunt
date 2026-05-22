import { gameAudioPath, type GameAudioKey } from './audioAssets';

export interface AudioController {
  play(key: GameAudioKey): Promise<void>;
  playSequence(keys: GameAudioKey[], gapMs: number): Promise<void>;
  stopAll(): void;
  setMuted(muted: boolean): void;
  setVolume(v0to1: number): void;
}

class BrowserAudioController implements AudioController {
  private elements = new Map<GameAudioKey, HTMLAudioElement>();
  private muted = false;
  private volume = 0.8;

  async play(key: GameAudioKey): Promise<void> {
    if (typeof window === 'undefined') {
      return;
    }
    const element = this.elementFor(key);
    element.pause();
    element.currentTime = 0;
    element.muted = this.muted;
    element.volume = this.volume;
    await new Promise<void>((resolve) => {
      const cleanup = () => {
        element.removeEventListener('ended', done);
        element.removeEventListener('error', done);
      };
      const done = () => {
        cleanup();
        resolve();
      };
      element.addEventListener('ended', done, { once: true });
      element.addEventListener('error', done, { once: true });
      element.play().catch(() => done());
    });
  }

  async playSequence(keys: GameAudioKey[], gapMs: number): Promise<void> {
    for (const key of keys) {
      await this.play(key);
      if (gapMs > 0) {
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
    this.muted = muted;
    for (const element of this.elements.values()) {
      element.muted = muted;
    }
  }

  setVolume(v0to1: number): void {
    this.volume = Math.max(0, Math.min(1, v0to1));
    for (const element of this.elements.values()) {
      element.volume = this.volume;
    }
  }

  private elementFor(key: GameAudioKey): HTMLAudioElement {
    const existing = this.elements.get(key);
    if (existing) {
      return existing;
    }
    const element = new Audio(gameAudioPath(key));
    element.preload = 'auto';
    element.muted = this.muted;
    element.volume = this.volume;
    this.elements.set(key, element);
    return element;
  }
}

export const gameAudio = new BrowserAudioController();
