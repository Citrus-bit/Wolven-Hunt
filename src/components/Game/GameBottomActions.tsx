type GameBottomActionsProps = {
  allSeatsAssigned: boolean;
  allTestsPassed: boolean;
  canStartWithWarnings: boolean;
  isTesting: boolean;
  isStartingGame?: boolean;
  testMessage?: string | null;
  testFailures?: readonly string[];
  onClickTest: () => void;
  onClickEnterNight: () => void;
};

export function GameBottomActions({
  allSeatsAssigned,
  allTestsPassed,
  canStartWithWarnings,
  isTesting,
  isStartingGame = false,
  testMessage,
  testFailures = [],
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
      ? '正在创建对局'
      : isTesting
        ? '正在测试中'
      : '测试模型连通性';
  const actionClassName = [
    'game-bottom-btn',
    isNightReady ? 'game-bottom-btn--night-ready' : 'game-bottom-btn--test',
  ].join(' ');
  const handleClickAction = isNightReady ? onClickEnterNight : onClickTest;

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
    </div>
  );
}
