import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GameEffectsLayer } from '../../src/components/Game/GameEffectsLayer';
import { effectIdentity, type EffectSeenAtMap } from '../../src/lib/gameEffects';
import type { SpectatorEffect } from '../../src/lib/gameApi';

describe('GameEffectsLayer', () => {
  it('renders recent spectator effect announcements with the matching asset', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const seenAtByKey: EffectSeenAtMap = {
      [effectIdentity(wolf)]: 1000,
    };

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={[wolf]}
        currentDay={2}
        currentPhase="DAY_SPEECH"
        nowMs={1800}
        seenAtByKey={seenAtByKey}
      />,
    );

    expect(html).toContain('狼人袭击：4号');
    expect(html).toContain('/assets/game/effects/wolf_attack.png');
    expect(html).toContain('game-effect-announcement--wolf_attack');
  });

  it('keeps live announcements visible after the seat animation window', () => {
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const seenAtByKey: EffectSeenAtMap = {
      [effectIdentity(seer)]: 1000,
    };

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={[seer]}
        currentDay={2}
        currentPhase="DAY_SPEECH"
        nowMs={5200}
        seenAtByKey={seenAtByKey}
      />,
    );

    expect(html).toContain('预言查验：7号');
    expect(html).toContain('game-effect-announcement--seer_vision');
  });

  it('does not render expired transient or death reveal announcements', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const death = effect(3, 'death_reveal', 4, 'out_badge', {}, 0, 'DAY_ANNOUNCE');
    const seenAtByKey: EffectSeenAtMap = {
      [effectIdentity(wolf)]: 1000,
      [effectIdentity(death)]: 1000,
    };

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={[wolf, death]}
        currentDay={2}
        currentPhase="DAY_SPEECH"
        nowMs={7000}
        seenAtByKey={seenAtByKey}
      />,
    );

    expect(html).not.toContain('狼人袭击');
    expect(html).not.toContain('死亡');
    expect(html).not.toContain('game-effect-announcement');
  });
});

function effect(
  seq: number,
  kind: SpectatorEffect['kind'],
  target: number,
  assetKey: string,
  meta: Record<string, unknown> = {},
  durationMs = 0,
  phase = 'NIGHT_WITCH',
  sourceSeat: number | null = null,
): SpectatorEffect {
  return {
    seq,
    day: 1,
    phase,
    kind,
    actor: null,
    source_seat: sourceSeat,
    target_seat: target,
    asset_key: assetKey,
    duration_ms: durationMs,
    meta,
  };
}
