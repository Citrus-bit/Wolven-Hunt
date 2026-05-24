import { describe, expect, it } from 'vitest';
import {
  activePotionEffects,
  buildSeatEffectMap,
  deathRevealSeats,
  effectIdentity,
  publicEliminatedSeats,
} from '../../src/lib/gameEffects';
import type { GameEvent, SpectatorEffect } from '../../src/lib/gameApi';

describe('gameEffects', () => {
  it('builds active seat effect state for the current night', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
      effect(2, 'wolf_attack', 4, 'wolf_attack', { blocked_by_guard: true }, 3000, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'death_reveal', 8, 'out_badge', {}, 0, 'DAY_ANNOUNCE'),
    ];

    const map = buildSeatEffectMap(effects, 'NIGHT_SEER', { currentDay: 1 });

    expect(map[4]).toMatchObject({
      guardShield: true,
      guardShieldSeq: 1,
      wolfAttack: true,
      wolfAttackSeq: 2,
      wolfAttackBlocked: true,
    });
    expect(map[7].seerVisionSeq).toBe(3);
    expect(map[8].outBadge).toBe(true);
    expect([...deathRevealSeats(effects)]).toEqual([8]);
  });

  it('expires guard shields at day announce and later nights', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const dayMap = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      currentDay: 1,
      nowMs: 1500,
      seenAtByKey,
    });
    const laterNightMap = buildSeatEffectMap(effects, 'NIGHT_GUARD', {
      currentDay: 2,
      nowMs: 1500,
      seenAtByKey,
    });

    expect(dayMap[4].guardShield).toBeUndefined();
    expect(laterNightMap[4].guardShield).toBeUndefined();
  });

  it('keeps recent wolf attacks visible across fast phase changes', () => {
    const effects: SpectatorEffect[] = [
      effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      currentDay: 1,
      nowMs: 3000,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBe(true);
  });

  it('expires transient effects after their display window', () => {
    const effects: SpectatorEffect[] = [
      effect(2, 'wolf_attack', 4, 'wolf_attack', { blocked_by_guard: true }, 3000, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      currentDay: 1,
      nowMs: 7000,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBeUndefined();
    expect(map[7].seerVisionSeq).toBeUndefined();
  });

  it('collects public eliminations from night deaths, death reveal, exile, and final reveal', () => {
    const effects = [
      effect(4, 'death_reveal', 8, 'out_badge', {}, 0, 'DAY_ANNOUNCE'),
    ];
    const events: GameEvent[] = [
      gameEvent(4, 'death_at_night', { seat: 9 }),
      gameEvent(5, 'exile', { seat: 3 }),
      gameEvent(6, 'role_reveal', {
        seats: [
          { seat: 1, role: 'villager', alive: false },
          { seat: 2, role: 'wolf', alive: true },
        ],
      }),
    ];

    expect([...publicEliminatedSeats(events, effects)].sort((a, b) => a - b)).toEqual([
      1,
      3,
      8,
      9,
    ]);
  });

  it('keeps active save and poison potion effects distinct for overlay playback', () => {
    const save = effect(10, 'witch_potion', 4, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 7);
    const poison = effect(10, 'witch_potion', 4, 'potion_poison', { action: 'poison' }, 1200, 'NIGHT_WITCH', null);
    const oldPoison = effect(11, 'witch_potion', 5, 'potion_poison', { action: 'poison' }, 1200, 'NIGHT_WITCH', 7);
    const seenAtByKey = {
      [effectIdentity(save)]: 1000,
      [effectIdentity(poison)]: 1000,
      [effectIdentity(oldPoison)]: 1000,
    };

    const active = activePotionEffects(
      [save, poison, oldPoison],
      'NIGHT_SEER',
      {
        currentDay: 1,
        nowMs: 1800,
        seenAtByKey,
      },
    );
    const expired = activePotionEffects([save], 'NIGHT_SEER', {
      currentDay: 1,
      nowMs: 4000,
      seenAtByKey,
    });

    expect(active.map((item) => item.asset_key)).toEqual([
      'potion_antidote',
      'potion_poison',
      'potion_poison',
    ]);
    expect(effectIdentity(save)).not.toBe(effectIdentity(poison));
    expect(poison.source_seat).toBeNull();
    expect(expired).toEqual([]);
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

function gameEvent(
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): GameEvent {
  return {
    seq,
    day: 1,
    phase: 'DAY_ANNOUNCE',
    type,
    actor: null,
    payload,
  };
}
