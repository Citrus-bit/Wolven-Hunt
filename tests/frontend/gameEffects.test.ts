import { describe, expect, it } from 'vitest';
import {
  activeEffectAnnouncements,
  activePotionEffects,
  activeRecentEffectAnnouncements,
  activeRecentTransientEffects,
  appendRecentSpectatorEffects,
  appendUniqueSpectatorEffects,
  buildSeatEffectMap,
  deathRevealSeats,
  effectAnnouncementDurationMs,
  effectDisplayDurationMs,
  effectIdentity,
  publicEliminatedSeats,
  seedExpiredEffectSeenAt,
  seedEffectSeenAt,
  seedLiveEffectSeenAt,
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

  it('keeps just-seen guard shields visible after phase advances', () => {
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

    expect(dayMap[4].guardShield).toBe(true);
  });

  it('keeps live guard shields visible through the same night resolve phase', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const seerMap = buildSeatEffectMap(effects, 'NIGHT_SEER', {
      currentDay: 1,
      nowMs: 9000,
      seenAtByKey,
    });
    const resolveMap = buildSeatEffectMap(effects, 'NIGHT_RESOLVE', {
      currentDay: 1,
      nowMs: 12000,
      seenAtByKey,
    });
    const afterNightMap = buildSeatEffectMap(effects, 'CHECK_WIN_NIGHT', {
      currentDay: 1,
      nowMs: 5600,
      seenAtByKey,
    });

    expect(seerMap[4].guardShield).toBe(true);
    expect(resolveMap[4].guardShield).toBe(true);
    expect(afterNightMap[4].guardShield).toBeUndefined();
  });

  it('expires guard shields after their arrival grace window and later nights', () => {
    const effects: SpectatorEffect[] = [
      effect(1, 'guard_shield', 4, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const dayMap = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      currentDay: 1,
      nowMs: 5600,
      seenAtByKey,
    });
    const laterNightMap = buildSeatEffectMap(effects, 'NIGHT_GUARD', {
      currentDay: 2,
      nowMs: 5600,
      seenAtByKey,
    });

    expect(dayMap[4].guardShield).toBeUndefined();
    expect(laterNightMap[4].guardShield).toBeUndefined();
  });

  it('keeps late-arriving wolf attacks visible across fast non-terminal phase and day changes', () => {
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
    const gameEndMap = buildSeatEffectMap(effects, 'GAME_END', {
      currentDay: 1,
      nowMs: 3000,
      seenAtByKey,
    });
    const laterDayMap = buildSeatEffectMap(effects, 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 3000,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBe(true);
    expect(gameEndMap[4].wolfAttack).toBeUndefined();
    expect(laterDayMap[4].wolfAttack).toBe(true);
  });

  it('keeps late-arriving seer and potion effects visible by arrival duration', () => {
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_poison', { action: 'poison' }, 1200, 'NIGHT_WITCH', 9);
    const seenAtByKey = {
      [effectIdentity(seer)]: 1000,
      [effectIdentity(potion)]: 1000,
    };

    const map = buildSeatEffectMap([seer], 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 1800,
      seenAtByKey,
    });
    const activePotions = activePotionEffects([potion], 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 1800,
      seenAtByKey,
    });
    const terminalMap = buildSeatEffectMap([seer], 'GAME_END', {
      currentDay: 2,
      nowMs: 1800,
      seenAtByKey,
    });
    const terminalPotions = activePotionEffects([potion], 'GAME_END', {
      currentDay: 2,
      nowMs: 1800,
      seenAtByKey,
    });

    expect(map[7].seerVisionSeq).toBe(3);
    expect(activePotions).toEqual([potion]);
    expect(terminalMap[7].seerVisionSeq).toBeUndefined();
    expect(terminalPotions).toEqual([]);
  });

  it('keeps live short effects visible after fast phase changes by arrival time', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 9);
    const effects = [wolf, seer, potion];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap([wolf, seer], 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 3200,
      seenAtByKey,
    });
    const activePotions = activePotionEffects([potion], 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 3200,
      seenAtByKey,
    });
    const announcements = activeEffectAnnouncements(effects, 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 5500,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBe(true);
    expect(map[7].seerVisionSeq).toBe(3);
    expect(activePotions).toEqual([potion]);
    expect(announcements.map((item) => item.kind)).toEqual([
      'wolf_attack',
      'seer_vision',
      'witch_potion',
    ]);
  });

  it('expires transient effects after their display window', () => {
    const effects: SpectatorEffect[] = [
      effect(2, 'wolf_attack', 4, 'wolf_attack', { blocked_by_guard: true }, 3000, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'witch_potion', 5, 'potion_poison', { action: 'poison' }, 1200, 'NIGHT_WITCH', 9),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const map = buildSeatEffectMap(effects, 'DAY_ANNOUNCE', {
      currentDay: 2,
      nowMs: 7000,
      seenAtByKey,
    });
    const activePotions = activePotionEffects(effects, 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 7000,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBeUndefined();
    expect(map[7].seerVisionSeq).toBeUndefined();
    expect(activePotions).toEqual([]);
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
      nowMs: 5000,
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

  it('seeds replay history transient effects as expired while keeping death reveals', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 9);
    const death = effect(5, 'death_reveal', 8, 'out_badge', {}, 0, 'DAY_ANNOUNCE');
    const effects = [wolf, seer, potion, death];
    const seenAtByKey = {};

    seedExpiredEffectSeenAt(effects, seenAtByKey, 5000);

    const map = buildSeatEffectMap(effects, 'GAME_END', {
      currentDay: 1,
      nowMs: 5000,
      seenAtByKey,
    });
    const activePotions = activePotionEffects(effects, 'GAME_END', {
      currentDay: 1,
      nowMs: 5000,
      seenAtByKey,
    });

    expect(map[4].wolfAttack).toBeUndefined();
    expect(map[7].seerVisionSeq).toBeUndefined();
    expect(map[8].outBadge).toBe(true);
    expect(activePotions).toEqual([]);
  });

  it('does not replay expired history announcements', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const seer = effect(3, 'seer_vision', 7, 'seer_vision', {}, 1800, 'NIGHT_SEER');
    const potion = effect(4, 'witch_potion', 5, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 9);
    const seenAtByKey = {};

    seedExpiredEffectSeenAt([wolf, seer, potion], seenAtByKey, 5000);

    expect(
      activeEffectAnnouncements([wolf, seer, potion], 'GAME_END', {
        currentDay: 1,
        nowMs: 5000,
        seenAtByKey,
      }),
    ).toEqual([]);
  });

  it('keeps live recent announcements visible independent of current day and phase', () => {
    const effects = [
      effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
      effect(2, 'wolf_attack', 9, 'wolf_attack', { blocked_by_guard: true }, 3000, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 5, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'witch_potion', 6, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 3),
      effect(5, 'death_reveal', 6, 'out_badge', {}, 0, 'DAY_ANNOUNCE'),
    ];

    const recent = appendRecentSpectatorEffects([], effects, 1000);
    const active = activeRecentEffectAnnouncements(recent, 8999);
    const terminal = activeRecentEffectAnnouncements(recent, 1800, { terminal: true });
    const expired = activeRecentEffectAnnouncements(recent, 9001);

    expect(recent.map((item) => item.effect.kind)).toEqual([
      'guard_shield',
      'wolf_attack',
      'seer_vision',
      'witch_potion',
    ]);
    expect(active.map((item) => item.text)).toEqual([
      '守卫护盾：8号',
      '狼人袭击：9号',
      '预言查验：5号',
      '女巫解药：6号',
    ]);
    expect(terminal).toEqual([]);
    expect(expired).toEqual([]);
  });

  it('builds live recent transient overlays for the seat layer only during display windows', () => {
    const effects = [
      effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
      effect(2, 'wolf_attack', 9, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 5, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'witch_potion', 6, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 3),
    ];
    const recent = appendRecentSpectatorEffects([], effects, 1000);

    expect(activeRecentTransientEffects(recent, 2500).map((item) => item.effect.kind)).toEqual([
      'guard_shield',
      'wolf_attack',
      'seer_vision',
      'witch_potion',
    ]);
    expect(activeRecentTransientEffects(recent, 5600).map((item) => item.effect.kind)).toEqual([]);
    expect(activeRecentTransientEffects(recent, 4600, { terminal: true })).toEqual([]);
  });

  it('queues live transient overlays by effect kind and valid witch action', () => {
    const skip = effect(
      5,
      'witch_potion',
      6,
      'potion_antidote',
      { action: 'skip' },
      1200,
      'NIGHT_WITCH',
      3,
    );
    const death = effect(6, 'death_reveal', 6, 'out_badge', {}, 0, 'DAY_ANNOUNCE');
    const effects = [
      effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
      effect(2, 'wolf_attack', 9, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 5, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'witch_potion', 6, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 3),
      skip,
      death,
    ];
    const recent = appendRecentSpectatorEffects([], effects, 1000);

    expect(recent.map((item) => item.effect.kind)).toEqual([
      'guard_shield',
      'wolf_attack',
      'seer_vision',
      'witch_potion',
    ]);
    expect(activeRecentTransientEffects(recent, 1200)).toHaveLength(4);
  });

  it('does not create a recent announcement for witch skip payloads', () => {
    const skip = effect(
      4,
      'witch_potion',
      6,
      'potion_antidote',
      { action: 'skip' },
      1200,
      'NIGHT_WITCH',
      3,
    );

    const recent = appendRecentSpectatorEffects([], [skip], 1000);
    const seenAtByKey = { [effectIdentity(skip)]: 1000 };

    expect(recent).toEqual([]);
    expect(activeRecentEffectAnnouncements(recent, 1200)).toEqual([]);
    expect(
      activePotionEffects([skip], 'NIGHT_WITCH', {
        currentDay: 1,
        nowMs: 1200,
        seenAtByKey,
      }),
    ).toEqual([]);
  });

  it('deduplicates spectator effects without resetting first-seen timestamps', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const duplicate = { ...wolf };
    const seenAtByKey = {};

    seedEffectSeenAt([wolf], seenAtByKey, 1000);
    seedEffectSeenAt([duplicate], seenAtByKey, 5000);

    expect(appendUniqueSpectatorEffects([wolf], [duplicate])).toEqual([wolf]);
    expect(seenAtByKey).toEqual({ [effectIdentity(wolf)]: 1000 });
  });

  it('refreshes expired REST history when the same effect arrives live by SSE', () => {
    const wolf = effect(2, 'wolf_attack', 4, 'wolf_attack', {}, 0, 'NIGHT_WOLF_VOTE');
    const seenAtByKey = {};

    seedExpiredEffectSeenAt([wolf], seenAtByKey, 10000);
    expect(buildSeatEffectMap([wolf], 'DAY_SPEECH', {
      currentDay: 1,
      nowMs: 10000,
      seenAtByKey,
    })[4].wolfAttack).toBeUndefined();

    seedLiveEffectSeenAt([wolf], seenAtByKey, 11000);

    expect(buildSeatEffectMap([wolf], 'DAY_SPEECH', {
      currentDay: 1,
      nowMs: 11000,
      seenAtByKey,
    })[4].wolfAttack).toBe(true);

    const recent = appendRecentSpectatorEffects([], [wolf], 11000);
    expect(activeRecentTransientEffects(recent, 11100).map((item) => item.id)).toEqual([
      effectIdentity(wolf),
    ]);
  });

  it('builds recent effect announcements without private result details', () => {
    const effects = [
      effect(1, 'guard_shield', 8, 'guard_shield', {}, 0, 'NIGHT_GUARD'),
      effect(2, 'wolf_attack', 9, 'wolf_attack', { blocked_by_guard: true }, 3000, 'NIGHT_WOLF_VOTE'),
      effect(3, 'seer_vision', 5, 'seer_vision', {}, 1800, 'NIGHT_SEER'),
      effect(4, 'witch_potion', 6, 'potion_antidote', { action: 'save' }, 1200, 'NIGHT_WITCH', 3),
      effect(5, 'death_reveal', 6, 'out_badge', {}, 0, 'DAY_ANNOUNCE'),
    ];
    const seenAtByKey = Object.fromEntries(
      effects.map((item) => [effectIdentity(item), 1000]),
    );

    const announcements = activeEffectAnnouncements(effects, 'DAY_SPEECH', {
      currentDay: 2,
      nowMs: 1800,
      seenAtByKey,
    });

    expect(announcements.map((item) => item.text)).toEqual([
      '守卫护盾：8号',
      '狼人袭击：9号',
      '预言查验：5号',
      '女巫解药：6号',
    ]);
    expect(announcements.map((item) => item.text).join(' ')).not.toContain('blocked');
    expect(announcements.map((item) => item.text).join(' ')).not.toContain('结果');
  });

  it('uses readable minimum display durations for transient effects', () => {
    expect(effectDisplayDurationMs(effect(1, 'guard_shield', 4, 'guard_shield'))).toBe(4500);
    expect(effectDisplayDurationMs(effect(2, 'wolf_attack', 4, 'wolf_attack'))).toBe(4500);
    expect(effectDisplayDurationMs(effect(3, 'seer_vision', 4, 'seer_vision'))).toBe(4200);
    expect(
      effectDisplayDurationMs(
        effect(4, 'witch_potion', 4, 'potion_antidote', { action: 'save' }, 1200),
      ),
    ).toBe(3800);
    expect(effectDisplayDurationMs(effect(5, 'wolf_attack', 4, 'wolf_attack', {}, 5000))).toBe(5000);
    expect(effectAnnouncementDurationMs(effect(6, 'seer_vision', 4, 'seer_vision'))).toBe(8000);
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
