import { useCallback, useEffect, useSyncExternalStore } from 'react';

type AudioSnapshot = {
  muted: boolean;
  unlocked: boolean;
};

const audioSrc = '/assets/lobby/lobby_bgm.mp3';
let audio: HTMLAudioElement | null = null;
let snapshot: AudioSnapshot = {
  muted: true,
  unlocked: false,
};
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function setSnapshot(next: Partial<AudioSnapshot>) {
  snapshot = {
    ...snapshot,
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
  return snapshot;
}

function getServerSnapshot() {
  return snapshot;
}

function getAudio() {
  if (!audio) {
    audio = new Audio(audioSrc);
    audio.loop = true;
    audio.preload = 'auto';
    audio.muted = true;
  }

  return audio;
}

async function playMuted() {
  const current = getAudio();
  current.muted = true;

  try {
    await current.play();
  } catch {
    // Muted autoplay can still be blocked in some contexts. The first user
    // interaction path retries audibly and reports only real unlock failures.
  }
}

async function unlockAudio() {
  const current = getAudio();
  current.muted = false;

  try {
    await current.play();
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
  const { muted, unlocked } = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  useEffect(() => {
    void playMuted();
  }, []);

  const ensureUnlock = useCallback(async () => {
    if (unlocked && !getAudio().muted) {
      return true;
    }

    return unlockAudio();
  }, [unlocked]);

  const toggleMute = useCallback(() => {
    const current = getAudio();
    const nextMuted = !current.muted;
    current.muted = nextMuted;

    setSnapshot({
      muted: nextMuted,
      unlocked: snapshot.unlocked || !nextMuted,
    });

    if (!nextMuted) {
      void current.play().catch((error) => {
        current.muted = true;
        setSnapshot({
          muted: true,
          unlocked: false,
        });
        console.warn('[lobby] BGM unlock failed', error);
      });
    }
  }, []);

  return {
    muted,
    toggleMute,
    ensureUnlock,
  };
}
