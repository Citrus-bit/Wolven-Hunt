import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Minus, Plus, Send } from 'lucide-react';
import type { GameEvent, NarrativeRow, TurnRequest } from '../../lib/gameApi';
import {
  resolveSeatDisplay,
  type SeatPresentationMap,
} from '../../lib/seatPresentation';
import {
  TYPEWRITER_DURATION_MS,
  typewriterVisibleText,
} from '../../lib/typewriter';
import { VoteHistogram } from './VoteHistogram';

type GameChatProps = {
  events: GameEvent[];
  narrativeRows: NarrativeRow[];
  assignments: (number | null)[];
  seatPresentation?: SeatPresentationMap;
  streamStatus: 'idle' | 'connecting' | 'open' | 'error' | 'failed';
  autoScrollEnabled: boolean;
  liveTypingEnabled: boolean;
  inputKind?: Extract<TurnRequest['kind'], 'speech' | 'wolf_chat' | 'last_words'> | null;
  inputEnabled?: boolean;
  inputMaxChars?: number;
  secondsLeft?: number | null;
  onSubmitText?: (text: string) => void;
};

export function GameChat({
  events,
  narrativeRows,
  assignments,
  seatPresentation = {},
  streamStatus,
  autoScrollEnabled,
  liveTypingEnabled,
  inputKind = null,
  inputEnabled = false,
  inputMaxChars = 300,
  secondsLeft = null,
  onSubmitText,
}: GameChatProps) {
  const generalBodyRef = useRef<HTMLDivElement | null>(null);
  const wolfBodyRef = useRef<HTMLDivElement | null>(null);
  const [generalExpanded, setGeneralExpanded] = useState(false);
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
    <div className={gameChatClassName(generalExpanded)} aria-label="游戏聊天区">
      <section
        className="game-chat-panel game-chat-panel--general"
        aria-label="通用聊天框"
      >
        <GeneralChatHeader
          streamStatus={streamStatus}
          generalExpanded={generalExpanded}
          onToggleGeneralExpanded={() => setGeneralExpanded((expanded) => !expanded)}
        />
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
                seatPresentation={seatPresentation}
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
        {inputKind && inputKind !== 'wolf_chat' && (
          <ChatInput
            kind={inputKind}
            enabled={inputEnabled}
            maxChars={inputMaxChars}
            secondsLeft={secondsLeft}
            onSubmitText={onSubmitText}
          />
        )}
      </section>
      <section
        id="game-chat-wolf-panel"
        className="game-chat-panel game-chat-panel--wolf"
        aria-label="狼人聊天框"
        aria-hidden={generalExpanded}
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
                  seatPresentation={seatPresentation}
                  liveTypingEnabled={liveTypingEnabled}
                  onTypingFrame={scrollWolfToBottom}
                />
              </Fragment>
            ))
          )}
        </div>
        {inputKind === 'wolf_chat' && (
          <ChatInput
            kind={inputKind}
            enabled={inputEnabled}
            maxChars={inputMaxChars}
            secondsLeft={secondsLeft}
            onSubmitText={onSubmitText}
          />
        )}
      </section>
    </div>
  );
}

function ChatInput({
  kind,
  enabled,
  maxChars,
  secondsLeft,
  onSubmitText,
}: {
  kind: Extract<TurnRequest['kind'], 'speech' | 'wolf_chat' | 'last_words'>;
  enabled: boolean;
  maxChars: number;
  secondsLeft: number | null;
  onSubmitText?: (text: string) => void;
}) {
  const [text, setText] = useState('');

  useEffect(() => {
    setText('');
  }, [kind]);

  const submit = () => {
    const trimmed = text.trim();
    if (!enabled || !trimmed) {
      return;
    }
    onSubmitText?.(trimmed);
    setText('');
  };

  return (
    <footer className="game-chat-footer">
      <label className="game-chat-seat">
        <span>{TEXT_TURN_LABELS[kind]}</span>
        <span>{secondsLeft === null ? '' : `${secondsLeft}s`}</span>
      </label>
      <textarea
        className="game-chat-input"
        value={text}
        maxLength={maxChars}
        disabled={!enabled}
        rows={2}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <button
        type="button"
        className="game-chat-submit"
        disabled={!enabled || text.trim().length === 0}
        onClick={submit}
        aria-label="提交文本"
      >
        <Send size={16} strokeWidth={2.5} aria-hidden="true" />
      </button>
    </footer>
  );
}

export function GeneralChatHeader({
  streamStatus,
  generalExpanded,
  onToggleGeneralExpanded,
}: {
  streamStatus: GameChatProps['streamStatus'];
  generalExpanded: boolean;
  onToggleGeneralExpanded: () => void;
}) {
  const Icon = generalExpanded ? Minus : Plus;

  return (
    <header className="game-chat-header">
      <span className="game-chat-title">通用聊天框</span>
      <span className="game-chat-header-actions">
        <span className={`game-stream-status game-stream-status--${streamStatus}`}>
          {streamStatusLabel(streamStatus)}
        </span>
        <button
          type="button"
          className="game-chat-expand-toggle"
          aria-label={generalExpanded ? '还原通用聊天框' : '展开通用聊天框'}
          aria-expanded={generalExpanded}
          aria-controls="game-chat-wolf-panel"
          onClick={onToggleGeneralExpanded}
        >
          <Icon aria-hidden="true" strokeWidth={2.4} />
        </button>
      </span>
    </header>
  );
}

export function gameChatClassName(generalExpanded: boolean) {
  return generalExpanded
    ? 'game-chat game-chat--general-expanded'
    : 'game-chat';
}

const TEXT_TURN_LABELS: Record<
  Extract<TurnRequest['kind'], 'speech' | 'wolf_chat' | 'last_words'>,
  string
> = {
  speech: '发言',
  wolf_chat: '狼聊',
  last_words: '遗言',
};

function streamStatusLabel(streamStatus: GameChatProps['streamStatus']) {
  if (streamStatus === 'open') {
    return '已连接';
  }
  if (streamStatus === 'connecting') {
    return '连接中';
  }
  if (streamStatus === 'idle') {
    return '待开始';
  }
  if (streamStatus === 'failed') {
    return '失败';
  }
  return '未连接';
}

function NarrativeLine({
  row,
  assignments,
  seatPresentation,
  liveTypingEnabled,
  onTypingFrame,
}: {
  row: NarrativeRow;
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  liveTypingEnabled: boolean;
  onTypingFrame: () => void;
}) {
  const display =
    row.actor === null ? null : resolveSeatDisplay(row.actor, assignments, seatPresentation);

  if (row.kind === 'speech' && display) {
    return (
      <article className="game-narrative-line game-narrative-line--speech">
        <img src={display.iconPath} alt="" className="game-narrative-avatar" />
        <div>
          <strong>{display.nickname}</strong>
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
  seatPresentation,
  liveTypingEnabled,
  onTypingFrame,
}: {
  event: GameEvent;
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  liveTypingEnabled: boolean;
  onTypingFrame: () => void;
}) {
  const display =
    event.actor === null ? null : resolveSeatDisplay(event.actor, assignments, seatPresentation);
  const actorLabel = event.actor === null ? '狼人' : `${event.actor}号`;

  return (
    <article className="game-narrative-line game-narrative-line--wolf">
      {display && <img src={display.iconPath} alt="" className="game-narrative-avatar" />}
      <div>
        <strong>{display ? `${actorLabel} ${display.nickname}` : actorLabel}</strong>
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
