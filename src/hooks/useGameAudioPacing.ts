import { useCallback, useRef, type MutableRefObject } from 'react';
import { type GameAudioKey } from '../lib/audioAssets';
import { sendAck, type GameEvent } from '../lib/gameApi';
import { gameAudio } from '../lib/gameAudio';
import {
  dayAnnounceAudioPlan,
  hostAudioPlan,
  phaseAudioPlan,
  type DayAnnounceAudioPlan,
  type GamePhaseAudioPlan,
  type HostAudioPlan,
} from '../lib/gamePhaseAudio';

const AUDIO_ACK_TIMEOUT_MS = 12000;

type AudioQueueCursor = {
  day: number;
  seq: number;
};

type UseGameAudioPacingParams = {
  gameId: string | null;
  eventsRef: MutableRefObject<GameEvent[]>;
  audioDayRef: MutableRefObject<number>;
  terminalRef: MutableRefObject<boolean>;
};

export function useGameAudioPacing({
  gameId,
  eventsRef,
  audioDayRef,
  terminalRef,
}: UseGameAudioPacingParams) {
  const audioQueueRef = useRef(Promise.resolve());
  const audioTriggeredSeqRef = useRef(new Set<number>());

  const resetAudioPacing = useCallback(() => {
    audioQueueRef.current = Promise.resolve();
    audioTriggeredSeqRef.current = new Set();
  }, []);

  const enqueueAudioTrigger = useCallback(
    (event: GameEvent) => {
      if (!gameId || audioTriggeredSeqRef.current.has(event.seq)) {
        return;
      }

      const plan = phaseAudioPlan(event, eventsRef.current);
      if (plan) {
        audioTriggeredSeqRef.current.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueueRef.current = audioQueueRef.current
          .catch(() => undefined)
          .then(() =>
            playSequenceThenAck(
              gameId,
              plan,
              cursor,
              audioDayRef,
              terminalRef,
            ),
          );
        return;
      }

      const dayPlan = dayAnnounceAudioPlan(event);
      if (dayPlan) {
        audioTriggeredSeqRef.current.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueueRef.current = audioQueueRef.current
          .catch(() => undefined)
          .then(() =>
            playDayAnnounceSequence(
              dayPlan,
              cursor,
              audioDayRef,
              terminalRef,
            ),
          );
        return;
      }

      const hostPlan = hostAudioPlan(event);
      if (hostPlan) {
        audioTriggeredSeqRef.current.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueueRef.current = audioQueueRef.current
          .catch(() => undefined)
          .then(() => playHostAudioSequence(hostPlan, cursor, audioDayRef, terminalRef));
      }
    },
    [audioDayRef, eventsRef, gameId, terminalRef],
  );

  return {
    enqueueAudioTrigger,
    resetAudioPacing,
  };
}

async function playSequenceThenAck(
  gameId: string,
  plan: GamePhaseAudioPlan,
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
) {
  try {
    if (shouldPlayAudio(cursor, audioDayRef, terminalRef)) {
      await withTimeout(
        gameAudio.playSequence(plan.sequence, plan.gapMs),
        AUDIO_ACK_TIMEOUT_MS,
        plan.sequence,
      );
    }
  } catch {
    // Audio playback is best-effort; pacing must keep moving even if autoplay hangs.
  }
  if (plan.settleMs > 0) {
    await delay(plan.settleMs);
  }
  await sendAck(gameId, plan.phase, plan.ackEvent).catch(() => undefined);
}

async function playDayAnnounceSequence(
  plan: DayAnnounceAudioPlan,
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
) {
  if (!shouldPlayAudio(cursor, audioDayRef, terminalRef)) {
    return;
  }
  try {
    await withTimeout(
      gameAudio.playSequence(plan.sequence, plan.gapMs),
      AUDIO_ACK_TIMEOUT_MS,
      plan.sequence,
    );
  } catch {
    // Result voice is UI-only; stale or blocked audio should never block the game.
  }
}

async function playHostAudioSequence(
  plan: HostAudioPlan,
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
) {
  if (!shouldPlayAudio(cursor, audioDayRef, terminalRef)) {
    return;
  }
  try {
    await withTimeout(
      gameAudio.playSequence(plan.sequence, plan.gapMs),
      AUDIO_ACK_TIMEOUT_MS,
      plan.sequence,
    );
  } catch {
    // Host voice is UI-only; stale or blocked audio should never block the game.
  }
}

function audioCursorFromEvent(event: GameEvent): AudioQueueCursor {
  return {
    day: event.day,
    seq: event.seq,
  };
}

function shouldPlayAudio(
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
) {
  return !terminalRef.current && cursor.day >= audioDayRef.current;
}

function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  stopKeys: GameAudioKey[] = [],
): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      if (stopKeys.length > 0) {
        gameAudio.stopKeys(stopKeys);
      }
      reject(new Error('audio_timeout'));
    }, timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timeout);
        resolve(value);
      },
      (error: unknown) => {
        window.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

function delay(ms: number): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
