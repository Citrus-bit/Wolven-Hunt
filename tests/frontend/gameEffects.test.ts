import { describe, expect, it } from 'vitest';
import {
  buildSeatEffectMap,
  deathRevealSeats,
  effectIdentity,
} from '../../src/lib/gameEffects';
import type { SpectatorEffect } from '../../src/lib/gameApi';

describe('gameEffects', () => {
  it('builds active seat effect state for night effects', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield'),
      effect(2, 'wolf_attack', 4, 'wolf_attack', { blocked_by_guard: true }),
      effect(3, 'seer_vision', 7, 'seer_vision'),
      effect(4, 'death_reveal', 8, 'out_badge'),
    ];

    const map = buildSeatEffectMap(effects, 'NIGHT_WOLF_VOTE');

    expect(map[4]).toMatchObject({
      guardShield: true,
      wolfAttack: true,
      wolfAttackBlocked: true,
    });
    expect(map[7].seerVisionSeq).toBe(3);
    expect(map[8].outBadge).toBe(true);
    expect([...deathRevealSeats(effects)]).toEqual([8]);
  });

  it('keeps recent night effects visible across fast phase changes', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield'),
      effect(2, 'wolf_attack', 4, 'wolf_attack'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      nowMs: 3000,
      seenAtByKey,
    });

    expect(map[4].guardShield).toBe(true);
    expect(map[4].wolfAttack).toBe(true);
  });

  it('expires transient effects after their display window', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield'),
      effect(2, 'wolf_attack', 4, 'wolf_attack', { blocked_by_guard: true }, 3000),
      effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      nowMs: 7000,
      seenAtByKey,
    });

    expect(map[4].guardShield).toBe(false);
    expect(map[4].wolfAttack).toBe(false);
    expect(map[7].seerVisionSeq).toBeUndefined();
  });
});

function effect(
  seq: number,
  kind: SpectatorEffect['kind'],
  target: number,
  assetKey: string,
  meta: Record<string, unknown> = {},
  durationMs = 0,
): SpectatorEffect {
  return {
    seq,
    day: 1,
    phase: 'NIGHT_WITCH',
    kind,
    actor: null,
    source_seat: null,
    target_seat: target,
    asset_key: assetKey,
    duration_ms: durationMs,
    meta,
  };
}
