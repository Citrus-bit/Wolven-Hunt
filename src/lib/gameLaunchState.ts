export type LaunchState =
  | 'idle'
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
