import { useEffect, useState } from 'react';
import { getReveal, type GameEvent, type RoleReveal } from '../../lib/gameApi';
import { MODEL_SLOTS } from '../../lib/modelConfigs';

type FinalRevealOverlayProps = {
  gameId: string | null;
  events: GameEvent[];
  assignments: (number | null)[];
  onExitGame: () => void;
};

const ROLE_LABELS: Record<string, string> = {
  wolf: '狼人',
  villager: '村民',
  seer: '预言家',
  witch: '女巫',
  guard: '守卫',
};

export function FinalRevealOverlay({
  gameId,
  events,
  assignments,
  onExitGame,
}: FinalRevealOverlayProps) {
  const [reveal, setReveal] = useState<RoleReveal | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const hasRevealEvent = events.some((event) => event.type === 'role_reveal');

  useEffect(() => {
    if (!gameId || !hasRevealEvent || reveal) {
      return;
    }
    getReveal(gameId)
      .then((payload) => {
        setReveal(payload);
        setErrorMessage(null);
      })
      .catch((error) => {
        const fallback = events.find((event) => event.type === 'role_reveal');
        if (fallback) {
          setReveal(fallback.payload as RoleReveal);
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : '结局揭晓加载失败');
      });
  }, [gameId, hasRevealEvent, reveal]);

  if (!reveal && !errorMessage) {
    return null;
  }

  if (!reveal) {
    return (
      <div className="final-reveal-overlay" role="dialog" aria-modal="true">
        <section className="final-reveal-panel">
          <header className="final-reveal-header">
            <span>结局加载失败</span>
            <button type="button" onClick={onExitGame}>
              返回大厅
            </button>
          </header>
          <p className="final-reveal-error">{errorMessage}</p>
        </section>
      </div>
    );
  }

  return (
    <div className="final-reveal-overlay" role="dialog" aria-modal="true">
      <section className="final-reveal-panel">
        <header className="final-reveal-header">
          <span>{reveal.winner === 'wolf' ? '狼人胜利' : '好人胜利'}</span>
          <button type="button" onClick={onExitGame}>
            再来一局
          </button>
        </header>
        <div className="final-reveal-seats">
          {reveal.seats.map((seat) => {
            const slotIndex = assignments[seat.seat - 1];
            const slot = slotIndex === null ? null : MODEL_SLOTS[slotIndex];
            return (
              <article className="final-reveal-seat" key={seat.seat}>
                {slot && <img src={slot.iconPath} alt="" />}
                <strong>{seat.seat}号 {slot?.nickname ?? '未命名'}</strong>
                <span>{ROLE_LABELS[seat.role] ?? seat.role}</span>
                <small>{seat.alive ? '存活' : '出局'}</small>
              </article>
            );
          })}
        </div>
        <ol className="final-reveal-highlights">
          {reveal.highlights.map((highlight) => (
            <li key={`${highlight.seq}-${highlight.summary}`}>{highlight.summary}</li>
          ))}
        </ol>
        <button
          type="button"
          className="final-reveal-raw-toggle"
          onClick={() => setShowRaw((value) => !value)}
        >
          查看完整事件
        </button>
        {showRaw && (
          <pre className="final-reveal-raw">
            {JSON.stringify(events.slice(-120), null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
