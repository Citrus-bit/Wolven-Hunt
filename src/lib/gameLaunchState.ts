export type LaunchState =
  | 'idle'
  | 'connecting_service'
  | 'creating'
  | 'connecting_stream'
  | 'starting_backend'
  | 'running'
  | 'failed';

export function isStartupPendingLaunchState(
  launchState: LaunchState,
  opts: { isReplay: boolean; gameStarted: boolean; finished: boolean },
) {
  return (
    !opts.isReplay &&
    opts.gameStarted &&
    !opts.finished &&
    (launchState === 'connecting_stream' || launchState === 'starting_backend')
  );
}

export function isPendingRunLaunchState(launchState: LaunchState) {
  return launchState === 'connecting_stream' || launchState === 'starting_backend';
}

export function launchStateAfterPhase(
  launchState: LaunchState,
  phase: string | null,
) {
  if (
    (launchState === 'connecting_stream' || launchState === 'starting_backend') &&
    phase !== null &&
    phase !== 'GAME_START'
  ) {
    return 'running';
  }
  return launchState;
}

export function startupMessageForLaunchState(launchState: LaunchState) {
  if (launchState === 'connecting_service') {
    return '正在连接本地服务';
  }
  if (launchState === 'creating') {
    return '正在创建对局';
  }
  if (launchState === 'connecting_stream' || launchState === 'starting_backend') {
    return '正在启动对局';
  }
  return '等待游戏开始';
}
