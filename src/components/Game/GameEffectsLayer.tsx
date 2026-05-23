import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { gameEffectAssetPath, type GameEffectAssetKey } from '../../lib/effectAssets';
import type { SpectatorEffect } from '../../lib/gameApi';

type GameEffectsLayerProps = {
  effects: SpectatorEffect[];
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

export function GameEffectsLayer({ effects }: GameEffectsLayerProps) {
  const layerRef = useRef<HTMLDivElement | null>(null);
  const seenFlightIdsRef = useRef(new Set<string>());
  const [flights, setFlights] = useState<PotionFlight[]>([]);
  const [bursts, setBursts] = useState<PotionBurst[]>([]);

  useEffect(() => {
    for (const effect of effects) {
      if (effect.kind !== 'witch_potion' || effect.source_seat === null) {
        continue;
      }
      const id = `${effect.seq}:${effect.source_seat}:${effect.target_seat}:${effect.asset_key}`;
      if (seenFlightIdsRef.current.has(id)) {
        continue;
      }
      seenFlightIdsRef.current.add(id);
      const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      const flight = reduceMotion ? null : buildPotionFlight(id, effect, layerRef.current);
      if (!flight) {
        const burst = buildPotionBurst(id, effect, layerRef.current);
        if (!burst) {
          continue;
        }
        setBursts((current) => [...current, burst]);
        window.setTimeout(() => {
          setBursts((current) => current.filter((item) => item.id !== id));
        }, burst.durationMs + 220);
        continue;
      }
      setFlights((current) => [...current, flight]);
      window.setTimeout(() => {
        setFlights((current) => current.filter((item) => item.id !== id));
      }, flight.durationMs + 220);
    }
  }, [effects]);

  return (
    <div ref={layerRef} className="game-effects-layer" aria-hidden="true">
      {flights.map((flight) => (
        <img
          key={flight.id}
          src={gameEffectAssetPath(flight.assetKey)}
          alt=""
          className="game-effect-flight"
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
          className="game-effect-burst"
          style={{
            '--effect-burst-x': `${burst.x}px`,
            '--effect-burst-y': `${burst.y}px`,
            '--effect-duration': `${burst.durationMs}ms`,
          } as CSSProperties}
        />
      ))}
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
    durationMs: Math.max(300, effect.duration_ms || 1200),
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
    durationMs: Math.max(300, Math.min(1600, effect.duration_ms || 900)),
  };
}

function seatCenter(seat: number, layer: HTMLDivElement) {
  const circle = document.querySelector(
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
