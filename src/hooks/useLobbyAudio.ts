import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { VOLUME_DEFAULT, VOLUME_MAX, VOLUME_MIN } from '../lib/modelConfigs';

type AudioSnapshot = {
  muted: boolean;
  unlocked: boolean;
  volume: number;
};

type LobbyAudioStore = {
  audio: HTMLAudioElement | null;
  hasStoredMutedPreference: boolean;
  mutedAutoplayStarted: boolean;
  snapshot: AudioSnapshot;
};

declare global {
  interface Window {
    __wolvenHuntLobbyAudio?: LobbyAudioStore;
  }
}

const audioSrc = '/assets/lobby/lobby_bgm.mp3';
const volumeKey = 'wolven_hunt.lobby.volume';
const mutedKey = 'wolven_hunt.lobby.muted';
const initialSnapshot: AudioSnapshot = {
  muted: true,
  unlocked: false,
  volume: VOLUME_DEFAULT,
};
const audioStore: LobbyAudioStore =
  typeof window === 'undefined'
    ? {
        audio: null,
        hasStoredMutedPreference: false,
        mutedAutoplayStarted: false,
        snapshot: initialSnapshot,
      }
    : (window.__wolvenHuntLobbyAudio ??= {
        audio: null,
        hasStoredMutedPreference: false,
        mutedAutoplayStarted: false,
        snapshot: initialSnapshot,
      });
const listeners = new Set<() => void>();

function clampVolume(value: number) {
  if (!Number.isFinite(value)) {
    return VOLUME_DEFAULT;
  }

  return Math.min(VOLUME_MAX, Math.max(VOLUME_MIN, Math.round(value)));
}

function readStoredVolume() {
  if (typeof window === 'undefined') {
    return VOLUME_DEFAULT;
  }

  try {
    const raw = window.localStorage.getItem(volumeKey);
    if (raw === null) {
      return VOLUME_DEFAULT;
    }

    return clampVolume(Number(raw));
  } catch (error) {
    console.warn(`[lobby] failed to read localStorage key=${volumeKey}`, error);
    return VOLUME_DEFAULT;
  }
}

function readStoredMuted() {
  if (typeof window === 'undefined') {
    return true;
  }

  try {
    const raw = window.localStorage.getItem(mutedKey);
    audioStore.hasStoredMutedPreference = raw !== null;
    return raw === null ? true : raw === 'true';
  } catch (error) {
    console.warn(`[lobby] failed to read localStorage key=${mutedKey}`, error);
    audioStore.hasStoredMutedPreference = false;
    return true;
  }
}

function writeStoredValue(key: string, value: string) {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn(`[lobby] failed to write localStorage key=${key}`, error);
  }
}

function hydrateAudioPreferences() {
  const volume = readStoredVolume();
  const muted = readStoredMuted();
  audioStore.snapshot = {
    ...audioStore.snapshot,
    muted,
    volume,
  };
}

hydrateAudioPreferences();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function setSnapshot(next: Partial<AudioSnapshot>) {
  audioStore.snapshot = {
    ...audioStore.snapshot,
    ...next,
  };
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot() {
  return audioStore.snapshot;
}

function getServerSnapshot() {
  return audioStore.snapshot;
}

function getAudio() {
  if (!audioStore.audio) {
    const existing =
      typeof document === 'undefined'
        ? []
        : Array.from(
            document.querySelectorAll<HTMLAudioElement>(
              'audio[data-lobby-bgm="true"]',
            ),
          );
    const [current, ...duplicates] = existing;

    for (const duplicate of duplicates) {
      duplicate.pause();
      duplicate.removeAttribute('src');
      duplicate.load();
      duplicate.remove();
    }

    audioStore.audio = current ?? new Audio(audioSrc);
    audioStore.audio.loop = true;
    audioStore.audio.preload = 'auto';
    audioStore.audio.volume = audioStore.snapshot.volume / 100;
    audioStore.audio.muted = true;
    audioStore.audio.setAttribute('aria-hidden', 'true');
    audioStore.audio.dataset.lobbyBgm = 'true';
    audioStore.audio.style.display = 'none';
  }

  const current = audioStore.audio;
  if (
    typeof document !== 'undefined' &&
    document.body &&
    !current.isConnected
  ) {
    document.body.append(current);
  }

  return current;
}

async function playMuted() {
  if (audioStore.mutedAutoplayStarted) {
    return;
  }

  audioStore.mutedAutoplayStarted = true;
  const current = getAudio();
  current.muted = true;
  current.volume = audioStore.snapshot.volume / 100;

  try {
    await current.play();
  } catch {
    // Muted autoplay can still be blocked in some contexts. The first user
    // interaction path retries audibly and reports only real unlock failures.
  }
}

async function unlockAudio() {
  const current = getAudio();
  const shouldStayMuted =
    audioStore.hasStoredMutedPreference && audioStore.snapshot.muted;
  current.volume = audioStore.snapshot.volume / 100;
  current.muted = shouldStayMuted;

  if (shouldStayMuted) {
    setSnapshot({
      unlocked: true,
    });
    return true;
  }

  try {
    await current.play();
    writeStoredValue(mutedKey, 'false');
    setSnapshot({
      muted: false,
      unlocked: true,
    });
    return true;
  } catch (error) {
    current.muted = true;
    setSnapshot({
      muted: true,
      unlocked: false,
    });
    console.warn('[lobby] BGM unlock failed', error);
    return false;
  }
}

export function useLobbyAudio() {
  const { muted, unlocked, volume } = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  useEffect(() => {
    void playMuted();
  }, []);

  const ensureUnlock = useCallback(async () => {
    if (unlocked) {
      return true;
    }

    return unlockAudio();
  }, [unlocked]);

  const toggleMute = useCallback(() => {
    const current = getAudio();
    const nextMuted = !current.muted;
    current.muted = nextMuted;
    current.volume = audioStore.snapshot.volume / 100;
    writeStoredValue(mutedKey, String(nextMuted));

    setSnapshot({
      muted: nextMuted,
      unlocked: audioStore.snapshot.unlocked || !nextMuted,
    });

    if (!nextMuted) {
      void current.play().catch((error) => {
        current.muted = true;
        setSnapshot({
          muted: true,
          unlocked: false,
        });
        writeStoredValue(mutedKey, 'true');
        console.warn('[lobby] BGM unlock failed', error);
      });
    }
  }, []);

  const setVolume = useCallback((next: number) => {
    const nextVolume = clampVolume(next);
    const current = getAudio();
    current.volume = nextVolume / 100;
    writeStoredValue(volumeKey, String(nextVolume));

    setSnapshot({
      volume: nextVolume,
    });
  }, []);

  return {
    muted,
    volume,
    setVolume,
    toggleMute,
    ensureUnlock,
  };
}
