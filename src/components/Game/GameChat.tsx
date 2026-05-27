import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { GameEvent, NarrativeRow } from '../../lib/gameApi';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import {
  TYPEWRITER_DURATION_MS,
  typewriterVisibleText,
} from '../../lib/typewriter';
import { VoteHistogram } from './VoteHistogram';

type GameChatProps = {
  events: GameEvent[];
  narrativeRows: NarrativeRow[];
  assignments: (number | null)[];
  streamStatus: 'idle' | 'connecting' | 'open' | 'error' | 'failed';
  autoScrollEnabled: boolean;
  liveTypingEnabled: boolean;
};

export function GameChat({
  events,
  narrativeRows,
  assignments,
  streamStatus,
  autoScrollEnabled,
  liveTypingEnabled,
}: GameChatProps) {
  const generalBodyRef = useRef<HTMLDivElement | null>(null);
  const wolfBodyRef = useRef<HTMLDivElement | null>(null);
  const rows = useMemo(() => narrativeRows.slice(-80), [narrativeRows]);
  const wolfRows = useMemo(
    () => events.filter((event) => event.type === 'wolf_chat_message').slice(-80),
    [events],
  );
  const voteCounts = useMemo(() => latestVoteCounts(events), [events]);
  const scrollGeneralToBottom = useCallback(() => {
    scrollChatBodyToBottom(generalBodyRef.current, autoScrollEnabled);
  }, [autoScrollEnabled]);
  const scrollWolfToBottom = useCallback(() => {
    scrollChatBodyToBottom(wolfBodyRef.current, autoScrollEnabled);
  }, [autoScrollEnabled]);

  useEffect(() => {
    scrollGeneralToBottom();
  }, [rows.length, rows[rows.length - 1]?.seq, scrollGeneralToBottom]);

  useEffect(() => {
    scrollWolfToBottom();
  }, [wolfRows.length, wolfRows[wolfRows.length - 1]?.seq, scrollWolfToBottom]);

  return (
    <div className="game-chat" aria-label="游戏聊天区">
      <section
        className="game-chat-panel game-chat-panel--general"
        aria-label="好人聊天框"
      >
        <header className="game-chat-header">
          <span>好人聊天框</span>
          <span className={`game-stream-status game-stream-status--${streamStatus}`}>
            {streamStatus === 'open'
              ? '已连接'
              : streamStatus === 'connecting'
                ? '连接中'
                : streamStatus === 'idle'
                  ? '待开始'
                  : streamStatus === 'failed'
                    ? '失败'
                    : '未连接'}
          </span>
        </header>
        <div
          ref={generalBodyRef}
          className="game-chat-body"
          role="log"
          aria-live="polite"
        >
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
                liveTypingEnabled={liveTypingEnabled}
                onTypingFrame={scrollGeneralToBottom}
              />
            ))
          )}
        </div>
        {voteCounts && (
          <VoteHistogram
            counts={voteCounts.counts}
            abstainCount={voteCounts.abstainCount}
          />
        )}
      </section>
      <section
        className="game-chat-panel game-chat-panel--wolf"
        aria-label="狼人聊天框"
      >
        <header className="game-chat-header">狼人聊天框</header>
        <div
          ref={wolfBodyRef}
          className="game-chat-body"
          role="log"
          aria-live="polite"
        >
          {wolfRows.length === 0 ? (
            <p className="game-event-line game-event-line--system">
              等待狼人夜聊。
            </p>
          ) : (
            wolfRows.map((event, index) => (
              <Fragment key={`${event.seq}-wolf-chat`}>
                {shouldShowWolfNightDivider(wolfRows, index) && (
                  <div className="game-wolf-night-divider" role="separator">
                    <span>{wolfNightLabel(event.day)}</span>
                  </div>
                )}
                <WolfChatLine
                  event={event}
                  assignments={assignments}
                  liveTypingEnabled={liveTypingEnabled}
                  onTypingFrame={scrollWolfToBottom}
                />
              </Fragment>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function NarrativeLine({
  row,
  assignments,
  liveTypingEnabled,
  onTypingFrame,
}: {
  row: NarrativeRow;
  assignments: (number | null)[];
  liveTypingEnabled: boolean;
  onTypingFrame: () => void;
}) {
  const slotIndex = row.actor === null ? null : assignments[row.actor - 1];
  const slot = slotIndex === null ? null : MODEL_SLOTS[slotIndex];

  if (row.kind === 'speech' && slot) {
    return (
      <article className="game-narrative-line game-narrative-line--speech">
        <img src={slot.iconPath} alt="" className="game-narrative-avatar" />
        <div>
          <strong>{slot.nickname}</strong>
          <p>
            <TypewriterText
              text={row.text}
              enabled={liveTypingEnabled}
              onFrame={onTypingFrame}
            />
          </p>
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

function WolfChatLine({
  event,
  assignments,
  liveTypingEnabled,
  onTypingFrame,
}: {
  event: GameEvent;
  assignments: (number | null)[];
  liveTypingEnabled: boolean;
  onTypingFrame: () => void;
}) {
  const slotIndex = event.actor === null ? null : assignments[event.actor - 1];
  const slot = slotIndex === null ? null : MODEL_SLOTS[slotIndex];
  const actorLabel = event.actor === null ? '狼人' : `${event.actor}号`;

  return (
    <article className="game-narrative-line game-narrative-line--wolf">
      {slot && <img src={slot.iconPath} alt="" className="game-narrative-avatar" />}
      <div>
        <strong>{slot ? `${actorLabel} ${slot.nickname}` : actorLabel}</strong>
        <p>
          <TypewriterText
            text={String(event.payload.text ?? '')}
            enabled={liveTypingEnabled}
            onFrame={onTypingFrame}
          />
        </p>
      </div>
    </article>
  );
}

function TypewriterText({
  text,
  enabled,
  onFrame,
}: {
  text: string;
  enabled: boolean;
  onFrame: () => void;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [elapsedMs, setElapsedMs] = useState(() =>
    enabled && !reducedMotion ? 0 : TYPEWRITER_DURATION_MS,
  );
  const shouldAnimate = enabled && !reducedMotion && text.length > 0;
  const visibleText = typewriterVisibleText(text, {
    elapsedMs,
    enabled: shouldAnimate,
    reducedMotion,
  });
  const complete = visibleText === text;

  useEffect(() => {
    if (!shouldAnimate) {
      setElapsedMs(TYPEWRITER_DURATION_MS);
      return undefined;
    }

    let frameId = 0;
    const startedAt = window.performance.now();
    setElapsedMs(0);

    const tick = (now: number) => {
      const nextElapsed = now - startedAt;
      setElapsedMs(nextElapsed);
      if (nextElapsed < TYPEWRITER_DURATION_MS) {
        frameId = window.requestAnimationFrame(tick);
      }
    };

    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [shouldAnimate, text]);

  useEffect(() => {
    if (shouldAnimate) {
      onFrame();
    }
  }, [onFrame, shouldAnimate, visibleText]);

  return (
    <span
      className={[
        'game-typewriter-text',
        shouldAnimate && !complete ? 'game-typewriter-text--active' : '',
      ].join(' ')}
    >
      {visibleText}
    </span>
  );
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => prefersReducedMotion());

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener?.('change', update);
    return () => media.removeEventListener?.('change', update);
  }, []);

  return reduced;
}

function prefersReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function scrollChatBodyToBottom(
  element: Pick<HTMLDivElement, 'scrollHeight' | 'scrollTo'> | null,
  enabled: boolean,
) {
  if (!enabled || element === null) {
    return;
  }
  element.scrollTo({
    top: element.scrollHeight,
    behavior: chatScrollBehavior(),
  });
}

export function chatScrollBehavior(): ScrollBehavior {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'smooth';
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth';
}

export function shouldShowWolfNightDivider(
  events: { day?: unknown }[],
  index: number,
) {
  if (index < 0 || index >= events.length) {
    return false;
  }
  if (index === 0) {
    return true;
  }
  return wolfNightKey(events[index]?.day) !== wolfNightKey(events[index - 1]?.day);
}

export function wolfNightLabel(day: unknown) {
  const night = wolfNightKey(day);
  return night === null ? '夜晚' : `第${night}晚`;
}

function wolfNightKey(day: unknown) {
  return typeof day === 'number' && Number.isInteger(day) && day > 0
    ? day
    : null;
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
      return {
        counts: event.payload.counts as Record<string, unknown>,
        abstainCount: event.payload.abstain_count,
      };
    }
  }
  return null;
}
