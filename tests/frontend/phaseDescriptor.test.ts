import { describe, expect, it } from 'vitest';
import {
  phaseCountdownText,
  phaseDurationMs,
  phaseShowsWaitingFeedback,
  phaseStatusText,
  phaseWaitingText,
} from '../../src/lib/phaseDescriptor';

const phases = [
  'GAME_START',
  'NIGHT_START',
  'NIGHT_GUARD',
  'NIGHT_WOLF_CHAT',
  'NIGHT_WOLF_VOTE',
  'NIGHT_WITCH',
  'NIGHT_SEER',
  'NIGHT_RESOLVE',
  'CHECK_WIN_NIGHT',
  'DAY_ANNOUNCE',
  'DAY_LAST_WORDS',
  'DAY_SPEECH',
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
    expect(phaseStatusText('DAY_SPEECH', null, true)).toBe('发言结束，准备投票');
  });

  it('maps configured phase durations', () => {
    const timings = {
      night_start_ms: 1000,
      night_guard_ms: 60000,
      night_wolf_chat_ms: 15000,
      night_wolf_vote_ms: 8000,
      night_witch_ms: 60000,
      night_seer_ms: 60000,
      day_announce_ms: 1000,
      day_last_words_ms: 60000,
      day_speech_ms: 25000,
      day_vote_ms: 8000,
      day_vote_pk_ms: 8000,
    };

    expect(phaseDurationMs('NIGHT_GUARD', timings)).toBe(60000);
    expect(phaseDurationMs('NIGHT_WOLF_CHAT', timings)).toBe(15000);
    expect(phaseDurationMs('NIGHT_WOLF_VOTE', timings)).toBe(8000);
    expect(phaseDurationMs('NIGHT_WITCH', timings)).toBe(60000);
    expect(phaseDurationMs('DAY_SPEECH', timings)).toBe(25000);
    expect(phaseDurationMs('DAY_VOTE', timings)).toBe(8000);
    expect(phaseDurationMs('DAY_VOTE_PK', timings)).toBe(8000);
    expect(phaseDurationMs('GAME_END', timings)).toBe(0);
  });

  it('uses explicit waiting labels for speech countdown states', () => {
    expect(phaseCountdownText('DAY_SPEECH', 60000, 1250, { speakerSeat: 4 })).toBe('2s');
    expect(phaseCountdownText('DAY_SPEECH', 60000, 0, { speakerSeat: 4 })).toBe(
      '等待响应',
    );
    expect(phaseCountdownText('DAY_SPEECH', 60000, 0, { speechComplete: true })).toBe(
      '等待推进',
    );
    expect(phaseCountdownText('DAY_VOTE', 30000, 0)).toBe('等待中...');
  });

  it('shows only public-safe aggregate waiting feedback', () => {
    expect(phaseWaitingText('DAY_SPEECH', 3200)).toBe('模型响应中 · 已等待 3s');
    expect(phaseWaitingText('NIGHT_WOLF_CHAT', 12000)).toBe(
      '模型响应中 · 已等待 12s',
    );
    expect(phaseWaitingText('DAY_VOTE', 8300)).toBe('收集投票中 · 已等待 8s');
    expect(phaseWaitingText('DAY_VOTE_PK', 8300)).toBe('收集投票中 · 已等待 8s');
    expect(phaseWaitingText('NIGHT_WOLF_VOTE', 8300)).toBe(
      '收集投票中 · 已等待 8s',
    );
    expect(phaseWaitingText('NIGHT_WITCH', 8300)).toBeNull();
    expect(phaseWaitingText('DAY_SPEECH', 8300, { speechComplete: true })).toBeNull();
    expect(phaseShowsWaitingFeedback('DAY_VOTE')).toBe(true);
    expect(phaseShowsWaitingFeedback('NIGHT_WITCH')).toBe(false);
  });
});
