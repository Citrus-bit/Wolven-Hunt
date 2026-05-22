import { useMemo } from 'react';
import type { GameEvent, NarrativeRow } from '../../lib/gameApi';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import { VoteHistogram } from './VoteHistogram';

type GameChatProps = {
  events: GameEvent[];
  narrativeRows: NarrativeRow[];
  assignments: (number | null)[];
  streamStatus: 'idle' | 'connecting' | 'open' | 'error';
};

export function GameChat({
  events,
  narrativeRows,
  assignments,
  streamStatus,
}: GameChatProps) {
  const rows = useMemo(() => narrativeRows.slice(-80), [narrativeRows]);
  const voteCounts = useMemo(() => latestVoteCounts(events), [events]);

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
                : streamStatus === 'idle'
                  ? '待开始'
                  : '未连接'}
          </span>
        </header>
        <div className="game-chat-body" role="log" aria-live="polite">
          {rows.length === 0 ? (
            <p className="game-event-line game-event-line--system">
              完成席位分配并通过测试后，点击夜深了开始观赛。
            </p>
          ) : (
            rows.map((row) => (
              <NarrativeLine
                key={`${row.seq}-${row.kind}`}
                row={row}
                assignments={assignments}
              />
            ))
          )}
        </div>
        {voteCounts && <VoteHistogram counts={voteCounts} />}
      </section>
      <section
        className="game-chat-panel game-chat-panel--wolf"
        aria-label="狼人聊天框"
      >
        <header className="game-chat-header">狼人聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite">
          <p className="game-event-line game-event-line--system">
            观众视角无法查看狼人夜聊，终局后统一揭晓身份。
          </p>
        </div>
      </section>
    </div>
  );
}

function NarrativeLine({
  row,
  assignments,
}: {
  row: NarrativeRow;
  assignments: (number | null)[];
}) {
  const slotIndex = row.actor === null ? null : assignments[row.actor - 1];
  const slot = slotIndex === null ? null : MODEL_SLOTS[slotIndex];

  if (row.kind === 'speech' && slot) {
    return (
      <article className="game-narrative-line game-narrative-line--speech">
        <img src={slot.iconPath} alt="" className="game-narrative-avatar" />
        <div>
          <strong>{slot.nickname}</strong>
          <p>{row.text}</p>
        </div>
      </article>
    );
  }

  return (
    <p className={`game-event-line game-event-line--${row.kind}`}>
      <span className="game-event-seq">#{row.seq}</span>
      <span>{row.text}</span>
    </p>
  );
}

function latestVoteCounts(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === 'vote_pk_enter') {
      return null;
    }
    if (
      event.type === 'vote_result' &&
      event.payload.counts &&
      typeof event.payload.counts === 'object' &&
      !Array.isArray(event.payload.counts)
    ) {
      return event.payload.counts as Record<string, unknown>;
    }
  }
  return null;
}
