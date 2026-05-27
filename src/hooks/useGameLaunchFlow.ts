import { useCallback, type MutableRefObject } from 'react';
import {
  launchStateAfterPhase,
  type LaunchState,
} from '../lib/gameLaunchState';
import { checkHealth, createGame, runGame, type GameTimings } from '../lib/gameApi';
import { buildAgentSpecs } from '../lib/agentSpecs';
import { writeLiveGameSession } from '../lib/liveGameSession';
import {
  buildSeatPresentation,
  type SeatPresentationMap,
} from '../lib/seatPresentation';
import type { GameStage } from '../lib/gameStage';

type LiveSessionSnapshotDraft = {
  gameId: string | null;
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  launchState: LaunchState;
  streamCursor: number;
  effectSeq: number;
  recentEffects: [];
};

type UseGameLaunchFlowParams = {
  assignments: (number | null)[];
  isStartingGame: boolean;
  gameStarted: boolean;
  stage: GameStage;
  pendingRunGameIdRef: MutableRefObject<string | null>;
  runStartedGameIdsRef: MutableRefObject<Set<string>>;
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
  isStartingGame,
  gameStarted,
  stage,
  pendingRunGameIdRef,
  runStartedGameIdsRef,
  liveSessionSnapshotRef,
  streamCursorRef,
  effectSeqRef,
  unlockAudio,
  setPickerSeat,
  setSeatPresentation,
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
    updateLaunchState('connecting_service');
    setTestMessage('正在连接本地服务');
    try {
      void unlockAudio();
      const healthy = await checkHealth();
      if (!healthy) {
        updateLaunchState('failed');
        setTestMessage('本地服务未连接，请先运行 make dev 或检查 7002 后端');
        return;
      }
      updateLaunchState('creating');
      setTestMessage('正在创建对局并接入模型');
      const agents = buildAgentSpecs(assignments);
      const presentation = buildSeatPresentation(assignments);
      setSeatPresentation(presentation);
      liveSessionSnapshotRef.current = {
        gameId: null,
        assignments,
        seatPresentation: presentation,
        launchState: 'creating',
        streamCursor: 0,
        effectSeq: 0,
        recentEffects: [],
      };
      const created = await createGame({
        agents,
        pacing: 'live',
        startPaused: true,
        seatPresentation: presentation,
      });
      streamCursorRef.current = 0;
      effectSeqRef.current = 0;
      pendingRunGameIdRef.current = created.game_id;
      const createdSnapshot = {
        gameId: created.game_id,
        assignments,
        seatPresentation: presentation,
        launchState: 'connecting_stream' as const,
        streamCursor: 0,
        effectSeq: 0,
        recentEffects: [],
      };
      liveSessionSnapshotRef.current = createdSnapshot;
      writeLiveGameSession(createdSnapshot);
      setLaunchState('connecting_stream');
      setGameId(created.game_id);
      transitionToStage({ dayNumber: stage.dayNumber, phase: 'night' });
    } catch (caught) {
      updateLaunchState('failed');
      setTestMessage(caught instanceof Error ? caught.message : '创建游戏失败');
    }
  }, [
    assignments,
    effectSeqRef,
    gameStarted,
    isStartingGame,
    liveSessionSnapshotRef,
    pendingRunGameIdRef,
    setGameId,
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
      if (pendingRunGameIdRef.current !== id || runStartedGameIdsRef.current.has(id)) {
        return;
      }
      const seatsMounted = document.querySelector('.game-seats') !== null;
      const effectsLayerMounted = document.querySelector('.game-effects-layer') !== null;
      if (!seatsMounted || !effectsLayerMounted) {
        window.setTimeout(() => {
          void startPausedGameWhenReady(id);
        }, 50);
        return;
      }
      runStartedGameIdsRef.current.add(id);
      try {
        const summary = await runGame(id);
        pendingRunGameIdRef.current = null;
        setTimings(summary.timings);
        setCurrentPhase(summary.phase);
        if (summary.status === 'failed') {
          updateLaunchState('failed');
          setStreamStatus('failed');
        } else {
          updateLaunchState((current) => launchStateAfterPhase(current, summary.phase));
        }
      } catch (error) {
        runStartedGameIdsRef.current.delete(id);
        updateLaunchState('failed');
        setStreamStatus('error');
        setTestMessage(error instanceof Error ? error.message : '启动游戏失败');
      }
    },
    [
      pendingRunGameIdRef,
      runStartedGameIdsRef,
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
