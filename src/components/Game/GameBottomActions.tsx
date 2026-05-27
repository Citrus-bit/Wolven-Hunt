import type { ModelTestStatus } from '../../lib/modelTest';

export type ModelTestTimingRow = {
  seat: number;
  nickname: string;
  modelName: string;
  status: ModelTestStatus;
  errorMessage?: string;
  durationMs: number;
  startedOffsetMs: number;
  finishedOffsetMs: number;
};

type GameBottomActionsProps = {
  allSeatsAssigned: boolean;
  allTestsPassed: boolean;
  canStartWithWarnings: boolean;
  isTesting: boolean;
  isStartingGame?: boolean;
  startingLabel?: string;
  testMessage?: string | null;
  testFailures?: readonly string[];
  testTimings?: readonly ModelTestTimingRow[];
  onClickTest: () => void;
  onClickEnterNight: () => void;
};

export function GameBottomActions({
  allSeatsAssigned,
  allTestsPassed,
  canStartWithWarnings,
  isTesting,
  isStartingGame = false,
  startingLabel = '正在创建对局',
  testMessage,
  testFailures = [],
  testTimings = [],
  onClickTest,
  onClickEnterNight,
}: GameBottomActionsProps) {
  const isNightReady =
    allSeatsAssigned &&
    (allTestsPassed || canStartWithWarnings) &&
    !isTesting &&
    !isStartingGame;
  const actionDisabled = !allSeatsAssigned || isTesting || isStartingGame;
  const actionLabel = isNightReady
    ? allTestsPassed
      ? '夜深了...'
      : '仍然开局'
    : isStartingGame
      ? startingLabel
      : isTesting
        ? '正在测试中'
      : '测试模型连通性';
  const actionClassName = [
    'game-bottom-btn',
    isNightReady ? 'game-bottom-btn--night-ready' : 'game-bottom-btn--test',
  ].join(' ');
  const handleClickAction = isNightReady ? onClickEnterNight : onClickTest;
  const sortedTimings = [...testTimings].sort(
    (left, right) => right.durationMs - left.durationMs,
  );

  return (
    <div className="game-bottom-actions">
      <button
        type="button"
        className={actionClassName}
        disabled={actionDisabled}
        onClick={handleClickAction}
      >
        {actionLabel}
      </button>
      {testMessage && (
        <p className="game-test-status" role="status" aria-live="polite">
          {testMessage}
        </p>
      )}
      {testFailures.length > 0 && (
        <ul className="game-test-failures" aria-label="模型测试失败详情">
          {testFailures.map((failure) => (
            <li key={failure}>{failure}</li>
          ))}
        </ul>
      )}
      {sortedTimings.length > 0 && (
        <div className="game-test-timings" aria-label="模型连通性耗时表">
          <div className="game-test-timings-header">
            <span>模型</span>
            <span>结果</span>
            <span>开始</span>
            <span>结束</span>
            <span>耗时</span>
          </div>
          {sortedTimings.map((timing, index) => (
            <div
              className="game-test-timings-row"
              key={`${timing.seat}-${timing.modelName}`}
            >
              <span className="game-test-timings-model">
                <span>{timing.seat}号 {timing.nickname}</span>
                <small>{timing.modelName}</small>
              </span>
              <span
                className={[
                  'game-test-timings-result',
                  timing.status === 'pass'
                    ? 'game-test-timings-result--pass'
                    : 'game-test-timings-result--fail',
                ].join(' ')}
              >
                {timing.status === 'pass' ? '通过' : '失败'}
              </span>
              <span>{formatTimingSeconds(timing.startedOffsetMs)}</span>
              <span>{formatTimingSeconds(timing.finishedOffsetMs)}</span>
              <span className="game-test-timings-duration">
                {formatTimingSeconds(timing.durationMs)}
                {index === 0 && <b>最慢</b>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatTimingSeconds(ms: number) {
  return `${Math.max(0, ms / 1000).toFixed(2)}s`;
}
