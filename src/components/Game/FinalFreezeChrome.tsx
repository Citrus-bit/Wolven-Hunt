import { ChevronDown, ChevronUp, LogOut, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  getReveal,
  type GameEvent,
  type RoleReveal,
} from '../../lib/gameApi';
import {
  resolveSeatDisplay,
  type SeatPresentationMap,
} from '../../lib/seatPresentation';

type FinalFreezeChromeProps = {
  gameId: string | null;
  events: GameEvent[];
  assignments: (number | null)[];
  seatPresentation: SeatPresentationMap;
  isReplay: boolean;
  onExitGame: () => void;
};

const ROLE_LABELS: Record<string, string> = {
  wolf: '狼人',
  villager: '村民',
  seer: '预言家',
  witch: '女巫',
  guard: '守卫',
};

export function FinalFreezeChrome({
  gameId,
  events,
  assignments,
  seatPresentation,
  isReplay,
  onExitGame,
}: FinalFreezeChromeProps) {
  const fallbackReveal = useMemo(() => roleRevealFromEvents(events), [events]);
  const [reveal, setReveal] = useState<RoleReveal | null>(fallbackReveal);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasRevealEvent = events.some((event) => event.type === 'role_reveal');

  useEffect(() => {
    if (fallbackReveal) {
      setReveal(fallbackReveal);
      setErrorMessage(null);
    }
  }, [fallbackReveal]);

  useEffect(() => {
    if (!gameId || !hasRevealEvent || fallbackReveal) {
      return;
    }
    let cancelled = false;
    getReveal(gameId)
      .then((payload) => {
        if (!cancelled) {
          setReveal(payload);
          setErrorMessage(null);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '终局加载失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [fallbackReveal, gameId, hasRevealEvent]);

  if (!reveal) {
    return null;
  }

  const winnerLabel = reveal.winner === 'wolf' ? '狼人胜利' : '好人胜利';

  return (
    <aside className="final-freeze-chrome" aria-live="polite">
      {drawerOpen && (
        <section className="final-freeze-drawer" aria-label="终局复盘">
          <div className="final-freeze-seat-grid">
            {reveal.seats.map((seat) => {
              const display = resolveSeatDisplay(
                seat.seat,
                assignments,
                seatPresentation,
              );
              return (
                <article
                  className={[
                    'final-freeze-seat',
                    seat.alive ? 'final-freeze-seat--alive' : 'final-freeze-seat--out',
                  ].join(' ')}
                  key={seat.seat}
                >
                  {display?.iconPath ? (
                    <img src={display.iconPath} alt="" />
                  ) : (
                    <span className="final-freeze-seat-placeholder" aria-hidden="true">
                      {seat.seat}号
                    </span>
                  )}
                  <div>
                    <strong>{seat.seat}号 {display?.nickname ?? `${seat.seat}号`}</strong>
                    <span>{ROLE_LABELS[seat.role] ?? seat.role} · {seat.alive ? '存活' : '出局'}</span>
                  </div>
                </article>
              );
            })}
          </div>
          {reveal.highlights.length > 0 && (
            <ol className="final-freeze-highlights">
              {reveal.highlights.map((highlight) => (
                <li key={`${highlight.seq}-${highlight.summary}`}>
                  {highlight.summary}
                </li>
              ))}
            </ol>
          )}
          {errorMessage && (
            <p className="final-freeze-error">{errorMessage}</p>
          )}
        </section>
      )}
      <section className="final-freeze-banner" aria-label="终局定格">
        <div>
          <strong>{winnerLabel}</strong>
          <span>终局定格</span>
        </div>
        <div className="final-freeze-actions">
          <button
            type="button"
            className="final-freeze-btn"
            onClick={() => setDrawerOpen((value) => !value)}
            aria-expanded={drawerOpen}
          >
            {drawerOpen ? (
              <ChevronDown size={18} aria-hidden="true" />
            ) : (
              <ChevronUp size={18} aria-hidden="true" />
            )}
            {drawerOpen ? '收起' : '复盘'}
          </button>
          <button
            type="button"
            className="final-freeze-btn final-freeze-btn--primary"
            onClick={onExitGame}
          >
            {isReplay ? (
              <LogOut size={18} aria-hidden="true" />
            ) : (
              <RotateCcw size={18} aria-hidden="true" />
            )}
            {isReplay ? '返回大厅' : '再来一局'}
          </button>
        </div>
      </section>
    </aside>
  );
}

function roleRevealFromEvents(events: GameEvent[]): RoleReveal | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type !== 'role_reveal') {
      continue;
    }
    const payload = event.payload;
    if (
      typeof payload.winner === 'string' &&
      Array.isArray(payload.seats) &&
      Array.isArray(payload.highlights)
    ) {
      return payload as RoleReveal;
    }
  }
  return null;
}
