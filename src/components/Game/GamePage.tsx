import { useRef, useState } from 'react';
import { INITIAL_STAGE, type GameStage } from '../../lib/gameStage';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  readModelConfig,
  testModelConnection,
  type ModelTestResult,
} from '../../lib/modelTest';
import { ExitConfirmModal } from './ExitConfirmModal';
import { GameBottomActions } from './GameBottomActions';
import { GameChat } from './GameChat';
import { GameSeat } from './GameSeat';
import { GameTopBar } from './GameTopBar';
import { ModelPicker } from './ModelPicker';
import { RulesModal } from './RulesModal';
import { StageIndicator } from './StageIndicator';

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

  const handleClickSeat = (seatIndex: number) => {
    if (isTesting) {
      return;
    }

    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null) {
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
    if (pickerSeat === null || isTesting) {
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
    if (isTesting) {
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
    if (!allSeatsAssigned || isTesting) {
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

  const handleClickEnterNight = () => {
    transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
  };

  const handleConfirmExit = () => {
    setExitConfirmOpen(false);
    onExitGame();
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
      <GameChat />
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
                onClickSeat={handleClickSeat}
              />
            );
          })}
        </div>
      </div>
      <GameBottomActions
        allSeatsAssigned={allSeatsAssigned}
        allTestsPassed={allTestsPassed}
        isTesting={isTesting}
        testMessage={testMessage}
        onClickTest={handleClickTest}
        onClickEnterNight={handleClickEnterNight}
      />
      {import.meta.env.DEV && (
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
      <ExitConfirmModal
        open={exitConfirmOpen}
        onClose={() => setExitConfirmOpen(false)}
        onConfirm={handleConfirmExit}
      />
    </main>
  );
}
