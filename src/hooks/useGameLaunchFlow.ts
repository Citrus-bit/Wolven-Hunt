import { useCallback, type MutableRefObject } from 'react';
import type { LaunchState } from '../lib/gameLaunchState';
import { launchStateAfterSummary } from '../lib/gameLaunchState';
import {
  checkHealth,
  createGame,
  pauseGame,
  runGame,
  type HumanRole,
  type GameTimings,
} from '../lib/gameApi';
import { buildAgentSpecs } from '../lib/agentSpecs';
import { clearLiveGameSession, writeLiveGameSession } from '../lib/liveGameSession';
import {
  buildSeatPresentation,
  type SeatPresentationMap,
} from '../lib/seatPresentation';
import type { GameStage } from '../lib/gameStage';
import { readPromptEvolutionEnabled } from '../lib/evolutionSettings';

type LiveSessionSnapshotDraft = {
  gameId: string | null;
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  launchState: LaunchState;
  streamCursor: number;
  effectSeq: number;
  recentEffects: [];
  humanSeat?: number | null;
  playerToken?: string | null;
  humanRole?: HumanRole;
};

type UseGameLaunchFlowParams = {
  assignments: (number | null)[];
  humanSeatIndex: number | null;
  humanRole: HumanRole;
  isStartingGame: boolean;
  gameStarted: boolean;
  stage: GameStage;
  liveShellMountedRef: MutableRefObject<boolean>;
  pendingRunGameIdRef: MutableRefObject<string | null>;
  runStartedGameIdsRef: MutableRefObject<Set<string>>;
  liveSessionAbandonedRef: MutableRefObject<boolean>;
  liveSessionSnapshotRef: MutableRefObject<LiveSessionSnapshotDraft | {
    gameId: string | null;
    assignments: (number | null)[];
    seatPresentation: SeatPresentationMap;
    launchState: LaunchState;
    streamCursor: number;
    effectSeq: number;
    recentEffects: unknown[];
  }>;
  streamCursorRef: MutableRefObject<number>;
  effectSeqRef: MutableRefObject<number>;
  unlockAudio: () => unknown;
  setPickerSeat: (seat: number | null) => void;
  setSeatPresentation: (presentation: SeatPresentationMap) => void;
  setHumanContext: (context: { seat: number; token: string } | null) => void;
  setLaunchState: (state: LaunchState) => void;
  updateLaunchState: (
    next: LaunchState | ((current: LaunchState) => LaunchState),
  ) => void;
  setGameId: (gameId: string) => void;
  transitionToStage: (stage: GameStage) => void;
  setTestMessage: (message: string | null) => void;
  setTimings: (timings: GameTimings) => void;
  setCurrentPhase: (phase: string | null) => void;
  setStreamStatus: (status: 'idle' | 'connecting' | 'open' | 'error' | 'failed') => void;
};

export function useGameLaunchFlow({
  assignments,
  humanSeatIndex,
  humanRole,
  isStartingGame,
  gameStarted,
  stage,
  liveShellMountedRef,
  pendingRunGameIdRef,
  runStartedGameIdsRef,
  liveSessionAbandonedRef,
  liveSessionSnapshotRef,
  streamCursorRef,
  effectSeqRef,
  unlockAudio,
  setPickerSeat,
  setSeatPresentation,
  setHumanContext,
  setLaunchState,
  updateLaunchState,
  setGameId,
  transitionToStage,
  setTestMessage,
  setTimings,
  setCurrentPhase,
  setStreamStatus,
}: UseGameLaunchFlowParams) {
  const startGameWithAssignments = useCallback(async () => {
    if (isStartingGame || gameStarted) {
      return;
    }
    setPickerSeat(null);
    setHumanContext(null);
    updateLaunchState('connecting_service');
    setTestMessage('正在连接本地服务');
    const isHumanGame = humanSeatIndex !== null;
    const presentation = buildSeatPresentation(assignments, { humanSeatIndex });
    setSeatPresentation(presentation);
    transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
    try {
      void unlockAudio();
      const healthy = await checkHealth();
      if (liveSessionAbandonedRef.current) {
        return;
      }
      if (!healthy) {
        updateLaunchState('failed');
        setTestMessage('本地服务未连接，请先运行 make dev 或检查 7002 后端');
        return;
      }
      updateLaunchState('creating');
      setTestMessage('正在创建对局并接入模型');
      const agents = buildAgentSpecs(assignments, undefined, { humanSeatIndex });
      liveSessionSnapshotRef.current = {
        gameId: null,
        assignments,
        seatPresentation: presentation,
        launchState: 'creating',
        streamCursor: 0,
        effectSeq: 0,
        recentEffects: [],
        humanSeat: isHumanGame ? humanSeatIndex + 1 : null,
        playerToken: null,
        humanRole,
      };
      const created = await createGame({
        agents,
        pacing: 'live',
        startPaused: true,
        seatPresentation: presentation,
        evolutionEnabled: isHumanGame ? false : readPromptEvolutionEnabled(),
        humanSeat: isHumanGame ? humanSeatIndex + 1 : undefined,
        humanRole: isHumanGame ? humanRole : undefined,
      });
      if (isHumanGame && (!created.human_seat || !created.player_token)) {
        throw new Error('后端未返回真人座位 token');
      }
      if (liveSessionAbandonedRef.current) {
        clearLiveGameSession(created.game_id);
        void pauseGame(created.game_id).catch(() => undefined);
        return;
      }
      streamCursorRef.current = 0;
      effectSeqRef.current = 0;
      pendingRunGameIdRef.current = created.game_id;
      const nextHumanContext =
        isHumanGame && created.human_seat && created.player_token
          ? { seat: created.human_seat, token: created.player_token }
          : null;
      setHumanContext(nextHumanContext);
      const createdSnapshot = {
        gameId: created.game_id,
        assignments,
        seatPresentation: presentation,
        launchState: 'connecting_stream' as const,
        streamCursor: 0,
        effectSeq: 0,
        recentEffects: [],
        humanSeat: nextHumanContext?.seat ?? null,
        playerToken: nextHumanContext?.token ?? null,
        humanRole,
      };
      liveSessionSnapshotRef.current = createdSnapshot;
      writeLiveGameSession(createdSnapshot);
      setLaunchState('connecting_stream');
      setGameId(created.game_id);
    } catch (caught) {
      if (liveSessionAbandonedRef.current) {
        return;
      }
      updateLaunchState('failed');
      setTestMessage(caught instanceof Error ? caught.message : '创建游戏失败');
    }
  }, [
    assignments,
    effectSeqRef,
    gameStarted,
    humanRole,
    humanSeatIndex,
    isStartingGame,
    liveShellMountedRef,
    liveSessionAbandonedRef,
    liveSessionSnapshotRef,
    pendingRunGameIdRef,
    setGameId,
    setHumanContext,
    setLaunchState,
    setPickerSeat,
    setSeatPresentation,
    setTestMessage,
    stage.dayNumber,
    streamCursorRef,
    transitionToStage,
    unlockAudio,
    updateLaunchState,
  ]);

  const startPausedGameWhenReady = useCallback(
    async (id: string) => {
      if (liveSessionAbandonedRef.current) {
        return;
      }
      if (pendingRunGameIdRef.current !== id || runStartedGameIdsRef.current.has(id)) {
        return;
      }
      if (!liveShellMountedRef.current) {
        window.setTimeout(() => {
          void startPausedGameWhenReady(id);
        }, 50);
        return;
      }
      if (!claimPendingRunGame(id, pendingRunGameIdRef, runStartedGameIdsRef)) {
        return;
      }
      updateLaunchState('starting_backend');
      try {
        if (liveSessionAbandonedRef.current) {
          runStartedGameIdsRef.current.delete(id);
          return;
        }
        const summary = await runGame(id);
        if (liveSessionAbandonedRef.current) {
          return;
        }
        pendingRunGameIdRef.current = null;
        setTimings(summary.timings);
        setCurrentPhase(summary.phase);
        if (summary.status === 'failed') {
          updateLaunchState('failed');
          setStreamStatus('failed');
        } else {
          updateLaunchState((current) => {
            const afterSummary = launchStateAfterSummary(current, summary);
            if (afterSummary !== current) {
              return afterSummary;
            }
            return current === 'creating' ? 'starting_backend' : current;
          });
        }
      } catch (error) {
        runStartedGameIdsRef.current.delete(id);
        updateLaunchState('failed');
        setStreamStatus('error');
        setTestMessage(error instanceof Error ? error.message : '启动游戏失败');
      }
    },
    [
      liveSessionAbandonedRef,
      pendingRunGameIdRef,
      runStartedGameIdsRef,
      liveShellMountedRef,
      setCurrentPhase,
      setStreamStatus,
      setTestMessage,
      setTimings,
      updateLaunchState,
    ],
  );

  return {
    startGameWithAssignments,
    startPausedGameWhenReady,
  };
}

export function claimPendingRunGame(
  id: string,
  pendingRunGameIdRef: MutableRefObject<string | null>,
  runStartedGameIdsRef: MutableRefObject<Set<string>>,
) {
  if (pendingRunGameIdRef.current !== id || runStartedGameIdsRef.current.has(id)) {
    return false;
  }
  runStartedGameIdsRef.current.add(id);
  return true;
}
