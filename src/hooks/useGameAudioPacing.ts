import { useRef, type MutableRefObject } from 'react';
import { type GameAudioKey } from '../lib/audioAssets';
import { sendAck as defaultSendAck, type GameEvent } from '../lib/gameApi';
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
  initialStreamCursorRef?: MutableRefObject<number>;
  sendAck?: typeof defaultSendAck;
};

export type AudioPacingRuntime = {
  enqueueAudioTrigger(event: GameEvent): void;
  resetAudioPacing(playedThroughSeq?: number): void;
};

type MutableAudioPacingRuntime = AudioPacingRuntime & {
  updateParams(params: UseGameAudioPacingParams): void;
};

export function useGameAudioPacing(
  params: UseGameAudioPacingParams,
): AudioPacingRuntime {
  const runtimeRef = useRef<MutableAudioPacingRuntime | null>(null);
  if (runtimeRef.current === null) {
    runtimeRef.current = createGameAudioPacingRuntime(params);
  }
  runtimeRef.current.updateParams(params);
  return runtimeRef.current;
}

export function createGameAudioPacingRuntime({
  gameId,
  eventsRef,
  audioDayRef,
  terminalRef,
  initialStreamCursorRef,
  sendAck = defaultSendAck,
}: UseGameAudioPacingParams): MutableAudioPacingRuntime {
  const refs = {
    gameId,
    eventsRef,
    audioDayRef,
    terminalRef,
    initialStreamCursorRef,
    sendAck,
  };
  let audioQueue = Promise.resolve();
  let audioTriggeredSeq = new Set<number>();
  let audioGeneration = 0;

  const resetAudioPacing = (playedThroughSeq = 0) => {
    audioGeneration += 1;
    gameAudio.stopAll();
    audioQueue = Promise.resolve();
    audioTriggeredSeq = new Set(
      Array.from({ length: Math.max(0, playedThroughSeq) }, (_, index) => index + 1),
    );
  };

  const runtime = {
    updateParams(params: UseGameAudioPacingParams) {
      refs.gameId = params.gameId;
      refs.eventsRef = params.eventsRef;
      refs.audioDayRef = params.audioDayRef;
      refs.terminalRef = params.terminalRef;
      refs.initialStreamCursorRef = params.initialStreamCursorRef;
      refs.sendAck = params.sendAck ?? defaultSendAck;
    },
    resetAudioPacing,
    enqueueAudioTrigger(event: GameEvent) {
      if (
        !refs.gameId ||
        event.seq <= (refs.initialStreamCursorRef?.current ?? 0) ||
        audioTriggeredSeq.has(event.seq)
      ) {
        return;
      }
      const gameId = refs.gameId;
      const generation = audioGeneration;

      const plan = phaseAudioPlan(event, refs.eventsRef.current);
      if (plan) {
        audioTriggeredSeq.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueue = audioQueue
          .catch(() => undefined)
          .then(() =>
            playSequenceThenAck(
              gameId,
              plan,
              cursor,
              refs.audioDayRef,
              refs.terminalRef,
              refs.sendAck,
              () => generation === audioGeneration,
            ),
          );
        return;
      }

      const dayPlan = dayAnnounceAudioPlan(event);
      if (dayPlan) {
        audioTriggeredSeq.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueue = audioQueue
          .catch(() => undefined)
          .then(() =>
            playDayAnnounceSequence(
              dayPlan,
              cursor,
              refs.audioDayRef,
              refs.terminalRef,
              () => generation === audioGeneration,
            ),
          );
        return;
      }

      const hostPlan = hostAudioPlan(event);
      if (hostPlan) {
        audioTriggeredSeq.add(event.seq);
        const cursor = audioCursorFromEvent(event);
        audioQueue = audioQueue
          .catch(() => undefined)
          .then(() =>
            playHostAudioSequence(
              hostPlan,
              cursor,
              refs.audioDayRef,
              refs.terminalRef,
              () => generation === audioGeneration,
            ),
          );
      }
    },
  };

  return runtime;
}

async function playSequenceThenAck(
  gameId: string,
  plan: GamePhaseAudioPlan,
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
  sendAck: typeof defaultSendAck,
  isCurrent: () => boolean,
) {
  if (!isCurrent()) {
    return;
  }
  try {
    if (shouldPlayAudio(cursor, audioDayRef, terminalRef) && isCurrent()) {
      await withTimeout(
        gameAudio.playSequence(plan.sequence, plan.gapMs),
        AUDIO_ACK_TIMEOUT_MS,
        plan.sequence,
      );
    }
  } catch {
    // Audio playback is best-effort; pacing must keep moving even if autoplay hangs.
  }
  if (!isCurrent()) {
    return;
  }
  if (
    plan.settleMs > 0 &&
    shouldPlayAudio(cursor, audioDayRef, terminalRef)
  ) {
    await delay(plan.settleMs);
  }
  if (!isCurrent()) {
    return;
  }
  await sendAck(gameId, plan.phase, plan.ackEvent).catch(() => undefined);
}

async function playDayAnnounceSequence(
  plan: DayAnnounceAudioPlan,
  cursor: AudioQueueCursor,
  audioDayRef: MutableRefObject<number>,
  terminalRef: MutableRefObject<boolean>,
  isCurrent: () => boolean,
) {
  if (!isCurrent() || !shouldPlayAudio(cursor, audioDayRef, terminalRef)) {
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
  isCurrent: () => boolean,
) {
  if (!isCurrent() || !shouldPlayAudio(cursor, audioDayRef, terminalRef)) {
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
  return (
    !terminalRef.current &&
    cursor.day >= audioDayRef.current &&
    !gameAudio.getSnapshot().muted
  );
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
