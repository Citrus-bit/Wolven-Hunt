import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from 'react';
import { INITIAL_STAGE, type GameStage } from '../../lib/gameStage';
import {
  createGame,
  getEffects,
  getEvents,
  getGame,
  getNarrative,
  sendAck,
  spectatorEffectAckEvent,
  subscribeGameEvents,
  type GameEvent,
  type GameTimings,
  type NarrativeRow,
  type SpectatorEffect,
} from '../../lib/gameApi';
import { buildAgentSpecs } from '../../lib/agentSpecs';
import { preloadGameEffectAssets } from '../../lib/effectAssets';
import { gameAudio, useGameAudioControls } from '../../lib/gameAudio';
import {
  appendRecentSpectatorEffects,
  appendUniqueSpectatorEffects,
  buildSeatEffectMap,
  expireTransientEffectSeenAt,
  pruneRecentSpectatorEffects,
  publicEliminatedSeats,
  seedExpiredEffectSeenAt,
  seedLiveEffectSeenAt,
  type EffectSeenAtMap,
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
  buildSeatPresentation,
  type SeatPresentationMap,
} from '../../lib/seatPresentation';

const SEAT_COUNT = 10;
const MIN_TESTING_MS = 800;
const RECONNECT_DELAYS_MS = [1000, 3000, 5000, 10000] as const;
const MAX_RECONNECT_ATTEMPTS = RECONNECT_DELAYS_MS.length;
const AUDIO_ACK_TIMEOUT_MS = 6000;
const leftSeats = [0, 1, 2, 3, 4];
const rightSeats = [5, 6, 7, 8, 9];
type BgPhase = 'idle' | 'fade-out' | 'fade-in';

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
  const [gameId, setGameId] = useState<string | null>(replayGameId);
  const [assignments, setAssignments] = useState<(number | null)[]>(() =>
    Array.from({ length: SEAT_COUNT }, () => null),
  );
  const [seatPresentation, setSeatPresentation] = useState<SeatPresentationMap>({});
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
  const [spectatorEffects, setSpectatorEffects] = useState<SpectatorEffect[]>([]);
  const [recentEffects, setRecentEffects] = useState<RecentSpectatorEffect[]>([]);
  const effectSeenAtRef = useRef<EffectSeenAtMap>({});
  const [effectClockMs, setEffectClockMs] = useState(() => Date.now());
  const effectSeqRef = useRef(0);
  const effectAckSeqRef = useRef(new Set<number>());
  const terminalRef = useRef(false);
  const streamCursorRef = useRef(0);
  const [timings, setTimings] = useState<GameTimings | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    'idle' | 'connecting' | 'open' | 'error' | 'failed'
  >('idle');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [isStartingGame, setIsStartingGame] = useState(false);
  const [allowStartWithWarnings, setAllowStartWithWarnings] = useState(false);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const gameAudioControls = useGameAudioControls();
  const isReplay = replayGameId !== null;

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
  const freezePhase = deriveLastPlayablePhase(events);
  const renderPhase = finished ? freezePhase : currentPhase;
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
    !gameStarted && allTestsCompleted
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
    !gameStarted && allTestsCompleted
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

  useEffect(() => {
    gameAudio.preload();
    preloadGameEffectAssets();
    return () => gameAudio.stopAll();
  }, []);

  useEffect(() => {
    terminalRef.current = finished;
    if (!finished) {
      return;
    }
    const nowMs = Date.now();
    expireTransientEffectSeenAt(spectatorEffects, effectSeenAtRef.current, nowMs);
    setEffectClockMs(nowMs);
    setRecentEffects((current) => (current.length === 0 ? current : []));
  }, [finished, spectatorEffects]);

  useEffect(() => {
    if (spectatorEffects.length === 0 && recentEffects.length === 0) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      const nowMs = Date.now();
      setEffectClockMs(nowMs);
      setRecentEffects((current) => pruneRecentSpectatorEffects(current, nowMs));
    }, 250);
    return () => window.clearInterval(timer);
  }, [recentEffects.length, spectatorEffects.length]);

  useEffect(() => {
    if (!isReplay || !replayGameId) {
      return undefined;
    }
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
        effectSeenAtRef.current = {};
        const nowMs = Date.now();
        seedExpiredEffectSeenAt(loadedEffects, effectSeenAtRef.current, nowMs);
        terminalRef.current = isGameFinished(loadedEvents);
        setEffectClockMs(nowMs);
        setSpectatorEffects(loadedEffects);
        setRecentEffects([]);
        effectSeqRef.current = loadedEffects.reduce(
          (max, effect) => Math.max(max, effect.seq),
          0,
        );
        streamCursorRef.current = Math.max(
          loadedEvents[loadedEvents.length - 1]?.seq ?? 0,
          effectSeqRef.current,
        );
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
  }, [isReplay, replayGameId]);

  useEffect(() => {
    if (isReplay) {
      return undefined;
    }
    if (!gameId) {
      setStreamStatus('idle');
      setCurrentPhase(null);
      return undefined;
    }

    setEvents([]);
    eventsRef.current = [];
    setNarrativeRows([]);
    narrativeSeqRef.current = 0;
    setSpectatorEffects([]);
    setRecentEffects([]);
    effectSeenAtRef.current = {};
    setEffectClockMs(Date.now());
    effectSeqRef.current = 0;
    effectAckSeqRef.current = new Set();
    terminalRef.current = false;
    streamCursorRef.current = 0;
    setCurrentPhase(null);
    setStreamStatus('connecting');
    let closed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;

    const connect = (lastSeq: number, attempt: number) => {
      source = subscribeGameEvents(
        gameId,
        (event) => {
          setStreamStatus('open');
          setReconnectAttempts(0);
          streamCursorRef.current = Math.max(streamCursorRef.current, event.seq);
          if (isTerminalGameEvent(event)) {
            terminalRef.current = true;
            setRecentEffects((current) => (current.length === 0 ? current : []));
            setEffectClockMs(Date.now());
          }
          if (event.type === 'phase_enter') {
            setCurrentPhase(String(event.payload.phase ?? event.phase));
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
          void handleAudioTrigger(gameId, event, eventsRef);
        },
        () => {
          source?.close();
          void getGame(gameId).then((summary) => {
            setCurrentPhase(summary.phase);
            setTimings(summary.timings);
            if (summary.status === 'finished') {
              terminalRef.current = true;
              setRecentEffects((current) => (current.length === 0 ? current : []));
            }
            if (summary.status === 'failed') {
              setStreamStatus('failed');
            }
          }).catch(() => undefined);
          void getNarrative(gameId, narrativeSeqRef.current)
            .then((rows) => rows.forEach((row) => {
              narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
              appendNarrativeRow(setNarrativeRows, row);
            }))
            .catch(() => undefined);
          void getEffects(gameId, effectSeqRef.current)
            .then((effects) => {
              const nowMs = Date.now();
              ingestLiveSpectatorEffects(
                setSpectatorEffects,
                setRecentEffects,
                effects,
                effectSeenAtRef.current,
                nowMs,
                terminalRef.current,
                false,
              );
              effects.forEach((effect) => {
                effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
              });
              if (effects.length > 0) {
                setEffectClockMs(nowMs);
              }
            })
            .catch(() => undefined);
          if (closed) {
            return;
          }
          const nextAttempt = attempt + 1;
          setReconnectAttempts(nextAttempt);
          setStreamStatus('error');
          if (nextAttempt > MAX_RECONNECT_ATTEMPTS) {
            return;
          }
          reconnectTimer = window.setTimeout(() => {
            connect(streamCursorRef.current || lastSeq, nextAttempt);
          }, RECONNECT_DELAYS_MS[nextAttempt - 1]);
        },
        (row) => {
          narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
          streamCursorRef.current = Math.max(streamCursorRef.current, row.seq);
          appendNarrativeRow(setNarrativeRows, row);
        },
        (effect) => {
          const nowMs = Date.now();
          ingestLiveSpectatorEffects(
            setSpectatorEffects,
            setRecentEffects,
            [effect],
            effectSeenAtRef.current,
            nowMs,
            terminalRef.current,
          );
          setEffectClockMs(nowMs);
          effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
          streamCursorRef.current = Math.max(streamCursorRef.current, effect.seq);
        },
        lastSeq,
      );
    };
    connect(0, 0);

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
    if (isTesting || gameStarted) {
      return;
    }

    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null || gameStarted) {
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
    if (pickerSeat === null || isTesting || gameStarted) {
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
    if (isTesting || gameStarted) {
      return;
    }

    setPickerSeat(null);
    setAssignments(shuffledModelSlots());
    setTestResults({});
    setTestMessage(null);
    setAllowStartWithWarnings(false);
  };

  const transitionToStage = (next: GameStage) => {
    if (bgPhase !== 'idle') {
      return;
    }

    pendingStageRef.current = next;
    setBgPhase('fade-out');
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
    if (!allSeatsAssigned || isTesting || gameStarted) {
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
    setPickerSeat(null);
    setIsStartingGame(true);
    setTestMessage('正在创建对局并接入模型');
    try {
      void gameAudioControls.unlock();
      const agents = buildAgentSpecs(assignments);
      const presentation = buildSeatPresentation(assignments);
      setSeatPresentation(presentation);
      const created = await createGame({
        agents,
        pacing: 'live',
        seatPresentation: presentation,
      });
      setGameId(created.game_id);
      transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
    } catch (caught) {
      setTestMessage(caught instanceof Error ? caught.message : '创建游戏失败');
    } finally {
      setIsStartingGame(false);
    }
  };

  const handleRenderedSpectatorEffect = (effect: SpectatorEffect) => {
    if (!gameId || isReplay || terminalRef.current || effect.kind === 'death_reveal') {
      return;
    }
    if (effectAckSeqRef.current.has(effect.seq)) {
      return;
    }
    effectAckSeqRef.current.add(effect.seq);
    void sendAck(gameId, effect.phase, spectatorEffectAckEvent(effect.seq)).catch(
      () => undefined,
    );
  };

  const handleConfirmExit = () => {
    gameAudio.stopAll();
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
      {gameStarted && (
        <GamePhaseHeader
          phase={renderPhase}
          timings={timings}
          speakerSeat={currentSpeakerSeat}
          speechComplete={finished || speechProgress.complete}
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
      {!gameStarted && !isReplay && (
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
                showTestBadge={!gameStarted}
                thinkingEnabled={
                  assignment !== null &&
                  readModelConfig(assignment)?.thinkingEnabled === true
                }
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
                effects={seatEffects[seatIndex + 1]}
                disabled={gameStarted}
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
                showTestBadge={!gameStarted}
                thinkingEnabled={
                  assignment !== null &&
                  readModelConfig(assignment)?.thinkingEnabled === true
                }
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
                effects={seatEffects[seatIndex + 1]}
                disabled={gameStarted}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
      </div>
      {!gameStarted && !isReplay && (
        <GameBottomActions
          allSeatsAssigned={allSeatsAssigned}
          allTestsPassed={allTestsPassed}
          canStartWithWarnings={allowStartWithWarnings || allTestsCompleted}
          isTesting={isTesting}
          isStartingGame={isStartingGame}
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

function ingestLiveSpectatorEffects(
  setEffects: Dispatch<SetStateAction<SpectatorEffect[]>>,
  setRecentEffects: Dispatch<SetStateAction<RecentSpectatorEffect[]>>,
  effects: SpectatorEffect[],
  seenAtByKey: EffectSeenAtMap,
  nowMs: number,
  terminal: boolean,
  live = true,
) {
  if (effects.length === 0) {
    return;
  }
  logSpectatorEffectsReceived(effects);
  if (terminal || !live) {
    expireTransientEffectSeenAt(effects, seenAtByKey, nowMs);
    setEffects((prev) => appendUniqueSpectatorEffects(prev, effects));
    setRecentEffects((prev) => (prev.length === 0 ? prev : []));
    return;
  }
  seedLiveEffectSeenAt(effects, seenAtByKey, nowMs);
  setEffects((prev) => appendUniqueSpectatorEffects(prev, effects));
  setRecentEffects((prev) => appendRecentSpectatorEffects(prev, effects, nowMs));
}

function isTerminalGameEvent(event: GameEvent) {
  return event.type === 'game_end' || event.type === 'role_reveal';
}

function logSpectatorEffectsReceived(effects: SpectatorEffect[]) {
  if (!import.meta.env.DEV || import.meta.env.MODE === 'test') {
    return;
  }
  for (const effect of effects) {
    if (effect.kind === 'death_reveal') {
      continue;
    }
    console.info('[spectator_effect received]', {
      kind: effect.kind,
      seq: effect.seq,
      target: effect.target_seat,
    });
  }
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

async function handleAudioTrigger(
  gameId: string,
  event: GameEvent,
  eventsRef: { current: GameEvent[] },
) {
  if (event.type !== 'phase_enter') {
    return;
  }
  const phase = String(event.payload.phase ?? event.phase);
  if (phase === 'NIGHT_START') {
    await playSequenceThenAck(gameId, phase, 'night_intro_done', [
      'wolf_howl',
      'night_guard',
    ], 1000);
  } else if (phase === 'NIGHT_WOLF_CHAT') {
    await playSequenceThenAck(gameId, phase, 'night_wolves_done', [
      'night_wolves',
    ], 1000);
  } else if (phase === 'NIGHT_WITCH') {
    await playSequenceThenAck(gameId, phase, 'night_witch_done', [
      'night_witch',
    ], 1000);
  } else if (phase === 'NIGHT_SEER') {
    await playSequenceThenAck(gameId, phase, 'night_seer_done', [
      'night_seer',
    ], 1000);
  } else if (phase === 'DAY_ANNOUNCE') {
    const hasDeath = eventsRef.current.some(
      (item) => item.day === event.day && item.type === 'death_at_night',
    );
    await playSequenceThenAck(gameId, phase, 'day_intro_done', [
      'day_rooster',
      'day_dawn',
      hasDeath ? 'day_death' : 'day_peaceful',
    ], 250);
  }
}

async function playSequenceThenAck(
  gameId: string,
  phase: string,
  ackEvent: string,
  sequence: Parameters<typeof gameAudio.playSequence>[0],
  gapMs: number,
) {
  try {
    await withTimeout(
      gameAudio.playSequence(sequence, gapMs),
      AUDIO_ACK_TIMEOUT_MS,
    );
  } catch {
    // Audio playback is best-effort; pacing must keep moving even if autoplay hangs.
  }
  await sendAck(gameId, phase, ackEvent).catch(() => undefined);
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
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
