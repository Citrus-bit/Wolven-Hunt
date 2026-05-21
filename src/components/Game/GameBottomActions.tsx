type GameBottomActionsProps = {
  allSeatsAssigned: boolean;
  allTestsPassed: boolean;
  isTesting: boolean;
  testMessage?: string | null;
  onClickTest: () => void;
  onClickEnterNight: () => void;
};

export function GameBottomActions({
  allSeatsAssigned,
  allTestsPassed,
  isTesting,
  testMessage,
  onClickTest,
  onClickEnterNight,
}: GameBottomActionsProps) {
  const testDisabled = !allSeatsAssigned || isTesting;
  const enterDisabled = !allSeatsAssigned || !allTestsPassed || isTesting;

  return (
    <div className="game-bottom-actions">
      <button
        type="button"
        className="game-bottom-btn game-bottom-btn--test"
        disabled={testDisabled}
        onClick={onClickTest}
      >
        {isTesting ? '正在测试中' : '测试模型连通性'}
      </button>
      <button
        type="button"
        className="game-bottom-btn game-bottom-btn--night"
        disabled={enterDisabled}
        onClick={onClickEnterNight}
      >
        夜深了…
      </button>
      {testMessage && (
        <p className="game-test-status" role="status" aria-live="polite">
          {testMessage}
        </p>
      )}
    </div>
  );
}
