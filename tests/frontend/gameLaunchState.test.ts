import { describe, expect, it } from 'vitest';
import {
  isPendingRunLaunchState,
  isStartupPendingLaunchState,
  launchStateAfterPhase,
} from '../../src/lib/gameLaunchState';

describe('gameLaunchState', () => {
  it('shows startup feedback only during the live startup handshake', () => {
    expect(
      isStartupPendingLaunchState('connecting_stream', {
        isReplay: false,
        gameStarted: true,
        finished: false,
      }),
    ).toBe(true);
    expect(
      isStartupPendingLaunchState('starting_backend', {
        isReplay: false,
        gameStarted: true,
        finished: false,
      }),
    ).toBe(true);
    expect(
      isStartupPendingLaunchState('running', {
        isReplay: false,
        gameStarted: true,
        finished: false,
      }),
    ).toBe(false);
  });

  it('clears startup feedback after the first formal game phase arrives', () => {
    expect(launchStateAfterPhase('starting_backend', 'GAME_START')).toBe(
      'starting_backend',
    );
    expect(launchStateAfterPhase('starting_backend', 'NIGHT_START')).toBe('running');
    expect(launchStateAfterPhase('connecting_stream', 'NIGHT_GUARD')).toBe('running');
  });

  it('identifies restored sessions that still need the run handshake', () => {
    expect(isPendingRunLaunchState('connecting_stream')).toBe(true);
    expect(isPendingRunLaunchState('starting_backend')).toBe(true);
    expect(isPendingRunLaunchState('running')).toBe(false);
  });
});
