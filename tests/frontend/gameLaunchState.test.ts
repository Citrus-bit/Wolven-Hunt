import { describe, expect, it } from 'vitest';
import {
  isPendingRunLaunchState,
  isStartupPendingLaunchState,
  launchStateAfterPhase,
  launchStateAfterSummary,
  startupMessageForLaunchState,
} from '../../src/lib/gameLaunchState';

describe('gameLaunchState', () => {
  it('shows startup feedback only during the live startup handshake', () => {
    expect(
      isStartupPendingLaunchState('connecting_service', {
        isReplay: false,
        gameStarted: false,
        finished: false,
      }),
    ).toBe(false);
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

  it('clears startup feedback from a running backend summary with a playable phase', () => {
    expect(
      launchStateAfterSummary('starting_backend', {
        status: 'running',
        phase: 'NIGHT_START',
      }),
    ).toBe('running');
    expect(
      launchStateAfterSummary('starting_backend', {
        status: 'running',
        phase: 'GAME_START',
      }),
    ).toBe('running');
    expect(
      launchStateAfterSummary('starting_backend', {
        status: 'failed',
        phase: 'NIGHT_START',
      }),
    ).toBe('failed');
  });

  it('identifies restored sessions that still need the run handshake', () => {
    expect(isPendingRunLaunchState('connecting_service')).toBe(false);
    expect(isPendingRunLaunchState('connecting_stream')).toBe(true);
    expect(isPendingRunLaunchState('starting_backend')).toBe(true);
    expect(isPendingRunLaunchState('running')).toBe(false);
  });

  it('labels service connection separately from game startup', () => {
    expect(startupMessageForLaunchState('connecting_service')).toBe('正在连接本地服务');
    expect(startupMessageForLaunchState('creating')).toBe('正在创建对局');
    expect(startupMessageForLaunchState('connecting_stream')).toBe('正在启动对局');
    expect(startupMessageForLaunchState('starting_backend')).toBe('正在启动对局');
  });
});
