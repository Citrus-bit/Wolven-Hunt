import { FormEvent, useMemo, useState } from 'react';
import {
  submitSpeech,
  submitWolfChat,
  type GameEvent,
} from '../../lib/gameApi';

type GameChatProps = {
  gameId: string | null;
  events: GameEvent[];
  phase: string | null;
  streamStatus: 'connecting' | 'open' | 'error';
};

export function GameChat({ gameId, events, phase, streamStatus }: GameChatProps) {
  const [seat, setSeat] = useState(1);
  const [speechText, setSpeechText] = useState('');
  const [wolfText, setWolfText] = useState('');
  const [speechStatus, setSpeechStatus] = useState<string | null>(null);
  const [wolfStatus, setWolfStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<'speech' | 'wolf' | null>(null);
  const visibleEvents = useMemo(() => events.slice(-80), [events]);
  const disabled = !gameId || submitting !== null;
  const wolfDisabled = disabled || phase !== 'NIGHT_WOLF_CHAT';

  const handleSpeech = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!gameId || !speechText.trim()) {
      return;
    }
    setSubmitting('speech');
    setSpeechStatus(null);
    try {
      await submitSpeech(gameId, seat, speechText.trim());
      setSpeechText('');
      setSpeechStatus('已提交');
    } catch (caught) {
      setSpeechStatus(caught instanceof Error ? caught.message : '提交失败');
    } finally {
      setSubmitting(null);
    }
  };

  const handleWolfChat = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!gameId || wolfDisabled || !wolfText.trim()) {
      return;
    }
    setSubmitting('wolf');
    setWolfStatus(null);
    try {
      await submitWolfChat(gameId, seat, wolfText.trim());
      setWolfText('');
      setWolfStatus('已提交');
    } catch (caught) {
      setWolfStatus(caught instanceof Error ? caught.message : '提交失败');
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="game-chat" aria-label="游戏聊天区">
      <section
        className="game-chat-panel game-chat-panel--general"
        aria-label="通用聊天框"
      >
        <header className="game-chat-header">
          <span>通用聊天框</span>
          <span className={`game-stream-status game-stream-status--${streamStatus}`}>
            {streamStatus === 'open'
              ? '已连接'
              : streamStatus === 'connecting'
                ? '连接中'
                : '未连接'}
          </span>
        </header>
        <div className="game-chat-body" role="log" aria-live="polite">
          {visibleEvents.map((event) => (
            <p className="game-event-line" key={event.seq}>
              <span className="game-event-seq">#{event.seq}</span>
              <span>{formatEvent(event)}</span>
            </p>
          ))}
        </div>
        <form className="game-chat-footer" onSubmit={handleSpeech}>
          <SeatSelect value={seat} onChange={setSeat} disabled={disabled} />
          <input
            type="text"
            className="game-chat-input"
            placeholder="发言"
            value={speechText}
            onChange={(event) => setSpeechText(event.target.value)}
            disabled={disabled}
          />
          <button
            type="submit"
            className="game-chat-submit"
            disabled={disabled || !speechText.trim()}
          >
            发送
          </button>
          {speechStatus && <span className="game-chat-status">{speechStatus}</span>}
        </form>
      </section>
      <section
        className="game-chat-panel game-chat-panel--wolf"
        aria-label="狼人聊天框"
      >
        <header className="game-chat-header">狼人聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite">
          <p className="game-event-line">暂无可见消息</p>
        </div>
        <form className="game-chat-footer" onSubmit={handleWolfChat}>
          <SeatSelect value={seat} onChange={setSeat} disabled={wolfDisabled} />
          <input
            type="text"
            className="game-chat-input"
            placeholder={
              phase === 'NIGHT_WOLF_CHAT' ? '狼人夜聊' : '仅狼人夜聊阶段可用'
            }
            value={wolfText}
            onChange={(event) => setWolfText(event.target.value)}
            disabled={wolfDisabled}
          />
          <button
            type="submit"
            className="game-chat-submit"
            disabled={wolfDisabled || !wolfText.trim()}
          >
            发送
          </button>
          {wolfStatus && <span className="game-chat-status">{wolfStatus}</span>}
        </form>
      </section>
    </div>
  );
}

function SeatSelect({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (value: number) => void;
  disabled: boolean;
}) {
  return (
    <label className="game-chat-seat">
      <span>座位</span>
      <select
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        disabled={disabled}
      >
        {Array.from({ length: 8 }, (_, index) => index + 1).map((seat) => (
          <option key={seat} value={seat}>
            {seat}
          </option>
        ))}
      </select>
    </label>
  );
}

function formatEvent(event: GameEvent) {
  const actor = event.actor === null ? '系统' : `${event.actor}号`;
  const payload = event.payload;
  if (event.type === 'speech' || event.type === 'last_words') {
    return `${actor}: ${String(payload.text ?? '')}`;
  }
  if (event.type === 'day_announce') {
    return String(payload.message ?? '白天公示');
  }
  if (event.type === 'death_at_night') {
    return `夜晚死亡玩家：${String(payload.seat ?? '')}`;
  }
  if (event.type === 'no_death_tonight') {
    return '昨晚是平安夜';
  }
  if (event.type === 'vote_result') {
    return `投票结果：${JSON.stringify(payload.counts ?? {})}`;
  }
  if (event.type === 'exile') {
    return `放逐玩家：${String(payload.seat ?? '')}`;
  }
  if (event.type === 'game_end') {
    return `游戏结束：${String(payload.winner ?? '')}`;
  }
  return `${event.phase} / ${event.type}`;
}
