import type { GameEvent, NarrativeRow } from './gameApi';

export function toNarrative(event: GameEvent): NarrativeRow | null {
  const payload = event.payload;
  if (event.type === 'role_reveal') {
    return null;
  }
  if (event.type === 'phase_enter') {
    const text = phaseText(String(payload.phase ?? event.phase));
    return text ? row(event, 'system', text) : null;
  }
  if (event.type === 'speech') {
    return row(event, 'speech', `${event.actor}号：${String(payload.text ?? '')}`);
  }
  if (event.type === 'last_words') {
    return row(event, 'speech', `${event.actor}号遗言：${String(payload.text ?? '')}`);
  }
  if (event.type === 'day_announce') {
    return row(event, 'announce', String(payload.message ?? '白天公示'));
  }
  if (event.type === 'death_at_night') {
    return row(event, 'announce', `${String(payload.seat ?? '')}号倒在了夜里`);
  }
  if (event.type === 'no_death_tonight') {
    return row(event, 'announce', '昨晚是平安夜');
  }
  if (event.type === 'vote_cast') {
    return row(event, 'action', `${event.actor}号投票给${String(payload.target ?? '')}号`);
  }
  if (event.type === 'vote_result') {
    return row(event, 'verdict', `投票结果：${formatCounts(payload.counts)}`);
  }
  if (event.type === 'vote_pk_enter') {
    return row(event, 'verdict', `平票，${formatSeats(payload.pk_seats)}进入 PK`);
  }
  if (event.type === 'peaceful_day') {
    return row(event, 'verdict', '本轮无人被放逐，直接进入夜晚');
  }
  if (event.type === 'exile') {
    return row(event, 'verdict', `${String(payload.seat ?? '')}号被放逐`);
  }
  if (event.type === 'knight_challenge') {
    return row(event, 'action', `骑士向${String(payload.target ?? '')}号发起决斗`);
  }
  if (event.type === 'knight_result') {
    const result = payload.result === 'hit_wolf' ? '命中狼人' : '挑战失败';
    return row(event, 'verdict', `骑士决斗${result}，${String(payload.killed ?? '')}号死亡`);
  }
  if (event.type === 'game_end') {
    return row(event, 'verdict', `游戏结束，${winnerLabel(payload.winner)}胜利`);
  }
  return null;
}

function row(
  event: GameEvent,
  kind: NarrativeRow['kind'],
  text: string,
): NarrativeRow {
  return {
    seq: event.seq,
    day: event.day,
    phase: event.phase,
    kind,
    text,
    actor: event.actor,
    icon: null,
  };
}

function phaseText(phase: string) {
  return (
    {
      NIGHT_START: '夜幕降临',
      NIGHT_GUARD: '夜幕降临，守卫开始行动',
      NIGHT_WOLF_CHAT: '狼人正在讨论',
      NIGHT_WOLF_VOTE: '狼人正在行动',
      NIGHT_SEER: '预言家正在行动',
      NIGHT_RESOLVE: '夜晚行动结算中',
      DAY_ANNOUNCE: '天亮了，开始公布昨夜情况',
      DAY_LAST_WORDS: '死亡玩家正在发表遗言',
      DAY_SPEECH: '白天发言开始',
      DAY_VOTE: '正在举行公民投票',
      DAY_VOTE_PK: '正在进行 PK 重投',
      GAME_END: '游戏进入终局',
    } as Record<string, string>
  )[phase];
}

function formatCounts(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return '暂无票型';
  }
  return Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => Number(left) - Number(right))
    .map(([seat, count]) => `${seat}号 ${String(count)}票`)
    .join(' / ');
}

function formatSeats(value: unknown) {
  if (!Array.isArray(value)) {
    return '';
  }
  return value.map((seat) => `${String(seat)}号`).join('、');
}

function winnerLabel(value: unknown) {
  return value === 'wolf' ? '狼人' : '好人';
}
