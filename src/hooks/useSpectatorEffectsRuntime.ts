import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from 'react';
import {
  appendRecentSpectatorEffects,
  appendUniqueSpectatorEffects,
  expireTransientEffectSeenAt,
  pruneRecentSpectatorEffects,
  seedExpiredEffectSeenAt,
  seedLiveEffectSeenAt,
  type EffectSeenAtMap,
  type RecentSpectatorEffect,
} from '../lib/gameEffects';
import {
  sendAck,
  spectatorEffectAckEvent,
  type SpectatorEffect,
} from '../lib/gameApi';

type UseSpectatorEffectsRuntimeParams = {
  gameId: string | null;
  isReplay: boolean;
  terminalRef: MutableRefObject<boolean>;
  restored?: {
    gameId: string;
    effectSeq: number;
    recentEffects: RecentSpectatorEffect[];
  } | null;
  persistRecentEffects?: (effects: RecentSpectatorEffect[]) => void;
  onEffectSeq?: (seq: number) => void;
};

export function useSpectatorEffectsRuntime({
  gameId,
  isReplay,
  terminalRef,
  restored = null,
  persistRecentEffects,
  onEffectSeq,
}: UseSpectatorEffectsRuntimeParams) {
  const [spectatorEffects, setSpectatorEffects] = useState<SpectatorEffect[]>([]);
  const [recentEffects, setRecentEffects] = useState<RecentSpectatorEffect[]>(() =>
    restored?.recentEffects ?? [],
  );
  const [effectClockMs, setEffectClockMs] = useState(() => Date.now());
  const effectSeenAtRef = useRef<EffectSeenAtMap>({});
  const effectSeqRef = useRef(restored?.effectSeq ?? 0);
  const effectAckSeqRef = useRef(new Set<number>());
  const persistRecentEffectsRef = useRef(persistRecentEffects);
  const onEffectSeqRef = useRef(onEffectSeq);

  persistRecentEffectsRef.current = persistRecentEffects;
  onEffectSeqRef.current = onEffectSeq;

  const resetForGame = useCallback(
    (nextGameId: string | null) => {
      setSpectatorEffects([]);
      const restoredRecentEffects = restored?.gameId === nextGameId
        ? restored.recentEffects
        : [];
      setRecentEffects(restoredRecentEffects);
      effectSeenAtRef.current = {};
      if (restored?.gameId === nextGameId) {
        seedLiveEffectSeenAt(
          restored.recentEffects.map((item) => item.effect),
          effectSeenAtRef.current,
          Date.now(),
        );
      }
      setEffectClockMs(Date.now());
      effectSeqRef.current = restored?.gameId === nextGameId ? restored.effectSeq : 0;
      effectAckSeqRef.current = new Set();
      persistRecentEffectsRef.current?.(restoredRecentEffects);
    },
    [restored],
  );

  const loadReplayEffects = useCallback((effects: SpectatorEffect[]) => {
    effectSeenAtRef.current = {};
    const nowMs = Date.now();
    seedExpiredEffectSeenAt(effects, effectSeenAtRef.current, nowMs);
    setEffectClockMs(nowMs);
    setSpectatorEffects(effects);
    setRecentEffects((current) => (current.length === 0 ? current : []));
    effectSeqRef.current = effects.reduce(
      (max, effect) => Math.max(max, effect.seq),
      0,
    );
  }, []);

  const ingestLiveEffects = useCallback(
    (effects: SpectatorEffect[]) => {
      if (effects.length === 0) {
        return;
      }
      logSpectatorEffectsReceived(effects);
      const nowMs = Date.now();
      if (terminalRef.current) {
        expireTransientEffectSeenAt(effects, effectSeenAtRef.current, nowMs);
        setSpectatorEffects((prev) => appendUniqueSpectatorEffects(prev, effects));
        setRecentEffects((prev) => {
          const next = prev.length === 0 ? prev : [];
          persistRecentEffectsRef.current?.(next);
          return next;
        });
      } else {
        seedLiveEffectSeenAt(effects, effectSeenAtRef.current, nowMs);
        setSpectatorEffects((prev) => appendUniqueSpectatorEffects(prev, effects));
        setRecentEffects((prev) => {
          const next = appendRecentSpectatorEffects(prev, effects, nowMs);
          persistRecentEffectsRef.current?.(next);
          return next;
        });
      }
      setEffectClockMs(nowMs);
      for (const effect of effects) {
        effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
        onEffectSeqRef.current?.(effect.seq);
      }
    },
    [terminalRef],
  );

  const ingestHistoricalEffects = useCallback(
    (effects: SpectatorEffect[], terminal: boolean) => {
      if (effects.length === 0) {
        return;
      }
      const nowMs = Date.now();
      if (terminal) {
        expireTransientEffectSeenAt(effects, effectSeenAtRef.current, nowMs);
      } else {
        seedExpiredEffectSeenAt(effects, effectSeenAtRef.current, nowMs);
      }
      setSpectatorEffects((prev) => appendUniqueSpectatorEffects(prev, effects));
      for (const effect of effects) {
        effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
        onEffectSeqRef.current?.(effect.seq);
      }
      setEffectClockMs(nowMs);
    },
    [],
  );

  const markFinished = useCallback(() => {
    const nowMs = Date.now();
    expireTransientEffectSeenAt(spectatorEffects, effectSeenAtRef.current, nowMs);
    setEffectClockMs(nowMs);
    setRecentEffects((current) => {
      const next = current.length === 0 ? current : [];
      persistRecentEffectsRef.current?.(next);
      return next;
    });
  }, [spectatorEffects]);

  const handleRenderedSpectatorEffect = useCallback(
    (effect: SpectatorEffect) => {
      if (!gameId || isReplay || terminalRef.current || effect.kind === 'death_reveal') {
        return;
      }
      if (effectAckSeqRef.current.has(effect.seq)) {
        return;
      }
      effectAckSeqRef.current.add(effect.seq);
      effectSeqRef.current = Math.max(effectSeqRef.current, effect.seq);
      onEffectSeqRef.current?.(effect.seq);
      void sendAck(gameId, effect.phase, spectatorEffectAckEvent(effect.seq)).catch(
        () => undefined,
      );
    },
    [gameId, isReplay, terminalRef],
  );

  useEffect(() => {
    if (spectatorEffects.length === 0 && recentEffects.length === 0) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      const nowMs = Date.now();
      setEffectClockMs(nowMs);
      setRecentEffects((current) => {
        const next = pruneRecentSpectatorEffects(current, nowMs);
        persistRecentEffectsRef.current?.(next);
        return next;
      });
    }, 250);
    return () => window.clearInterval(timer);
  }, [recentEffects.length, spectatorEffects.length]);

  return {
    spectatorEffects,
    recentEffects,
    effectClockMs,
    effectSeenAtRef,
    effectSeqRef,
    resetForGame,
    loadReplayEffects,
    ingestLiveEffects,
    ingestHistoricalEffects,
    markFinished,
    handleRenderedSpectatorEffect,
  };
}

function logSpectatorEffectsReceived(effects: SpectatorEffect[]) {
  if (!import.meta.env.DEV || import.meta.env.MODE === 'test') {
    return;
  }
  for (const effect of effects) {
    if (effect.kind === 'death_reveal') {
      continue;
    }
    console.info('[spectator_effect received]', {
      kind: effect.kind,
      seq: effect.seq,
      target: effect.target_seat,
    });
  }
}
