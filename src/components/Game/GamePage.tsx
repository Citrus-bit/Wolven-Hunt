import {
  type Dispatch,
  type SetStateAction,
  useEffect,
  useRef,
  useState,
} from 'react';
import { INITIAL_STAGE, type GameStage } from '../../lib/gameStage';
import {
  isPendingRunLaunchState,
  isStartupPendingLaunchState,
  launchStateAfterPhase,
  launchStateAfterSummary,
  startupMessageForLaunchState,
  type LaunchState,
} from '../../lib/gameLaunchState';
import {
  getEffects,
  getEvents,
  getGame,
  getNarrative,
  pauseGame,
  subscribeGameEvents,
  type GameEvent,
  type GameTimings,
  type NarrativeRow,
  type SpectatorEffect,
} from '../../lib/gameApi';
import { preloadGameEffectAssets } from '../../lib/effectAssets';
import { gameAudio, useGameAudioControls } from '../../lib/gameAudio';
import {
  clearLiveGameSession,
  readLiveGameSession,
  writeLiveGameSession,
} from '../../lib/liveGameSession';
import {
  buildSeatEffectMap,
  publicEliminatedSeats,
  type RecentSpectatorEffect,
} from '../../lib/gameEffects';
import {
  deriveLastPlayablePhase,
  deriveStageFromEvents,
  isGameFinished,
} from '../../lib/gameSnapshot';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  missingModelConfigResult,
  readModelConfig,
  testModelConnection,
  type ModelTestResult,
} from '../../lib/modelTest';
import { ExitConfirmModal } from './ExitConfirmModal';
import { FinalFreezeChrome } from './FinalFreezeChrome';
import {
  GameBottomActions,
  type ModelTestTimingRow,
} from './GameBottomActions';
import { GameChat } from './GameChat';
import { GameEffectsLayer } from './GameEffectsLayer';
import { GamePhaseHeader } from './GamePhaseHeader';
import { GameSeat, type SeatRole } from './GameSeat';
import { GameTopBar } from './GameTopBar';
import { ModelPicker } from './ModelPicker';
import { RulesModal } from './RulesModal';
import { StageIndicator } from './StageIndicator';
import { toNarrative } from '../../lib/narrative';
import { deriveDaySpeechProgress } from '../../lib/speechProgress';
import {
  type SeatPresentationMap,
} from '../../lib/seatPresentation';
import { useGameAudioPacing } from '../../hooks/useGameAudioPacing';
import { useSpectatorEffectsRuntime } from '../../hooks/useSpectatorEffectsRuntime';
import { useGameLaunchFlow } from '../../hooks/useGameLaunchFlow';

const SEAT_COUNT = 10;
const MIN_TESTING_MS = 800;
const RECONNECT_DELAYS_MS = [1000, 3000, 5000, 10000] as const;
const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS_MS.length;
const leftSeats = [0, 1, 2, 3, 4];
const rightSeats = [5, 6, 7, 8, 9];
type BgPhase = 'idle' | 'fade-out' | 'fade-in';
const EMPTY_ASSIGNMENTS = Array.from({ length: SEAT_COUNT }, () => null);

type GamePageProps = {
  onExitGame: () => void;
  replayGameId?: string | null;
};

function shuffledModelSlots() {
  const slots = MODEL_SLOTS.map((slot) => slot.slot);

  for (let index = slots.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [slots[index], slots[swapIndex]] = [slots[swapIndex], slots[index]];
  }

  return slots;
}

function withModelTestTiming(
  result: ModelTestResult,
  startedAt: number,
  finishedAt: number,
  batchStartedAt: number,
): ModelTestResult {
  return {
    ...result,
    startedOffsetMs: startedAt - batchStartedAt,
    finishedOffsetMs: finishedAt - batchStartedAt,
    durationMs: finishedAt - startedAt,
  };
}

export function GamePage({ onExitGame, replayGameId = null }: GamePageProps) {
  const restoredLiveSessionRef = useRef(
    replayGameId === null ? readLiveGameSession() : null,
  );
  const restoredLiveSession = restoredLiveSessionRef.current;
  const [gameId, setGameId] = useState<string | null>(
    replayGameId ?? restoredLiveSession?.gameId ?? null,
  );
  const [assignments, setAssignments] = useState<(number | null)[]>(() =>
    restoredLiveSession?.assignments ?? EMPTY_ASSIGNMENTS,
  );
  const [seatPresentation, setSeatPresentation] = useState<SeatPresentationMap>(
    () => restoredLiveSession?.seatPresentation ?? {},
  );
  const [pickerSeat, setPickerSeat] = useState<number | null>(null);
  const [stage, setStage] = useState<GameStage>(INITIAL_STAGE);
  const [bgPhase, setBgPhase] = useState<BgPhase>('idle');
  const pendingStageRef = useRef<GameStage | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
  const [testResults, setTestResults] = useState<
    Record<number, ModelTestResult>
  >({});
  const [isTesting, setIsTesting] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const eventsRef = useRef<GameEvent[]>([]);
  const [narrativeRows, setNarrativeRows] = useState<NarrativeRow[]>([]);
  const narrativeSeqRef = useRef(0);
  const audioDayRef = useRef(0);
  const terminalRef = useRef(false);
  const liveSessionAbandonedRef = useRef(false);
  const liveShellMountedRef = useRef(false);
  const streamCursorRef = useRef(restoredLiveSession?.streamCursor ?? 0);
  const initialStreamCursorRef = useRef(restoredLiveSession?.streamCursor ?? 0);
  const pendingRunGameIdRef = useRef<string | null>(
    restoredLiveSession && isPendingRunLaunchState(restoredLiveSession.launchState)
      ? restoredLiveSession.gameId
      : null,
  );
  const runStartedGameIdsRef = useRef(new Set<string>());
  const [timings, setTimings] = useState<GameTimings | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    'idle' | 'connecting' | 'open' | 'error' | 'failed'
  >('idle');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [launchState, setLaunchState] = useState<LaunchState>(
    restoredLiveSession?.launchState ?? 'idle',
  );
  const [allowStartWithWarnings, setAllowStartWithWarnings] = useState(false);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const gameAudioControls = useGameAudioControls();
  const isReplay = replayGameId !== null;
  const persistRecentEffects = (nextRecentEffects: RecentSpectatorEffect[]) => {
    persistLiveSessionSnapshot({ recentEffects: nextRecentEffects });
  };
  const {
    spectatorEffects,
    recentEffects,
    effectClockMs,
    effectSeenAtRef,
    effectSeqRef,
    resetForGame: resetSpectatorEffectsForGame,
    loadReplayEffects,
    ingestLiveEffects,
    ingestHistoricalEffects,
    markFinished: markSpectatorEffectsFinished,
    handleRenderedSpectatorEffect,
  } = useSpectatorEffectsRuntime({
    gameId,
    isReplay,
    terminalRef,
    restored: restoredLiveSession
      ? {
          gameId: restoredLiveSession.gameId,
          effectSeq: restoredLiveSession.effectSeq,
          recentEffects: restoredLiveSession.recentEffects,
        }
      : null,
    persistRecentEffects,
    onEffectSeq: (seq) => updateEffectSeq(seq),
  });
  const { enqueueAudioTrigger, resetAudioPacing } = useGameAudioPacing({
    gameId,
    eventsRef,
    audioDayRef,
    terminalRef,
    initialStreamCursorRef,
  });
  const liveSessionSnapshotRef = useRef({
    gameId,
    assignments,
    seatPresentation,
    launchState,
    streamCursor: streamCursorRef.current,
    effectSeq: effectSeqRef.current,
    recentEffects,
  });

  const allSeatsAssigned = assignments.every(
    (assignment) => assignment !== null,
  );
  const allTestsPassed =
    allSeatsAssigned &&
    assignments.every(
      (slotIndex) =>
        slotIndex !== null && testResults[slotIndex]?.status === 'pass',
    );
  const allTestsCompleted =
    allSeatsAssigned &&
    assignments.every(
      (slotIndex) =>
        slotIndex !== null &&
        ['pass', 'fail'].includes(testResults[slotIndex]?.status ?? ''),
    );
  const bgSrc =
    stage.phase === 'day' ? '/assets/game/day_bg.png' : '/assets/game/night_bg.png';
  const gameStarted = gameId !== null;
  const finished = isGameFinished(events);
  const isStartingGame = [
    'connecting_service',
    'creating',
    'connecting_stream',
    'starting_backend',
  ].includes(launchState);
  const liveShellActive = gameStarted || isStartingGame;
  const startupPending =
    launchState === 'connecting_service' ||
    isStartupPendingLaunchState(launchState, {
      isReplay,
      gameStarted: liveShellActive,
      finished,
    });
  const freezePhase = deriveLastPlayablePhase(events);
  const renderPhase = finished ? freezePhase : currentPhase;
  const phaseHeaderPhase = startupPending && renderPhase === null ? 'GAME_START' : renderPhase;
  const effectPhase = finished ? 'GAME_END' : currentPhase;
  const speechProgress = deriveDaySpeechProgress(events, renderPhase);
  const currentSpeakerSeat = finished ? null : speechProgress.nextSpeakerSeat;
  const currentDay = deriveCurrentDay(events, stage.dayNumber);
  const seatEffects = buildSeatEffectMap(spectatorEffects, effectPhase, {
    currentDay,
    nowMs: effectClockMs,
    seenAtByKey: effectSeenAtRef.current,
  });
  const deadSeats = publicEliminatedSeats(events, spectatorEffects);
  const seatRoles = deriveSeatRoles(events);
  const failedModelSummaries =
    !liveShellActive && allTestsCompleted
      ? assignments
          .filter((slotIndex): slotIndex is number => slotIndex !== null)
          .filter((slotIndex) => testResults[slotIndex]?.status === 'fail')
          .map((slotIndex) => {
            const nickname = MODEL_SLOTS[slotIndex]?.nickname ?? `模型 ${slotIndex + 1}`;
            const message =
              testResults[slotIndex]?.errorMessage?.trim() || '模型测试失败';
            return `${nickname}: ${message}`;
          })
      : [];
  const modelTestTimings: ModelTestTimingRow[] =
    !liveShellActive && allTestsCompleted
      ? assignments
          .map((slotIndex, seatIndex): ModelTestTimingRow | null => {
            if (slotIndex === null) {
              return null;
            }
            const result = testResults[slotIndex];
            if (
              !result ||
              result.durationMs === undefined ||
              result.startedOffsetMs === undefined ||
              result.finishedOffsetMs === undefined ||
              !['pass', 'fail'].includes(result.status)
            ) {
              return null;
            }
            const nickname = MODEL_SLOTS[slotIndex]?.nickname ?? `模型 ${slotIndex + 1}`;
            const modelName =
              readModelConfig(slotIndex)?.modelName || `slot-${slotIndex + 1}`;

            return {
              seat: seatIndex + 1,
              nickname,
              modelName,
              status: result.status,
              errorMessage: result.errorMessage,
              durationMs: result.durationMs,
              startedOffsetMs: result.startedOffsetMs,
              finishedOffsetMs: result.finishedOffsetMs,
            };
          })
          .filter((row): row is ModelTestTimingRow => row !== null)
      : [];

  const persistLiveSessionSnapshot = (
    overrides: Partial<{
      gameId: string | null;
      assignments: (number | null)[];
      seatPresentation: SeatPresentationMap;
      launchState: LaunchState;
      streamCursor: number;
      effectSeq: number;
      recentEffects: RecentSpectatorEffect[];
    }> = {},
  ) => {
    const next = { ...liveSessionSnapshotRef.current, ...overrides };
    liveSessionSnapshotRef.current = next;
    if (
      liveSessionAbandonedRef.current ||
      isReplay ||
      terminalRef.current ||
      !next.gameId ||
      next.launchState === 'idle' ||
      next.launchState === 'failed'
    ) {
      return;
    }
    writeLiveGameSession({
      gameId: next.gameId,
      assignments: next.assignments,
      seatPresentation: next.seatPresentation,
      launchState: next.launchState,
      streamCursor: next.streamCursor,
      effectSeq: next.effectSeq,
      recentEffects: next.recentEffects,
    });
  };

  const updateStreamCursor = (seq: number) => {
    const next = Math.max(streamCursorRef.current, seq);
    if (next === streamCursorRef.current) {
      return;
    }
    streamCursorRef.current = next;
    persistLiveSessionSnapshot({ streamCursor: next });
  };

  const updateEffectSeq = (seq: number) => {
    const next = Math.max(effectSeqRef.current, seq);
    if (next === effectSeqRef.current) {
      return;
    }
    effectSeqRef.current = next;
    persistLiveSessionSnapshot({ effectSeq: next });
  };

  const updateLaunchState = (
    next:
      | LaunchState
      | ((current: LaunchState) => LaunchState),
  ) => {
    setLaunchState((current) => {
      const value = typeof next === 'function' ? next(current) : next;
      persistLiveSessionSnapshot({ launchState: value });
      return value;
    });
  };

  const transitionToStage = (next: GameStage) => {
    if (bgPhase !== 'idle') {
      return;
    }

    pendingStageRef.current = next;
    setBgPhase('fade-out');
  };

  const startPausedGameWhenReadyRef = useLatestRef<
    ((gameId: string) => Promise<void>) | null
  >(null);
  const updateLaunchStateRef = useLatestRef(updateLaunchState);
  const enqueueAudioTriggerRef = useLatestRef(enqueueAudioTrigger);
  const resetAudioPacingRef = useLatestRef(resetAudioPacing);
  const resetSpectatorEffectsForGameRef = useLatestRef(resetSpectatorEffectsForGame);
  const ingestLiveEffectsRef = useLatestRef(ingestLiveEffects);
  const ingestHistoricalEffectsRef = useLatestRef(ingestHistoricalEffects);
  const markSpectatorEffectsFinishedRef = useLatestRef(markSpectatorEffectsFinished);

  const { startGameWithAssignments, startPausedGameWhenReady } = useGameLaunchFlow({
    assignments,
    isStartingGame,
    gameStarted,
    stage,
    liveShellMountedRef,
    pendingRunGameIdRef,
    runStartedGameIdsRef,
    liveSessionAbandonedRef,
    liveSessionSnapshotRef,
    streamCursorRef,
    effectSeqRef,
    unlockAudio: gameAudioControls.unlock,
    setPickerSeat,
    setSeatPresentation,
    setLaunchState,
    updateLaunchState,
    setGameId,
    transitionToStage,
    setTestMessage,
    setTimings,
    setCurrentPhase,
    setStreamStatus,
  });
  startPausedGameWhenReadyRef.current = startPausedGameWhenReady;

  useEffect(() => {
    return () => gameAudio.stopAll();
  }, []);

  useEffect(() => {
    if (!liveShellActive) {
      return undefined;
    }
    const preloadTimer = window.setTimeout(() => {
      gameAudio.preload();
      preloadGameEffectAssets();
    }, 0);
    return () => {
      window.clearTimeout(preloadTimer);
    };
  }, [liveShellActive]);

  useEffect(() => {
    liveShellMountedRef.current = true;
    return () => {
      liveShellMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    liveSessionSnapshotRef.current = {
      gameId,
      assignments,
      seatPresentation,
      launchState,
      streamCursor: streamCursorRef.current,
      effectSeq: effectSeqRef.current,
      recentEffects,
    };
  }, [assignments, gameId, launchState, recentEffects, seatPresentation]);

  useEffect(() => {
    terminalRef.current = finished;
    if (!finished) {
      return;
    }
    clearLiveGameSession(gameId);
    liveSessionSnapshotRef.current = {
      ...liveSessionSnapshotRef.current,
      recentEffects: [],
    };
    markSpectatorEffectsFinishedRef.current();
  }, [finished, gameId]);

  useEffect(() => {
    if (!isReplay || !replayGameId) {
      return undefined;
    }
    clearLiveGameSession();
    let cancelled = false;
    setStreamStatus('connecting');
    Promise.all([getGame(replayGameId), getEvents(replayGameId), getEffects(replayGameId)])
      .then(([summary, loadedEvents, loadedEffects]) => {
        if (cancelled) {
          return;
        }
        setGameId(replayGameId);
        setSeatPresentation(summary.seat_presentation ?? {});
        setTimings(summary.timings);
        setEvents(loadedEvents);
        eventsRef.current = loadedEvents;
        terminalRef.current = isGameFinished(loadedEvents);
        loadReplayEffects(loadedEffects);
        const loadedEffectSeq = loadedEffects.reduce(
          (max, effect) => Math.max(max, effect.seq),
          0,
        );
        streamCursorRef.current = loadedEvents[loadedEvents.length - 1]?.seq ?? 0;
        effectSeqRef.current = loadedEffectSeq;
        setNarrativeRows(
          loadedEvents
            .map(toNarrative)
            .filter((row): row is NarrativeRow => row !== null),
        );
        const playablePhase = deriveLastPlayablePhase(loadedEvents);
        if (playablePhase) {
          setCurrentPhase(playablePhase);
          setStage(deriveStageFromEvents(loadedEvents, INITIAL_STAGE));
        }
        setStreamStatus('open');
      })
      .catch((error) => {
        if (!cancelled) {
          setStreamStatus('error');
          setTestMessage(error instanceof Error ? error.message : '复盘加载失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isReplay, loadReplayEffects, replayGameId]);

  useEffect(() => {
    if (isReplay) {
      return undefined;
    }
    if (!gameId) {
      setStreamStatus('idle');
      setCurrentPhase(null);
      if (!isStartingGame) {
        updateLaunchStateRef.current('idle');
      }
      return undefined;
    }

    setEvents([]);
    eventsRef.current = [];
    setNarrativeRows([]);
    narrativeSeqRef.current = 0;
    resetSpectatorEffectsForGameRef.current(gameId);
    terminalRef.current = false;
    streamCursorRef.current = restoredLiveSession?.gameId === gameId
      ? restoredLiveSession.streamCursor
      : 0;
    initialStreamCursorRef.current = streamCursorRef.current;
    resetAudioPacingRef.current(initialStreamCursorRef.current);
    runStartedGameIdsRef.current.delete(gameId);
    setCurrentPhase(null);
    setStreamStatus('connecting');
    let closed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    const handleStreamReady = () => {
      if (closed || liveSessionAbandonedRef.current) {
        return;
      }
      if (pendingRunGameIdRef.current === gameId) {
        updateLaunchStateRef.current('starting_backend');
      }
      void startPausedGameWhenReadyRef.current?.(gameId);
    };

    const connect = (lastSeq: number, attempt: number) => {
      source = subscribeGameEvents(
        gameId,
        () => {
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          setStreamStatus('open');
          setReconnectAttempts(0);
        },
        handleStreamReady,
        (event, streamCursor) => {
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          setStreamStatus('open');
          setReconnectAttempts(0);
          if (streamCursor !== null) {
            updateStreamCursor(streamCursor);
          }
          audioDayRef.current = Math.max(audioDayRef.current, event.day);
          if (isTerminalGameEvent(event)) {
            terminalRef.current = true;
            markSpectatorEffectsFinishedRef.current();
          }
          if (event.type === 'game_start') {
            updateLaunchStateRef.current((current) =>
              current === 'connecting_stream' || current === 'starting_backend'
                ? 'running'
                : current,
            );
          } else if (event.type === 'phase_enter') {
            setCurrentPhase(String(event.payload.phase ?? event.phase));
            const phase = String(event.payload.phase ?? event.phase);
            updateLaunchStateRef.current((current) => launchStateAfterPhase(current, phase));
          } else if (event.phase !== 'GAME_START') {
            updateLaunchStateRef.current((current) =>
              launchStateAfterPhase(current, event.phase),
            );
          }
          setEvents((prev) => {
            if (prev.some((existing) => existing.seq === event.seq)) {
              return prev;
            }
            const next = [...prev, event];
            eventsRef.current = next;
            return next;
          });
          const row = toNarrative(event);
          if (row) {
            narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
            appendNarrativeRow(setNarrativeRows, row);
          }
          enqueueAudioTriggerRef.current(event);
        },
        () => {
          source?.close();
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          if (terminalRef.current) {
            setStreamStatus('open');
            return;
          }
          void getGame(gameId).then((summary) => {
            if (closed || liveSessionAbandonedRef.current) {
              return;
            }
            setCurrentPhase(summary.phase);
            setTimings(summary.timings);
            if (summary.status === 'finished') {
              terminalRef.current = true;
              liveSessionSnapshotRef.current = {
                ...liveSessionSnapshotRef.current,
                recentEffects: [],
              };
              markSpectatorEffectsFinishedRef.current();
              clearLiveGameSession(gameId);
            }
            if (summary.status === 'failed') {
              setStreamStatus('failed');
            }
          }).catch(() => undefined);
          void getNarrative(gameId, narrativeSeqRef.current)
            .then((rows) => rows.forEach((row) => {
              if (closed || liveSessionAbandonedRef.current) {
                return;
              }
              narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
              appendNarrativeRow(setNarrativeRows, row);
            }))
            .catch(() => undefined);
          void getEffects(gameId, effectSeqRef.current)
            .then((effects) => {
              if (closed || liveSessionAbandonedRef.current) {
                return;
              }
              ingestHistoricalEffectsRef.current(effects, terminalRef.current);
            })
            .catch(() => undefined);
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          const nextAttempt = attempt + 1;
          setReconnectAttempts(nextAttempt);
          if (nextAttempt > MAX_RECONNECT_ATTEMPTS) {
            setStreamStatus('error');
            updateLaunchStateRef.current((current) =>
              current === 'connecting_stream' || current === 'starting_backend'
                ? 'failed'
                : current,
            );
            return;
          }
          setStreamStatus('connecting');
          reconnectTimer = window.setTimeout(() => {
            connect(streamCursorRef.current || lastSeq, nextAttempt);
          }, RECONNECT_DELAYS_MS[nextAttempt - 1]);
        },
        (row, streamCursor) => {
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          if (streamCursor !== null) {
            updateStreamCursor(streamCursor);
          }
          narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
          appendNarrativeRow(setNarrativeRows, row);
        },
        (effect, streamCursor) => {
          if (closed || liveSessionAbandonedRef.current) {
            return;
          }
          if (streamCursor !== null) {
            updateStreamCursor(streamCursor);
          }
          ingestLiveEffectsRef.current([effect]);
        },
        lastSeq,
      );
    };
    connect(streamCursorRef.current, 0);

    return () => {
      closed = true;
      source?.close();
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [gameId, isReplay]);

  useEffect(() => {
    if (!gameId || isReplay) {
      return undefined;
    }

    let cancelled = false;
    const refresh = async () => {
      try {
        const summary = await getGame(gameId);
        if (!cancelled) {
          setCurrentPhase(summary.phase);
          setTimings(summary.timings);
          updateLaunchState((current) =>
            launchStateAfterSummary(current, summary),
          );
          if (summary.status === 'finished') {
            clearLiveGameSession(gameId);
          }
          if (Object.keys(summary.seat_presentation ?? {}).length > 0) {
            setSeatPresentation(summary.seat_presentation);
          }
        }
      } catch {
        if (!cancelled) {
          setStreamStatus('error');
        }
      }
    };
    refresh();

    return () => {
      cancelled = true;
    };
  }, [gameId, isReplay]);

  useEffect(() => {
    if (events.length === 0 || bgPhase !== 'idle') {
      return;
    }
    const nextStage = deriveStageFromEvents(events, stage);
    if (stage.dayNumber !== nextStage.dayNumber || stage.phase !== nextStage.phase) {
      transitionToStage(nextStage);
    }
  }, [bgPhase, events, stage.dayNumber, stage.phase]);

  const handleClickSeat = (seatIndex: number) => {
    if (isTesting || liveShellActive) {
      return;
    }

    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null || liveShellActive) {
      return;
    }

    const previousSlot = assignments[pickerSeat];
    if (previousSlot === slotIndex) {
      setPickerSeat(null);
      return;
    }

    const occupiedSeat = assignments.findIndex(
      (assignment, seatIndex) =>
        seatIndex !== pickerSeat && assignment === slotIndex,
    );
    if (occupiedSeat !== -1) {
      return;
    }

    setAssignments((prev) => {
      const next = [...prev];
      next[pickerSeat] = slotIndex;
      return next;
    });
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[slotIndex];

      if (previousSlot !== null) {
        delete next[previousSlot];
      }

      return next;
    });
    setTestMessage(null);
    setAllowStartWithWarnings(false);
    setPickerSeat(null);
  };

  const handleSwapModel = (slotIndex: number) => {
    if (pickerSeat === null || isTesting || liveShellActive) {
      return;
    }

    const currentSlot = assignments[pickerSeat];
    if (currentSlot === null || currentSlot === slotIndex) {
      return;
    }

    const targetSeat = assignments.findIndex(
      (assignment, seatIndex) =>
        seatIndex !== pickerSeat && assignment === slotIndex,
    );
    if (targetSeat === -1) {
      return;
    }

    setAssignments((prev) => {
      const next = [...prev];
      next[pickerSeat] = slotIndex;
      next[targetSeat] = currentSlot;
      return next;
    });
    setPickerSeat(null);
  };

  const handleQuickAssign = () => {
    if (isTesting || liveShellActive) {
      return;
    }

    setPickerSeat(null);
    setAssignments(shuffledModelSlots());
    setTestResults({});
    setTestMessage(null);
    setAllowStartWithWarnings(false);
  };

  const handleStageOverlayTransitionEnd = () => {
    if (bgPhase === 'fade-out' && pendingStageRef.current) {
      setStage(pendingStageRef.current);
      pendingStageRef.current = null;
      requestAnimationFrame(() => setBgPhase('fade-in'));
      return;
    }

    if (bgPhase === 'fade-in') {
      setBgPhase('idle');
    }
  };

  const handleClickTest = async () => {
    if (!allSeatsAssigned || isTesting || liveShellActive) {
      return;
    }

    setPickerSeat(null);
    setIsTesting(true);
    setTestMessage(`正在测试 0/${SEAT_COUNT}`);

    const assignedSlots = assignments.filter(
      (slotIndex): slotIndex is number => slotIndex !== null,
    );

    const initial: Record<number, ModelTestResult> = {};
    assignedSlots.forEach((slotIndex) => {
      initial[slotIndex] = { status: 'testing' };
    });
    setTestResults(initial);

    let completedCount = 0;
    const batchStartedAt = window.performance.now();

    const testTasks = assignedSlots.map(async (slotIndex) => {
      const requestStartedAt = window.performance.now();
      try {
        const config = readModelConfig(slotIndex);
        if (!config) {
          const finishedAt = window.performance.now();
          return {
            slotIndex,
            result: withModelTestTiming(
              missingModelConfigResult(),
              requestStartedAt,
              finishedAt,
              batchStartedAt,
            ),
          };
        }

        const result = await testModelConnection(config);
        const finishedAt = window.performance.now();
        return {
          slotIndex,
          result: withModelTestTiming(
            result,
            requestStartedAt,
            finishedAt,
            batchStartedAt,
          ),
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : '未知错误';
        const finishedAt = window.performance.now();
        return {
          slotIndex,
          result: withModelTestTiming(
            {
              status: 'fail',
              errorMessage: message.slice(0, 80),
            },
            requestStartedAt,
            finishedAt,
            batchStartedAt,
          ),
        };
      } finally {
        completedCount += 1;
        setTestMessage(`正在测试 ${completedCount}/${assignedSlots.length}`);
      }
    });

    const settledResults = await Promise.allSettled(testTasks);
    const elapsed = window.performance.now() - batchStartedAt;
    if (elapsed < MIN_TESTING_MS) {
      await new Promise((resolve) =>
        window.setTimeout(resolve, MIN_TESTING_MS - elapsed),
      );
    }

    const settledAt = window.performance.now();
    const nextResults: Record<number, ModelTestResult> = {};
    assignedSlots.forEach((slotIndex) => {
      nextResults[slotIndex] = withModelTestTiming(
        {
          status: 'fail',
          errorMessage: '测试未返回结果',
        },
        batchStartedAt,
        settledAt,
        batchStartedAt,
      );
    });
    settledResults.forEach((settled) => {
      if (settled.status === 'fulfilled') {
        const { slotIndex, result } = settled.value;
        nextResults[slotIndex] = result;
      }
    });
    setTestResults((prev) => {
      const next = { ...prev };
      Object.entries(nextResults).forEach(([slotIndex, result]) => {
        next[Number(slotIndex)] = result;
      });
      return next;
    });

    const passCount = Object.values(nextResults).filter(
      (result) => result.status === 'pass',
    ).length;
    const hasFailures = passCount < assignedSlots.length;
    setTestMessage(
      hasFailures
        ? `${passCount}/${assignedSlots.length} 个模型连通性测试通过；仍可开局，运行失败时后端会按 fallback 继续`
        : '全部模型连通性测试通过',
    );
    setAllowStartWithWarnings(hasFailures);
    setIsTesting(false);
  };

  const handleClickEnterNight = async () => {
    if (!allSeatsAssigned || isStartingGame || gameStarted) {
      return;
    }
    if (!allTestsPassed && !allowStartWithWarnings && allTestsCompleted) {
      setAllowStartWithWarnings(true);
      setTestMessage('模型测试存在失败；再次点击“仍然开局”将继续，后端 fallback 会兜底');
      return;
    }
    await startGameWithAssignments();
  };

  const handleConfirmExit = () => {
    liveSessionAbandonedRef.current = true;
    gameAudio.stopAll();
    clearLiveGameSession(gameId);
    if (gameId && !isReplay && !finished) {
      void pauseGame(gameId).catch(() => undefined);
    }
    setExitConfirmOpen(false);
    onExitGame();
  };

  const handleToggleAutoScroll = () => {
    setAutoScrollEnabled((enabled) => !enabled);
  };

  const handleToggleGameAudio = () => {
    if (gameAudioControls.playError && !gameAudioControls.muted) {
      void gameAudioControls.unlock();
      return;
    }
    gameAudioControls.toggleMuted();
  };

  return (
    <main
      className={['game-page', finished ? 'game-page--final-freeze' : ''].join(' ')}
      aria-label="Wolven Hunt 游戏"
    >
      <img
        key={bgSrc}
        src={bgSrc}
        alt=""
        className="game-bg"
        loading="eager"
      />
      <div
        className={`game-stage-overlay ${
          bgPhase !== 'idle' ? `game-stage-overlay--${bgPhase}` : ''
        }`}
        onTransitionEnd={handleStageOverlayTransitionEnd}
      />
      <GameTopBar
        onClickRules={() => setRulesOpen(true)}
        onClickExit={() => setExitConfirmOpen(true)}
        streamStatus={streamStatus}
        reconnectAttempts={reconnectAttempts}
        autoScrollEnabled={autoScrollEnabled}
        gameAudioMuted={gameAudioControls.muted}
        gameAudioError={gameAudioControls.playError}
        onToggleAutoScroll={handleToggleAutoScroll}
        onToggleGameAudio={handleToggleGameAudio}
      />
      <StageIndicator stage={stage} />
      {liveShellActive && (
        <GamePhaseHeader
          phase={phaseHeaderPhase}
          timings={timings}
          speakerSeat={currentSpeakerSeat}
          speechComplete={finished || speechProgress.complete}
          startupPending={startupPending}
          startupMessage={startupMessageForLaunchState(launchState)}
        />
      )}
      <GameChat
        events={events}
        narrativeRows={narrativeRows}
        assignments={assignments}
        streamStatus={streamStatus}
        autoScrollEnabled={autoScrollEnabled}
        liveTypingEnabled={!isReplay}
      />
      <GameEffectsLayer
        effects={spectatorEffects}
        currentDay={currentDay}
        currentPhase={currentPhase}
        nowMs={effectClockMs}
        seenAtByKey={effectSeenAtRef.current}
        recentEffects={recentEffects}
        terminal={finished}
        onEffectRendered={handleRenderedSpectatorEffect}
      />
      {!liveShellActive && !isReplay && (
        <div className="game-quick-assign-helper">
          <button
            type="button"
            className="game-quick-assign"
            onClick={handleQuickAssign}
            disabled={isTesting}
          >
            一键分配
          </button>
        </div>
      )}
      <div className="game-seats" aria-label="席位区">
        <div className="game-seats-col game-seats-col--left">
          {leftSeats.map((seatIndex) => {
            const assignment = assignments[seatIndex];

            return (
              <GameSeat
                key={seatIndex}
                seatIndex={seatIndex}
                side="left"
                assignment={assignment}
                presentation={seatPresentation[seatIndex + 1] ?? null}
                role={seatRoles[seatIndex + 1] ?? null}
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!liveShellActive}
                thinkingEnabled={
                  assignment !== null &&
                  readModelConfig(assignment)?.thinkingEnabled === true
                }
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
                effects={seatEffects[seatIndex + 1]}
                disabled={liveShellActive}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
        <div className="game-seats-col game-seats-col--right">
          {rightSeats.map((seatIndex) => {
            const assignment = assignments[seatIndex];

            return (
              <GameSeat
                key={seatIndex}
                seatIndex={seatIndex}
                side="right"
                assignment={assignment}
                presentation={seatPresentation[seatIndex + 1] ?? null}
                role={seatRoles[seatIndex + 1] ?? null}
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!liveShellActive}
                thinkingEnabled={
                  assignment !== null &&
                  readModelConfig(assignment)?.thinkingEnabled === true
                }
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
                effects={seatEffects[seatIndex + 1]}
                disabled={liveShellActive}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
      </div>
      {!liveShellActive && !isReplay && (
        <GameBottomActions
          allSeatsAssigned={allSeatsAssigned}
          allTestsPassed={allTestsPassed}
          canStartWithWarnings={allowStartWithWarnings || allTestsCompleted}
          isTesting={isTesting}
          isStartingGame={isStartingGame}
          startingLabel={startupMessageForLaunchState(launchState)}
          testMessage={testMessage}
          testFailures={failedModelSummaries}
          testTimings={modelTestTimings}
          onClickTest={handleClickTest}
          onClickEnterNight={handleClickEnterNight}
        />
      )}
      <ModelPicker
        open={pickerSeat !== null}
        onClose={() => setPickerSeat(null)}
        currentAssignment={pickerSeat !== null ? assignments[pickerSeat] : null}
        usedSlots={assignments.filter((slot): slot is number => slot !== null)}
        onPick={handlePickModel}
        onSwap={handleSwapModel}
      />
      <RulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} />
      <FinalFreezeChrome
        gameId={gameId}
        events={events}
        assignments={assignments}
        seatPresentation={seatPresentation}
        isReplay={isReplay}
        onExitGame={handleConfirmExit}
      />
      <ExitConfirmModal
        open={exitConfirmOpen}
        onClose={() => setExitConfirmOpen(false)}
        onConfirm={handleConfirmExit}
      />
    </main>
  );
}

function appendNarrativeRow(
  setRows: Dispatch<SetStateAction<NarrativeRow[]>>,
  row: NarrativeRow,
) {
  setRows((prev) => {
    if (
      prev.some(
        (existing) =>
          existing.seq === row.seq &&
          existing.kind === row.kind &&
          existing.text === row.text,
      )
    ) {
      return prev;
    }
    return [...prev, row];
  });
}

function isTerminalGameEvent(event: GameEvent) {
  return event.type === 'game_end' || event.type === 'role_reveal';
}

function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

function deriveSeatRoles(events: GameEvent[]): Partial<Record<number, SeatRole>> {
  const roles: Partial<Record<number, SeatRole>> = {};
  for (const event of events) {
    if (event.type === 'game_start') {
      const assignment = event.payload.role_assignment;
      if (assignment && typeof assignment === 'object' && !Array.isArray(assignment)) {
        for (const [seat, role] of Object.entries(assignment as Record<string, unknown>)) {
          if (isSeatRole(role)) {
            roles[Number(seat)] = role;
          }
        }
      }
    }
    if (event.type === 'role_reveal' && Array.isArray(event.payload.seats)) {
      for (const seatInfo of event.payload.seats) {
        if (!seatInfo || typeof seatInfo !== 'object') {
          continue;
        }
        const seat = 'seat' in seatInfo ? Number(seatInfo.seat) : NaN;
        const role = 'role' in seatInfo ? seatInfo.role : null;
        if (Number.isFinite(seat) && isSeatRole(role)) {
          roles[seat] = role;
        }
      }
    }
  }
  return roles;
}

function deriveCurrentDay(events: GameEvent[], fallbackDay: number) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === 'phase_enter') {
      return events[index].day;
    }
  }
  return fallbackDay;
}

function isSeatRole(value: unknown): value is SeatRole {
  return (
    value === 'wolf' ||
    value === 'villager' ||
    value === 'seer' ||
    value === 'witch' ||
    value === 'guard'
  );
}
