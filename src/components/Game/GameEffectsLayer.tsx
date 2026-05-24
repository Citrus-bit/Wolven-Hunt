import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { gameEffectAssetPath, type GameEffectAssetKey } from '../../lib/effectAssets';
import {
  activeRecentEffectAnnouncements,
  activePotionEffects,
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

export function GameEffectsLayer({
  effects,
  currentDay,
  currentPhase,
  nowMs,
  seenAtByKey,
  recentEffects,
  terminal = false,
}: GameEffectsLayerProps) {
  const layerRef = useRef<HTMLDivElement | null>(null);
  const seenFlightIdsRef = useRef(new Set<string>());
  const renderedAnnouncementIdsRef = useRef(new Set<string>());
  const [flights, setFlights] = useState<PotionFlight[]>([]);
  const [bursts, setBursts] = useState<PotionBurst[]>([]);
  const announcements = activeRecentEffectAnnouncements(recentEffects, nowMs, {
    terminal,
  }).slice(-4);

  useEffect(() => {
    if (!import.meta.env.DEV || import.meta.env.MODE === 'test') {
      return;
    }
    for (const announcement of announcements) {
      if (renderedAnnouncementIdsRef.current.has(announcement.id)) {
        continue;
      }
      renderedAnnouncementIdsRef.current.add(announcement.id);
      console.info('[spectator_effect rendered]', {
        kind: announcement.kind,
        seq: announcement.seq,
        target: announcement.targetSeat,
      });
    }
  }, [announcements]);

  useEffect(() => {
    if (terminal) {
      setFlights([]);
      setBursts([]);
      return;
    }
    const activeEffects = activePotionEffects(effects, currentPhase, {
      currentDay,
      nowMs,
      seenAtByKey,
    });
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
        window.setTimeout(() => {
          setBursts((current) => current.filter((item) => item.id !== id));
        }, burst.durationMs + 220);
        continue;
      }
      seenFlightIdsRef.current.add(id);
      setFlights((current) => [...current, flight]);
      window.setTimeout(() => {
        setFlights((current) => current.filter((item) => item.id !== id));
      }, flight.durationMs + 220);
    }
  }, [currentDay, currentPhase, effects, nowMs, seenAtByKey, terminal]);

  return (
    <div ref={layerRef} className="game-effects-layer" aria-hidden="true">
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
        <div className="game-effect-announcements">
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
  const target = seatCenter(effect.target_seat, layer);
  if (!target) {
    return null;
  }
  return {
    id,
    assetKey: effect.asset_key,
    x: target.x,
    y: target.y,
    durationMs: effectDisplayDurationMs(effect),
  };
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
