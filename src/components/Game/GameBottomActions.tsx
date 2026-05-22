type GameBottomActionsProps = {
  allSeatsAssigned: boolean;
  allTestsPassed: boolean;
  isTesting: boolean;
  isStartingGame?: boolean;
  testMessage?: string | null;
  onClickTest: () => void;
  onClickEnterNight: () => void;
};

export function GameBottomActions({
  allSeatsAssigned,
  allTestsPassed,
  isTesting,
  isStartingGame = false,
  testMessage,
  onClickTest,
  onClickEnterNight,
}: GameBottomActionsProps) {
  const isNightReady = allSeatsAssigned && allTestsPassed && !isTesting && !isStartingGame;
  const actionDisabled = !allSeatsAssigned || isTesting || isStartingGame;
  const actionLabel = isNightReady
    ? '夜深了...'
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
    </div>
  );
}
