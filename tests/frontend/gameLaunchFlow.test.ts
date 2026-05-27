import { describe, expect, it } from 'vitest';
import { claimPendingRunGame } from '../../src/hooks/useGameLaunchFlow';

describe('game launch flow', () => {
  it('claims a pending run only once across open and stream_ready triggers', () => {
    const pendingRunGameIdRef = { current: 'game-1' };
    const runStartedGameIdsRef = { current: new Set<string>() };

    expect(
      claimPendingRunGame('game-1', pendingRunGameIdRef, runStartedGameIdsRef),
    ).toBe(true);
    expect(
      claimPendingRunGame('game-1', pendingRunGameIdRef, runStartedGameIdsRef),
    ).toBe(false);
    expect(claimPendingRunGame('game-2', pendingRunGameIdRef, runStartedGameIdsRef)).toBe(
      false,
    );
    expect([...runStartedGameIdsRef.current]).toEqual(['game-1']);
  });
});
