import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { GameEffectsLayer } from '../../src/components/Game/GameEffectsLayer';
import {
  appendRecentSpectatorEffects,
  effectIdentity,
  type EffectSeenAtMap,
} from '../../src/lib/gameEffects';
import { spectatorEffectAckEvent, type SpectatorEffect } from '../../src/lib/gameApi';

describe('GameEffectsLayer', () => {
  it('uses stable spectator effect ack event names', () => {
    expect(spectatorEffectAckEvent(27)).toBe('spectator_effect_rendered:27');
  });

  it('renders live spectator effect announcements with matching assets', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const guard = effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD');
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 9);
    const effects = [guard, wolf, seer, potion];
    const seenAtByKey: EffectSeenAtMap = {
      [effectIdentity(wolf)]: 1000,
    };
    const recentEffects = appendRecentSpectatorEffects([], effects, 1000);

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={effects}
        currentDay={2}
        currentPhase="DAY_SPEECH"
        nowMs={1800}
        seenAtByKey={seenAtByKey}
        recentEffects={recentEffects}
      />,
    );

    expect(html).toContain('守卫护盾：8号');
    expect(html).toContain('狼人袭击：4号');
    expect(html).toContain('预言查验：7号');
    expect(html).toContain('女巫解药：5号');
    expect(html).toContain('/assets/game/effects/wolf_attack.png');
    expect(html).toContain('data-layout="side-stack"');
    expect(html).toContain('game-effect-announcement--wolf_attack');
    expect(html).toContain('game-effect-seat-overlay--guard_shield');
    expect(html).toContain('game-effect-seat-overlay--wolf_attack');
    expect(html).toContain('game-effect-seat-overlay--seer_vision');
    expect(html).toContain('game-effect-seat-overlay--witch_potion');
    expect(html).toContain('data-target-seat="8"');
    expect(html).toContain('data-target-seat="5"');
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
        recentEffects={appendRecentSpectatorEffects([], [seer], 1000)}
      />,
    );

    expect(html).toContain('预言查验：7号');
    expect(html).toContain('game-effect-announcement--seer_vision');
  });

  it('renders announcement text even when the asset key is unknown', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'missing_asset', {}, 0, 'NIGHT_WOLF_VOTE');
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
        recentEffects={appendRecentSpectatorEffects([], [wolf], 1000)}
      />,
    );

    expect(html).toContain('狼人袭击：4号');
    expect(html).not.toContain('missing_asset');
  });

  it('suppresses transient announcements in terminal mode', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const guard = effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD');
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 9);
    const effects = [guard, wolf, seer, potion];
    const seenAtByKey: EffectSeenAtMap = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={effects}
        currentDay={1}
        currentPhase="GAME_END"
        nowMs={1800}
        seenAtByKey={seenAtByKey}
        recentEffects={appendRecentSpectatorEffects([], effects, 1000)}
        terminal
      />,
    );

    expect(html).not.toContain('守卫护盾');
    expect(html).not.toContain('狼人袭击');
    expect(html).not.toContain('预言查验');
    expect(html).not.toContain('女巫解药');
    expect(html).not.toContain('game-effect-announcement');
    expect(html).not.toContain('game-effect-seat-overlay');
  });

  it('does not render expired transient or death reveal announcements', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const death = effect(3, 'death_reveal', 4, 'out_badge', {}, 0, 'DAY_ANNOUNCE');
    const seenAtByKey: EffectSeenAtMap = {
      [effectIdentity(wolf)]: 1000,
      [effectIdentity(death)]: 1000,
    };
    const recentEffects = appendRecentSpectatorEffects([], [wolf, death], 1000);

    const html = renderToStaticMarkup(
      <GameEffectsLayer
        effects={[wolf, death]}
        currentDay={2}
        currentPhase="DAY_SPEECH"
        nowMs={9100}
        seenAtByKey={seenAtByKey}
        recentEffects={recentEffects}
      />,
    );

    expect(html).not.toContain('狼人袭击');
    expect(html).not.toContain('死亡');
    expect(html).not.toContain('game-effect-announcement');
  });

  it('keeps live announcement layout away from the phase countdown area', () => {
    const css = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
    const announcementsRules = [
      ...css.matchAll(/\.game-effect-announcements\s*\{(?<body>[^}]+)\}/g),
    ].map((match) => match.groups?.body ?? '');
    const baseAnnouncementsRule = announcementsRules.find((body) =>
      body.includes('right: max(20px'),
    );
    const mobileAnnouncementsRule = announcementsRules.find((body) =>
      body.includes('top: clamp(182px'),
    );
    const phaseHeaderRule = css.match(/\.game-phase-header\s*\{(?<body>[^}]+)\}/)
      ?.groups?.body;

    expect(baseAnnouncementsRule).toBeDefined();
    expect(mobileAnnouncementsRule).toBeDefined();
    expect(phaseHeaderRule).toBeDefined();
    expect(baseAnnouncementsRule).toContain('right:');
    expect(baseAnnouncementsRule).not.toContain('left: 50%');
    expect(baseAnnouncementsRule).not.toContain('transform: translateX(-50%)');
    expect(mobileAnnouncementsRule).toContain('top: clamp(182px, 24vh, 228px)');
    expect(phaseHeaderRule).toContain('z-index: 7');
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
