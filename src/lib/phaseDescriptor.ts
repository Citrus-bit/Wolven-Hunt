import type { GameTimings } from './gameApi';

const MODEL_WAITING_PHASES = new Set(['DAY_SPEECH', 'NIGHT_WOLF_CHAT']);
const VOTE_WAITING_PHASES = new Set([
  'DAY_VOTE',
  'DAY_VOTE_PK',
  'NIGHT_WOLF_VOTE',
]);

export function phaseStatusText(
  phase: string | null,
  speakerSeat?: number | null,
  speechComplete = false,
) {
  if (!phase) {
    return '等待游戏开始';
  }
  if (phase === 'DAY_SPEECH' && speechComplete) {
    return '发言结束，准备投票';
  }
  if (phase === 'DAY_SPEECH' && speakerSeat) {
    return `${speakerSeat}号玩家正在发言`;
  }
  return (
    {
      GAME_START: '游戏正在开始',
      NIGHT_START: '夜幕降临',
      NIGHT_GUARD: '守卫正在行动',
      NIGHT_WOLF_CHAT: '狼人正在讨论',
      NIGHT_WOLF_VOTE: '狼人正在行动',
      NIGHT_WITCH: '女巫正在行动',
      NIGHT_SEER: '预言家正在行动',
      NIGHT_RESOLVE: '夜晚行动结算中',
      CHECK_WIN_NIGHT: '正在判定胜负',
      DAY_ANNOUNCE: '正在公布昨夜情况',
      DAY_LAST_WORDS: '死亡玩家正在发表遗言',
      DAY_SPEECH: '玩家正在发言',
      DAY_VOTE: '正在举行公民投票',
      DAY_VOTE_PK: '正在 PK 重投',
      DAY_EXILE: '正在执行放逐',
      CHECK_WIN_DAY: '正在判定胜负',
      GAME_END: '游戏结束',
    } as Record<string, string>
  )[phase] ?? phase;
}

export function phaseDurationMs(phase: string | null, timings: GameTimings | null) {
  if (!phase || !timings) {
    return 0;
  }
  const keyByPhase: Record<string, string> = {
    NIGHT_START: 'night_start_ms',
    NIGHT_GUARD: 'night_guard_ms',
    NIGHT_WOLF_CHAT: 'night_wolf_chat_ms',
    NIGHT_WOLF_VOTE: 'night_wolf_vote_ms',
    NIGHT_WITCH: 'night_witch_ms',
    NIGHT_SEER: 'night_seer_ms',
    DAY_ANNOUNCE: 'day_announce_ms',
    DAY_LAST_WORDS: 'day_last_words_ms',
    DAY_SPEECH: 'day_speech_ms',
    DAY_VOTE: 'day_vote_ms',
    DAY_VOTE_PK: 'day_vote_pk_ms',
  };
  return timings[keyByPhase[phase]] ?? 0;
}

export function phaseCountdownText(
  phase: string | null,
  durationMs: number,
  remainingMs: number,
  opts: { speakerSeat?: number | null; speechComplete?: boolean } = {},
) {
  if (opts.speechComplete) {
    return '等待推进';
  }
  if (durationMs <= 0) {
    return '--';
  }
  if (remainingMs <= 0) {
    return phase === 'DAY_SPEECH' && opts.speakerSeat ? '等待响应' : '等待中...';
  }
  return `${Math.ceil(remainingMs / 1000)}s`;
}

export function phaseWaitingText(
  phase: string | null,
  elapsedMs: number,
  opts: { speechComplete?: boolean } = {},
) {
  if (!phase || opts.speechComplete) {
    return null;
  }
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  if (MODEL_WAITING_PHASES.has(phase)) {
    return `模型响应中 · 已等待 ${elapsedSeconds}s`;
  }
  if (VOTE_WAITING_PHASES.has(phase)) {
    return `收集投票中 · 已等待 ${elapsedSeconds}s`;
  }
  return null;
}

export function phaseShowsWaitingFeedback(phase: string | null) {
  return (
    phase !== null &&
    (MODEL_WAITING_PHASES.has(phase) || VOTE_WAITING_PHASES.has(phase))
  );
}
