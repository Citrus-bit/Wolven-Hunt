import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { gameEffectAssetPath, type GameEffectAssetKey } from '../../lib/effectAssets';
import {
  activeRecentEffectAnnouncements,
  activeRecentTransientEffects,
  effectDisplayDurationMs,
  effectIdentity,
  type EffectSeenAtMap,
  type RecentSpectatorEffect,
} from '../../lib/gameEffects';
import type { SpectatorEffect } from '../../lib/gameApi';

type GameEffectsLayerProps = {
  effects: SpectatorEffect[];
  currentDay: number | null;
  currentPhase: string | null;
  nowMs: number;
  seenAtByKey: EffectSeenAtMap;
  recentEffects: RecentSpectatorEffect[];
  terminal?: boolean;
  onEffectRendered?: (effect: SpectatorEffect) => void;
};

type PotionFlight = {
  id: string;
  assetKey: GameEffectAssetKey;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  durationMs: number;
};

type PotionBurst = {
  id: string;
  assetKey: GameEffectAssetKey;
  x: number;
  y: number;
  durationMs: number;
};

type SeatOverlayPosition = {
  x: string;
  y: string;
};

type SeatOverlay = {
  id: string;
  effect: SpectatorEffect;
  kind: SpectatorEffect['kind'];
  assetKey: GameEffectAssetKey;
  blocked: boolean;
  durationMs: number;
};

const MIN_VISIBLE_EFFECT_ACK_MS = 700;
const MAX_VISIBLE_EFFECT_ACK_MS = 1200;

export function GameEffectsLayer({
  nowMs,
  recentEffects,
  terminal = false,
  onEffectRendered,
}: GameEffectsLayerProps) {
  const layerRef = useRef<HTMLDivElement | null>(null);
  const seenFlightIdsRef = useRef(new Set<string>());
  const renderedLiveEffectIdsRef = useRef(new Set<string>());
  const renderedAnnouncementIdsRef = useRef(new Set<string>());
  const renderAckTimersRef = useRef(new Map<string, number>());
  const [seatOverlayPositions, setSeatOverlayPositions] = useState<
    Record<string, SeatOverlayPosition>
  >({});
  const [flights, setFlights] = useState<PotionFlight[]>([]);
  const [bursts, setBursts] = useState<PotionBurst[]>([]);
  const activeRecentEffects = useMemo(
    () => activeRecentTransientEffects(recentEffects, nowMs, { terminal }),
    [nowMs, recentEffects, terminal],
  );
  const seatOverlays = useMemo(
    () => buildSeatOverlays(activeRecentEffects),
    [activeRecentEffects],
  );
  const announcements = activeRecentEffectAnnouncements(recentEffects, nowMs, {
    terminal,
  }).slice(-4);

  useEffect(() => {
    for (const announcement of announcements) {
      if (renderedAnnouncementIdsRef.current.has(announcement.id)) {
        continue;
      }
      renderedAnnouncementIdsRef.current.add(announcement.id);
      if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
        console.info('[spectator_effect rendered]', {
          kind: announcement.kind,
          seq: announcement.seq,
          target: announcement.targetSeat,
        });
      }
    }
  }, [announcements]);

  useEffect(() => () => clearRenderAckTimers(renderAckTimersRef.current), []);

  useEffect(() => {
    if (terminal) {
      renderedLiveEffectIdsRef.current.clear();
      clearRenderAckTimers(renderAckTimersRef.current);
      setSeatOverlayPositions((current) =>
        Object.keys(current).length === 0 ? current : {},
      );
      return;
    }
    if (seatOverlays.length === 0) {
      setSeatOverlayPositions((current) =>
        Object.keys(current).length === 0 ? current : {},
      );
      return;
    }
    const nextPositions: Record<string, SeatOverlayPosition> = {};
    for (const overlay of seatOverlays) {
      nextPositions[overlay.id] = seatOverlayPosition(
        overlay.effect.target_seat,
        layerRef.current,
      );
      markLiveEffectRendered(
        renderedLiveEffectIdsRef.current,
        renderAckTimersRef.current,
        overlay.id,
        overlay.effect,
        onEffectRendered,
      );
    }
    setSeatOverlayPositions((current) =>
      samePositionMap(current, nextPositions) ? current : nextPositions,
    );
  }, [onEffectRendered, seatOverlays, terminal]);

  useEffect(() => {
    if (terminal) {
      return;
    }
    for (const item of activeRecentEffects) {
      const effect = item.effect;
      if (effect.kind === 'death_reveal' || isEffectAssetKey(effect.asset_key)) {
        continue;
      }
      markLiveEffectRendered(
        renderedLiveEffectIdsRef.current,
        renderAckTimersRef.current,
        item.id,
        effect,
        onEffectRendered,
      );
    }
  }, [activeRecentEffects, onEffectRendered, terminal]);

  useEffect(() => {
    if (terminal) {
      setFlights([]);
      setBursts([]);
      return;
    }
    const activeEffects = activeRecentEffects.map((item) => item.effect);
    for (const effect of activeEffects) {
      if (effect.kind !== 'witch_potion') {
        continue;
      }
      const id = effectIdentity(effect);
      if (seenFlightIdsRef.current.has(id)) {
        continue;
      }
      const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      const flight = reduceMotion ? null : buildPotionFlight(id, effect, layerRef.current);
      if (!flight) {
        const burst = buildPotionBurst(id, effect, layerRef.current);
        if (!burst) {
          continue;
        }
        seenFlightIdsRef.current.add(id);
        setBursts((current) => [...current, burst]);
        markLiveEffectRendered(
          renderedLiveEffectIdsRef.current,
          renderAckTimersRef.current,
          id,
          effect,
          onEffectRendered,
        );
        window.setTimeout(() => {
          setBursts((current) => current.filter((item) => item.id !== id));
        }, burst.durationMs + 220);
        continue;
      }
      seenFlightIdsRef.current.add(id);
      setFlights((current) => [...current, flight]);
      markLiveEffectRendered(
        renderedLiveEffectIdsRef.current,
        renderAckTimersRef.current,
        id,
        effect,
        onEffectRendered,
      );
      window.setTimeout(() => {
        setFlights((current) => current.filter((item) => item.id !== id));
      }, flight.durationMs + 220);
    }
  }, [activeRecentEffects, onEffectRendered, terminal]);

  return (
    <div ref={layerRef} className="game-effects-layer" aria-hidden="true">
      {seatOverlays.map((overlay) => (
        <img
          key={overlay.id}
          src={gameEffectAssetPath(overlay.assetKey)}
          alt=""
          className={[
            'game-effect-seat-overlay',
            `game-effect-seat-overlay--${overlay.kind}`,
            `game-effect-seat-overlay--${overlay.assetKey}`,
            overlay.blocked ? 'game-effect-seat-overlay--blocked' : '',
          ].join(' ')}
          data-target-seat={overlay.effect.target_seat}
          style={{
            '--effect-seat-x':
              seatOverlayPositions[overlay.id]?.x ??
              fallbackSeatPosition(overlay.effect.target_seat).x,
            '--effect-seat-y':
              seatOverlayPositions[overlay.id]?.y ??
              fallbackSeatPosition(overlay.effect.target_seat).y,
            '--effect-duration': `${overlay.durationMs}ms`,
          } as CSSProperties}
        />
      ))}
      {flights.map((flight) => (
        <img
          key={flight.id}
          src={gameEffectAssetPath(flight.assetKey)}
          alt=""
          className={`game-effect-flight game-effect-flight--${flight.assetKey}`}
          style={{
            '--effect-from-x': `${flight.fromX}px`,
            '--effect-from-y': `${flight.fromY}px`,
            '--effect-to-x': `${flight.toX}px`,
            '--effect-to-y': `${flight.toY}px`,
            '--effect-duration': `${flight.durationMs}ms`,
          } as CSSProperties}
        />
      ))}
      {bursts.map((burst) => (
        <img
          key={burst.id}
          src={gameEffectAssetPath(burst.assetKey)}
          alt=""
          className={`game-effect-burst game-effect-burst--${burst.assetKey}`}
          style={{
            '--effect-burst-x': `${burst.x}px`,
            '--effect-burst-y': `${burst.y}px`,
            '--effect-duration': `${burst.durationMs}ms`,
          } as CSSProperties}
        />
      ))}
      {announcements.length > 0 && (
        <div className="game-effect-announcements" data-layout="side-stack">
          {announcements.map((announcement) => (
            <span
              key={announcement.id}
              className={`game-effect-announcement game-effect-announcement--${announcement.kind}`}
            >
              {isEffectAssetKey(announcement.assetKey) && (
                <img
                  src={gameEffectAssetPath(announcement.assetKey)}
                  alt=""
                  className="game-effect-announcement-icon"
                />
              )}
              <span>{announcement.text}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function buildPotionFlight(
  id: string,
  effect: SpectatorEffect,
  layer: HTMLDivElement | null,
): PotionFlight | null {
  if (!layer || effect.source_seat === null || !isEffectAssetKey(effect.asset_key)) {
    return null;
  }
  const from = seatCenter(effect.source_seat, layer);
  const to = seatCenter(effect.target_seat, layer);
  if (!from || !to) {
    return null;
  }
  return {
    id,
    assetKey: effect.asset_key,
    fromX: from.x,
    fromY: from.y,
    toX: to.x,
    toY: to.y,
    durationMs: effectDisplayDurationMs(effect),
  };
}

function buildPotionBurst(
  id: string,
  effect: SpectatorEffect,
  layer: HTMLDivElement | null,
): PotionBurst | null {
  if (!layer || !isEffectAssetKey(effect.asset_key)) {
    return null;
  }
  const target = seatCenter(effect.target_seat, layer) ?? layerCenter(layer);
  return {
    id,
    assetKey: effect.asset_key,
    x: target.x,
    y: target.y,
    durationMs: effectDisplayDurationMs(effect),
  };
}

function buildSeatOverlays(recentEffects: RecentSpectatorEffect[]): SeatOverlay[] {
  return recentEffects.flatMap((item) => {
    const effect = item.effect;
    if (!isEffectAssetKey(effect.asset_key) || effect.kind === 'death_reveal') {
      return [];
    }
    if (
      effect.kind !== 'guard_shield' &&
      effect.kind !== 'wolf_attack' &&
      effect.kind !== 'seer_vision' &&
      effect.kind !== 'witch_potion'
    ) {
      return [];
    }
    return [
      {
        id: item.id,
        effect,
        kind: effect.kind,
        assetKey: effect.asset_key,
        blocked: effect.kind === 'wolf_attack' && effect.meta.blocked_by_guard === true,
        durationMs: effectDisplayDurationMs(effect),
      },
    ];
  });
}

function seatCenter(seat: number, layer: HTMLDivElement) {
  const scope: ParentNode = layer.parentElement ?? document;
  const circle = scope.querySelector(
    `[data-seat-index="${seat - 1}"] .game-seat-circle`,
  );
  if (!(circle instanceof HTMLElement)) {
    return null;
  }
  const layerRect = layer.getBoundingClientRect();
  const rect = circle.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2 - layerRect.left,
    y: rect.top + rect.height / 2 - layerRect.top,
  };
}

function layerCenter(layer: HTMLDivElement) {
  return {
    x: layer.clientWidth / 2,
    y: layer.clientHeight / 2,
  };
}

function seatOverlayPosition(
  seat: number,
  layer: HTMLDivElement | null,
): SeatOverlayPosition {
  if (layer) {
    const center = seatCenter(seat, layer);
    if (center) {
      return { x: `${center.x}px`, y: `${center.y}px` };
    }
  }
  return fallbackSeatPosition(seat);
}

function fallbackSeatPosition(seat: number): SeatOverlayPosition {
  const clampedSeat = Number.isFinite(seat)
    ? Math.max(1, Math.min(10, Math.floor(seat)))
    : 1;
  const index = clampedSeat <= 5 ? clampedSeat - 1 : clampedSeat - 6;
  return {
    x: clampedSeat <= 5 ? '8vw' : '92vw',
    y: `${20 + index * 15}vh`,
  };
}

function samePositionMap(
  left: Record<string, SeatOverlayPosition>,
  right: Record<string, SeatOverlayPosition>,
) {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return rightKeys.every((key) => left[key]?.x === right[key].x && left[key]?.y === right[key].y);
}

function markLiveEffectRendered(
  renderedIds: Set<string>,
  renderAckTimers: Map<string, number>,
  id: string,
  effect: SpectatorEffect,
  onEffectRendered: ((effect: SpectatorEffect) => void) | undefined,
) {
  if (renderedIds.has(id)) {
    return;
  }
  renderedIds.add(id);
  if (!onEffectRendered) {
    return;
  }
  const timer = window.setTimeout(() => {
    renderAckTimers.delete(id);
    onEffectRendered(effect);
  }, effectRenderAckDelayMs(effect));
  renderAckTimers.set(id, timer);
}

function clearRenderAckTimers(renderAckTimers: Map<string, number>) {
  for (const timer of renderAckTimers.values()) {
    window.clearTimeout(timer);
  }
  renderAckTimers.clear();
}

function effectRenderAckDelayMs(effect: SpectatorEffect) {
  return Math.min(
    MAX_VISIBLE_EFFECT_ACK_MS,
    Math.max(
      MIN_VISIBLE_EFFECT_ACK_MS,
      Math.floor(effectDisplayDurationMs(effect) * 0.32),
    ),
  );
}

function isEffectAssetKey(value: string): value is GameEffectAssetKey {
  return (
    value === 'potion_antidote' ||
    value === 'potion_poison' ||
    value === 'guard_shield' ||
    value === 'wolf_attack' ||
    value === 'seer_vision' ||
    value === 'out_badge'
  );
}
