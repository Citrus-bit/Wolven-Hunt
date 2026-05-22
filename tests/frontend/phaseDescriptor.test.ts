import { describe, expect, it } from 'vitest';
import { phaseDurationMs, phaseStatusText } from '../../src/lib/phaseDescriptor';

const phases = [
  'GAME_START',
  'NIGHT_START',
  'NIGHT_GUARD',
  'NIGHT_WOLF_CHAT',
  'NIGHT_WOLF_VOTE',
  'NIGHT_SEER',
  'NIGHT_RESOLVE',
  'CHECK_WIN_NIGHT',
  'DAY_ANNOUNCE',
  'DAY_LAST_WORDS',
  'DAY_SPEECH',
  'DAY_KNIGHT_INTERRUPT',
  'DAY_VOTE',
  'DAY_VOTE_PK',
  'DAY_EXILE',
  'CHECK_WIN_DAY',
  'GAME_END',
];

describe('phaseDescriptor', () => {
  it('has display text for every engine phase', () => {
    for (const phase of phases) {
      expect(phaseStatusText(phase)).not.toBe(phase);
    }
    expect(phaseStatusText('DAY_SPEECH', 4)).toBe('4号玩家正在发言');
  });

  it('maps configured phase durations', () => {
    const timings = {
      night_start_ms: 1000,
      night_guard_ms: 60000,
      night_wolf_chat_ms: 120000,
      night_wolf_vote_ms: 30000,
      night_seer_ms: 60000,
      day_announce_ms: 1000,
      day_last_words_ms: 60000,
      day_speech_ms: 60000,
      day_vote_ms: 30000,
      day_vote_pk_ms: 30000,
      knight_duel_ms: 800,
    };

    expect(phaseDurationMs('NIGHT_GUARD', timings)).toBe(60000);
    expect(phaseDurationMs('DAY_KNIGHT_INTERRUPT', timings)).toBe(800);
    expect(phaseDurationMs('GAME_END', timings)).toBe(0);
  });
});
