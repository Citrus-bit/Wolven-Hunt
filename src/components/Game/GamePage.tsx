import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from 'react';
import { INITIAL_STAGE, type GameStage } from '../../lib/gameStage';
import {
  createGame,
  getEffects,
  getEvents,
  getGame,
  getNarrative,
  sendAck,
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
  buildSeatEffectMap,
  deathRevealSeats,
  seedEffectSeenAt,
  type EffectSeenAtMap,
} from '../../lib/gameEffects';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  missingModelConfigResult,
  readModelConfig,
  testModelConnection,
  type ModelTestResult,
} from '../../lib/modelTest';
import { ExitConfirmModal } from './ExitConfirmModal';
import { FinalRevealOverlay } from './FinalRevealOverlay';
import { GameBottomActions } from './GameBottomActions';
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

const SEAT_COUNT = 10;
const MIN_TESTING_MS = 800;
const MAX_RECONNECT_ATTEMPTS = 5;
const PACING_STORAGE_KEY = 'wolven_hunt.pacing_mode';
const leftSeats = [0, 1, 2, 3, 4];
const rightSeats = [5, 6, 7, 8, 9];
type BgPhase = 'idle' | 'fade-out' | 'fade-in';
export type PacingMode = 'live' | 'fast' | 'off';

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

function readPacingMode(): PacingMode {
  try {
    const value = window.localStorage.getItem(PACING_STORAGE_KEY);
    if (value === 'live' || value === 'fast' || value === 'off') {
      return value;
    }
  } catch {
    // Local storage may be unavailable in restricted browser contexts.
  }
  return 'live';
}

export function GamePage({ onExitGame, replayGameId = null }: GamePageProps) {
  const [gameId, setGameId] = useState<string | null>(replayGameId);
  const [assignments, setAssignments] = useState<(number | null)[]>(() =>
    Array.from({ length: SEAT_COUNT }, () => null),
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
  const [spectatorEffects, setSpectatorEffects] = useState<SpectatorEffect[]>([]);
  const effectSeenAtRef = useRef<EffectSeenAtMap>({});
  const [effectClockMs, setEffectClockMs] = useState(() => Date.now());
  const effectSeqRef = useRef(0);
  const streamCursorRef = useRef(0);
  const [timings, setTimings] = useState<GameTimings | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    'idle' | 'connecting' | 'open' | 'error' | 'failed'
  >('idle');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [isStartingGame, setIsStartingGame] = useState(false);
  const [allowStartWithWarnings, setAllowStartWithWarnings] = useState(false);
  const [pacingMode, setPacingMode] = useState<PacingMode>(() => readPacingMode());
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
  const speechProgress = deriveDaySpeechProgress(events, currentPhase);
  const currentSpeakerSeat = speechProgress.nextSpeakerSeat;
  const seatEffects = buildSeatEffectMap(spectatorEffects, currentPhase, {
    nowMs: effectClockMs,
    seenAtByKey: effectSeenAtRef.current,
  });
  const deadSeats = deriveDeadSeats(events, spectatorEffects);
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

  useEffect(() => {
    gameAudio.preload();
    preloadGameEffectAssets();
    return () => gameAudio.stopAll();
  }, []);

  useEffect(() => {
    const nowMs = Date.now();
    seedEffectSeenAt(spectatorEffects, effectSeenAtRef.current, nowMs);
    setEffectClockMs(nowMs);
  }, [spectatorEffects]);

  useEffect(() => {
    if (spectatorEffects.length === 0) {
      return undefined;
    }
    const timer = window.setInterval(() => setEffectClockMs(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [spectatorEffects.length]);

  useEffect(() => {
    if (!isReplay || !replayGameId) {
      return undefined;
    }
    let cancelled = false;
    setStreamStatus('connecting');
    Promise.all([getEvents(replayGameId), getEffects(replayGameId)])
      .then(([loadedEvents, loadedEffects]) => {
        if (cancelled) {
          return;
        }
        setGameId(replayGameId);
        setEvents(loadedEvents);
        eventsRef.current = loadedEvents;
        setSpectatorEffects(loadedEffects);
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
        const lastPhaseEnter = [...loadedEvents]
          .reverse()
          .find((event) => event.type === 'phase_enter');
        if (lastPhaseEnter) {
          const phase = String(lastPhaseEnter.payload.phase ?? lastPhaseEnter.phase);
          setCurrentPhase(phase);
          setStage({
            dayNumber: lastPhaseEnter.day,
            phase: phase.startsWith('NIGHT') ? 'night' : 'day',
          });
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
    effectSeenAtRef.current = {};
    setEffectClockMs(Date.now());
    effectSeqRef.current = 0;
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
            if (summary.status === 'failed') {
              setStreamStatus('failed');
            }
          }).catch(() => undefined);
          void getNarrative(gameId, narrativeSeqRef.current)
            .then((rows) => rows.forEach((row) => {
              narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
              streamCursorRef.current = Math.max(streamCursorRef.current, row.seq);
              appendNarrativeRow(setNarrativeRows, row);
            }))
            .catch(() => undefined);
          void getEffects(gameId, effectSeqRef.current)
            .then((effects) => effects.forEach((effect) => {
              effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
              streamCursorRef.current = Math.max(streamCursorRef.current, effect.seq);
              appendSpectatorEffect(setSpectatorEffects, effect);
            }))
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
          const jitter = Math.floor(Math.random() * 1000);
          reconnectTimer = window.setTimeout(() => {
            connect(streamCursorRef.current || lastSeq, nextAttempt);
          }, 2000 + jitter);
        },
        (row) => {
          narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
          streamCursorRef.current = Math.max(streamCursorRef.current, row.seq);
          appendNarrativeRow(setNarrativeRows, row);
        },
        (effect) => {
          effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
          streamCursorRef.current = Math.max(streamCursorRef.current, effect.seq);
          appendSpectatorEffect(setSpectatorEffects, effect);
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
    const lastPhaseEnter = [...events]
      .reverse()
      .find((event) => event.type === 'phase_enter');
    if (!lastPhaseEnter || bgPhase !== 'idle') {
      return;
    }
    const phase = String(lastPhaseEnter.payload.phase ?? lastPhaseEnter.phase);
    const nextPhase = phase.startsWith('NIGHT') ? 'night' : 'day';
    if (stage.dayNumber !== lastPhaseEnter.day || stage.phase !== nextPhase) {
      transitionToStage({ dayNumber: lastPhaseEnter.day, phase: nextPhase });
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
    const startedAt = window.performance.now();

    const testTasks = assignedSlots.map(async (slotIndex) => {
      try {
        const config = readModelConfig(slotIndex);
        if (!config) {
          return {
            slotIndex,
            result: missingModelConfigResult(),
          };
        }

        const result = await testModelConnection(config);
        return { slotIndex, result };
      } catch (error) {
        const message = error instanceof Error ? error.message : '未知错误';
        return {
          slotIndex,
          result: {
            status: 'fail',
            errorMessage: message.slice(0, 80),
          } satisfies ModelTestResult,
        };
      } finally {
        completedCount += 1;
        setTestMessage(`正在测试 ${completedCount}/${assignedSlots.length}`);
      }
      });

    const settledResults = await Promise.allSettled(testTasks);
    const elapsed = window.performance.now() - startedAt;
    if (elapsed < MIN_TESTING_MS) {
      await new Promise((resolve) =>
        window.setTimeout(resolve, MIN_TESTING_MS - elapsed),
      );
    }

    const nextResults: Record<number, ModelTestResult> = {};
    assignedSlots.forEach((slotIndex) => {
      nextResults[slotIndex] = {
        status: 'fail',
        errorMessage: '测试未返回结果',
      };
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
      const created = await createGame({ agents, pacing: pacingMode });
      setGameId(created.game_id);
      transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
    } catch (caught) {
      setTestMessage(caught instanceof Error ? caught.message : '创建游戏失败');
    } finally {
      setIsStartingGame(false);
    }
  };

  const handleConfirmExit = () => {
    gameAudio.stopAll();
    setExitConfirmOpen(false);
    onExitGame();
  };

  const handleChangePacingMode = (mode: PacingMode) => {
    if (gameStarted) {
      return;
    }
    setPacingMode(mode);
    try {
      window.localStorage.setItem(PACING_STORAGE_KEY, mode);
    } catch {
      // Local storage is optional; the in-memory selection still applies.
    }
  };

  const handleToggleGameAudio = () => {
    if (gameAudioControls.playError && !gameAudioControls.muted) {
      void gameAudioControls.unlock();
      return;
    }
    gameAudioControls.toggleMuted();
  };

  return (
    <main className="game-page" aria-label="Wolven Hunt 游戏">
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
        pacingMode={pacingMode}
        gameStarted={gameStarted}
        gameAudioMuted={gameAudioControls.muted}
        gameAudioError={gameAudioControls.playError}
        onChangePacingMode={handleChangePacingMode}
        onToggleGameAudio={handleToggleGameAudio}
      />
      <StageIndicator stage={stage} />
      {gameStarted && (
        <GamePhaseHeader
          phase={currentPhase}
          timings={timings}
          speakerSeat={currentSpeakerSeat}
          speechComplete={speechProgress.complete}
        />
      )}
      <GameChat
        events={events}
        narrativeRows={narrativeRows}
        assignments={assignments}
        streamStatus={streamStatus}
      />
      <GameEffectsLayer effects={spectatorEffects} />
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
                role={seatRoles[seatIndex + 1] ?? null}
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!gameStarted}
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
                role={seatRoles[seatIndex + 1] ?? null}
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!gameStarted}
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
          onClickTest={handleClickTest}
          onClickEnterNight={handleClickEnterNight}
        />
      )}
      {import.meta.env.DEV && !gameStarted && !isReplay && (
        <button
          type="button"
          className="game-stage-debug"
          onClick={() => {
            transitionToStage(
              stage.phase === 'day'
                ? { dayNumber: stage.dayNumber, phase: 'night' }
                : { dayNumber: stage.dayNumber + 1, phase: 'day' },
            );
          }}
        >
          [debug] 推进
        </button>
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
      <FinalRevealOverlay
        gameId={gameId}
        events={events}
        assignments={assignments}
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

function appendSpectatorEffect(
  setEffects: Dispatch<SetStateAction<SpectatorEffect[]>>,
  effect: SpectatorEffect,
) {
  setEffects((prev) => {
    if (
      prev.some(
        (existing) =>
          existing.seq === effect.seq &&
          existing.kind === effect.kind &&
          existing.target_seat === effect.target_seat &&
          existing.asset_key === effect.asset_key,
      )
    ) {
      return prev;
    }
    return [...prev, effect];
  });
}

function deriveDeadSeats(events: GameEvent[], effects: SpectatorEffect[]) {
  const dead = deathRevealSeats(effects);
  for (const event of events) {
    if (event.type === 'exile') {
      const seat = Number(event.payload.seat);
      if (Number.isFinite(seat)) {
        dead.add(seat);
      }
    }
    if (event.type === 'role_reveal' && Array.isArray(event.payload.seats)) {
      for (const seat of event.payload.seats) {
        if (
          typeof seat === 'object' &&
          seat !== null &&
          'seat' in seat &&
          'alive' in seat &&
          !seat.alive
        ) {
          dead.add(Number(seat.seat));
        }
      }
    }
  }
  return dead;
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
  try {
    if (phase === 'NIGHT_START') {
      await gameAudio.playSequence(['wolf_howl', 'night_guard'], 1000);
      await sendAck(gameId, phase, 'night_intro_done');
    } else if (phase === 'NIGHT_WOLF_CHAT') {
      await gameAudio.playSequence(['night_wolves'], 1000);
      await sendAck(gameId, phase, 'night_wolves_done');
    } else if (phase === 'NIGHT_WITCH') {
      await gameAudio.playSequence(['night_witch'], 1000);
      await sendAck(gameId, phase, 'night_witch_done');
    } else if (phase === 'NIGHT_SEER') {
      await gameAudio.playSequence(['night_seer'], 1000);
      await sendAck(gameId, phase, 'night_seer_done');
    } else if (phase === 'DAY_ANNOUNCE') {
      const hasDeath = eventsRef.current.some(
        (item) => item.day === event.day && item.type === 'death_at_night',
      );
      await gameAudio.playSequence(
        ['day_rooster', 'day_dawn', hasDeath ? 'day_death' : 'day_peaceful'],
        250,
      );
      await sendAck(gameId, phase, 'day_intro_done');
    }
  } catch {
    if (phase === 'NIGHT_START') {
      await sendAck(gameId, phase, 'night_intro_done').catch(() => undefined);
    } else if (phase === 'NIGHT_WOLF_CHAT') {
      await sendAck(gameId, phase, 'night_wolves_done').catch(() => undefined);
    } else if (phase === 'NIGHT_WITCH') {
      await sendAck(gameId, phase, 'night_witch_done').catch(() => undefined);
    } else if (phase === 'NIGHT_SEER') {
      await sendAck(gameId, phase, 'night_seer_done').catch(() => undefined);
    } else if (phase === 'DAY_ANNOUNCE') {
      await sendAck(gameId, phase, 'day_intro_done').catch(() => undefined);
    }
  }
}
