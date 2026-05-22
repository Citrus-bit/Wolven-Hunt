import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from 'react';
import { INITIAL_STAGE, type GameStage } from '../../lib/gameStage';
import {
  createGame,
  getGame,
  getNarrative,
  sendAck,
  subscribeGameEvents,
  type AgentSpec,
  type GameEvent,
  type GameTimings,
  type NarrativeRow,
} from '../../lib/gameApi';
import { gameAudio } from '../../lib/gameAudio';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  readModelConfig,
  testModelConnection,
  type ModelTestResult,
} from '../../lib/modelTest';
import { ExitConfirmModal } from './ExitConfirmModal';
import { FinalRevealOverlay } from './FinalRevealOverlay';
import { GameBottomActions } from './GameBottomActions';
import { GameChat } from './GameChat';
import { GamePhaseHeader } from './GamePhaseHeader';
import { GameSeat } from './GameSeat';
import { GameTopBar } from './GameTopBar';
import { KnightDuelBanner } from './KnightDuelBanner';
import { ModelPicker } from './ModelPicker';
import { RulesModal } from './RulesModal';
import { StageIndicator } from './StageIndicator';
import { toNarrative } from '../../lib/narrative';

const SEAT_COUNT = 8;
const MIN_TESTING_MS = 800;
const leftSeats = [0, 1, 2, 3];
const rightSeats = [4, 5, 6, 7];
type BgPhase = 'idle' | 'fade-out' | 'fade-in';

type GamePageProps = {
  onExitGame: () => void;
};

function shuffledModelSlots() {
  const slots = MODEL_SLOTS.map((slot) => slot.slot);

  for (let index = slots.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [slots[index], slots[swapIndex]] = [slots[swapIndex], slots[index]];
  }

  return slots;
}

export function GamePage({ onExitGame }: GamePageProps) {
  const [gameId, setGameId] = useState<string | null>(null);
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
  const [timings, setTimings] = useState<GameTimings | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    'idle' | 'connecting' | 'open' | 'error'
  >('idle');
  const [isStartingGame, setIsStartingGame] = useState(false);
  const [knightDuelActive, setKnightDuelActive] = useState(false);

  const allSeatsAssigned = assignments.every(
    (assignment) => assignment !== null,
  );
  const allTestsPassed =
    allSeatsAssigned &&
    assignments.every(
      (slotIndex) =>
        slotIndex !== null && testResults[slotIndex]?.status === 'pass',
    );
  const bgSrc =
    stage.phase === 'day' ? '/assets/game/day_bg.png' : '/assets/game/night_bg.png';
  const gameStarted = gameId !== null;
  const currentSpeakerSeat = currentPhase === 'DAY_SPEECH'
    ? [...events].reverse().find((event) => event.type === 'speech')?.actor ?? null
    : null;
  const deadSeats = deriveDeadSeats(events);

  useEffect(() => {
    try {
      const volume = Number(window.localStorage.getItem('wolven_hunt.lobby.volume') ?? '80');
      const muted = window.localStorage.getItem('wolven_hunt.lobby.muted') === 'true';
      gameAudio.setVolume(Number.isFinite(volume) ? volume / 100 : 0.8);
      gameAudio.setMuted(muted);
    } catch {
      gameAudio.setVolume(0.8);
    }
    return () => gameAudio.stopAll();
  }, []);

  useEffect(() => {
    if (!gameId) {
      setStreamStatus('idle');
      setCurrentPhase(null);
      return undefined;
    }

    setEvents([]);
    eventsRef.current = [];
    setNarrativeRows([]);
    narrativeSeqRef.current = 0;
    setCurrentPhase(null);
    setStreamStatus('connecting');
    const source = subscribeGameEvents(
      gameId,
      (event) => {
        setStreamStatus('open');
        if (event.type === 'phase_enter') {
          setCurrentPhase(String(event.payload.phase ?? event.phase));
        }
        if (event.type === 'knight_challenge') {
          setKnightDuelActive(true);
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
        setStreamStatus('error');
        void getGame(gameId).then((summary) => {
          setCurrentPhase(summary.phase);
          setTimings(summary.timings);
        }).catch(() => undefined);
        void getNarrative(gameId, narrativeSeqRef.current)
          .then((rows) => rows.forEach((row) => {
            narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
            appendNarrativeRow(setNarrativeRows, row);
          }))
          .catch(() => undefined);
      },
      (row) => {
        narrativeSeqRef.current = Math.max(narrativeSeqRef.current, row.seq);
        appendNarrativeRow(setNarrativeRows, row);
      },
    );

    return () => source.close();
  }, [gameId]);

  useEffect(() => {
    if (!gameId) {
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
  }, [gameId]);

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
            result: {
              status: 'fail',
              errorMessage: '配置缺失',
            } satisfies ModelTestResult,
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
    setTestMessage(
      passCount === assignedSlots.length
        ? '全部模型连通性测试通过'
        : `${passCount}/${assignedSlots.length} 个模型连通性测试通过，请检查标记为 ✕ 的模型配置`,
    );
    setIsTesting(false);
  };

  const handleClickEnterNight = async () => {
    if (!allTestsPassed || isStartingGame || gameStarted) {
      return;
    }
    setPickerSeat(null);
    setIsStartingGame(true);
    setTestMessage('正在创建对局并接入模型');
    try {
      const agents = buildAgentSpecs(assignments);
      const created = await createGame({ agents, pacing: 'live' });
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

  const handleKnightDuelDone = () => {
    setKnightDuelActive(false);
    if (gameId) {
      void sendAck(gameId, 'DAY_KNIGHT_INTERRUPT', 'knight_duel_done');
    }
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
      />
      <StageIndicator stage={stage} />
      {gameStarted && (
        <GamePhaseHeader
          phase={currentPhase}
          timings={timings}
          speakerSeat={currentSpeakerSeat}
        />
      )}
      <GameChat
        events={events}
        narrativeRows={narrativeRows}
        assignments={assignments}
        streamStatus={streamStatus}
      />
      {!gameStarted && (
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
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!gameStarted}
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
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
                testStatus={
                  assignment !== null
                    ? testResults[assignment]?.status
                    : undefined
                }
                showTestBadge={!gameStarted}
                speaking={currentSpeakerSeat === seatIndex + 1}
                dead={deadSeats.has(seatIndex + 1)}
                disabled={gameStarted}
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
      </div>
      {!gameStarted && (
        <GameBottomActions
          allSeatsAssigned={allSeatsAssigned}
          allTestsPassed={allTestsPassed}
          isTesting={isTesting}
          isStartingGame={isStartingGame}
          testMessage={testMessage}
          onClickTest={handleClickTest}
          onClickEnterNight={handleClickEnterNight}
        />
      )}
      {import.meta.env.DEV && !gameStarted && (
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
      <KnightDuelBanner active={knightDuelActive} onDone={handleKnightDuelDone} />
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

function buildAgentSpecs(assignments: (number | null)[]): Record<number, AgentSpec> {
  const agents: Record<number, AgentSpec> = {};
  assignments.forEach((slotIndex, seatIndex) => {
    if (slotIndex === null) {
      throw new Error(`第 ${seatIndex + 1} 号席位尚未分配模型`);
    }
    const config = readModelConfig(slotIndex);
    if (!config) {
      throw new Error(`${MODEL_SLOTS[slotIndex]?.nickname ?? '模型'} 配置缺失`);
    }
    agents[seatIndex + 1] = {
      kind: 'llm',
      provider: 'litellm',
      model: config.modelName,
      base_url: config.baseUrl,
      api_key: config.apiKey,
    };
  });
  return agents;
}

function deriveDeadSeats(events: GameEvent[]) {
  const dead = new Set<number>();
  for (const event of events) {
    if (event.type === 'death_at_night' || event.type === 'exile') {
      const seat = Number(event.payload.seat);
      if (Number.isFinite(seat)) {
        dead.add(seat);
      }
    }
    if (event.type === 'knight_result') {
      const killed = Number(event.payload.killed);
      if (Number.isFinite(killed)) {
        dead.add(killed);
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
    } else if (phase === 'NIGHT_SEER') {
      await sendAck(gameId, phase, 'night_seer_done').catch(() => undefined);
    } else if (phase === 'DAY_ANNOUNCE') {
      await sendAck(gameId, phase, 'day_intro_done').catch(() => undefined);
    }
  }
}
