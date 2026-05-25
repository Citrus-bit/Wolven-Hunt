import {
  BarChart3,
  FileText,
  LoaderCircle,
  LogOut,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  generateReviewReport,
  getReviewReport,
  getReveal,
  type GameEvent,
  type ReviewReport,
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
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportStatus, setReportStatus] = useState<
    'idle' | 'loading' | 'ready' | 'error'
  >('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reportErrorMessage, setReportErrorMessage] = useState<string | null>(null);
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

  useEffect(() => {
    if (!gameId || !reveal) {
      return undefined;
    }
    let cancelled = false;
    getReviewReport(gameId)
      .then((payload) => {
        if (!cancelled) {
          setReport(payload);
          setReportStatus('ready');
          setReportErrorMessage(null);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [gameId, reveal]);

  if (!reveal) {
    return null;
  }

  const winnerLabel = reveal.winner === 'wolf' ? '狼人胜利' : '好人胜利';
  const reportButtonLabel =
    reportStatus === 'loading'
      ? '正在生成中'
      : reportStatus === 'ready'
        ? '查阅报告'
        : 'AI一键生成复盘报告';

  const handleReportClick = () => {
    if (!gameId || reportStatus === 'loading') {
      return;
    }
    if (reportStatus === 'ready') {
      setReportOpen((value) => !value);
      return;
    }
    setReportStatus('loading');
    setReportErrorMessage(null);
    generateReviewReport(gameId)
      .then((payload) => {
        setReport(payload);
        setReportStatus('ready');
        setReportOpen(true);
      })
      .catch((error) => {
        setReportStatus('error');
        setReportErrorMessage(
          error instanceof Error ? error.message : '复盘报告生成失败',
        );
      });
  };

  return (
    <aside className="final-freeze-chrome" aria-live="polite">
      {reportOpen && report && (
        <ReviewReportDrawer report={report} />
      )}
      <section className="final-freeze-banner" aria-label="终局定格">
        <div>
          <strong>{winnerLabel}</strong>
          <span>终局定格</span>
        </div>
        <div className="final-freeze-actions">
          <button
            type="button"
            className={[
              'final-freeze-btn',
              reportStatus === 'loading' ? 'final-freeze-btn--loading' : '',
              reportStatus === 'ready' ? 'final-freeze-btn--report-ready' : '',
            ].join(' ')}
            onClick={handleReportClick}
            aria-expanded={reportOpen}
            disabled={reportStatus === 'loading' || !gameId}
          >
            {reportStatus === 'loading' ? (
              <LoaderCircle
                className="final-freeze-spinner"
                size={18}
                aria-hidden="true"
              />
            ) : reportStatus === 'ready' ? (
              <FileText size={18} aria-hidden="true" />
            ) : (
              <Sparkles size={18} aria-hidden="true" />
            )}
            {reportButtonLabel}
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
      {(errorMessage || reportErrorMessage) && (
        <p className="final-freeze-error final-freeze-error--banner">
          {reportErrorMessage ?? errorMessage}
        </p>
      )}
    </aside>
  );
}

export function ReviewReportDrawer({ report }: { report: ReviewReport }) {
  const sortedPlayers = [...report.players].sort(
    (left, right) => right.overall_score - left.overall_score,
  );
  return (
    <section className="final-freeze-drawer final-freeze-report" aria-label="AI复盘报告">
      <div className="review-report-summary">
        <div>
          <span>结构化报告</span>
          <h2>{report.summary.verdict}</h2>
          <p>{report.summary.overall_assessment}</p>
        </div>
        {report.summary.turning_points.length > 0 && (
          <ol>
            {report.summary.turning_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ol>
        )}
      </div>

      <section className="review-report-section" aria-label="Leaderboard">
        <div className="review-report-section-title">
          <BarChart3 size={16} aria-hidden="true" />
          <h3>Leaderboard</h3>
        </div>
        <div className="review-leaderboard">
          {report.leaderboard.map((item) => (
            <article className="review-leaderboard-row" key={`${item.rank}-${item.seat}`}>
              <strong>#{item.rank}</strong>
              <div>
                <span>{item.seat}号 {item.nickname}</span>
                <small>{ROLE_LABELS[item.role] ?? item.role} · {item.reason}</small>
              </div>
              <b>{item.overall_score}</b>
            </article>
          ))}
        </div>
      </section>

      <section className="review-report-section" aria-label="玩家可视化打分">
        <div className="review-report-section-title">
          <BarChart3 size={16} aria-hidden="true" />
          <h3>玩家打分与建议</h3>
        </div>
        <div className="review-player-grid">
          {sortedPlayers.map((player) => (
            <article className="review-player-row" key={player.seat}>
              <div className="review-player-header">
                <strong>{player.seat}号 {player.nickname}</strong>
                <span>
                  {ROLE_LABELS[player.role] ?? player.role} ·{' '}
                  {player.alive ? '存活' : '出局'} · 综合 {player.overall_score}
                </span>
              </div>
              <ScoreBar label="发言" value={player.speech_score} />
              <ScoreBar label="投票" value={player.vote_score} />
              <ScoreBar label="技能" value={player.skill_score} />
              <p>{firstText(player.suggestions, '建议下一局把公开逻辑、票型和身份收益讲得更清楚。')}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="review-report-section" aria-label="关键决策复盘">
        <h3>关键决策复盘</h3>
        <div className="review-analysis-list">
          {report.key_decisions.map((decision) => (
            <article key={`${decision.phase}-${decision.seq ?? decision.title}`}>
              <strong>{decision.title}</strong>
              <span>第{decision.day}天 · {decision.phase}{decision.seq ? ` · #${decision.seq}` : ''}</span>
              <p>{decision.analysis}</p>
              <p>{decision.impact}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="review-report-section" aria-label="反事实推演">
        <h3>反事实推演</h3>
        <div className="review-analysis-list">
          {report.counterfactuals.map((item) => (
            <article key={item.premise}>
              <strong>{item.premise}</strong>
              <p>{item.likely_outcome}</p>
              <p>{item.lesson}</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const width = `${Math.max(0, Math.min(100, value))}%`;
  return (
    <div className="review-score-row">
      <span>{label}</span>
      <div className="review-score-track">
        <i style={{ width }} />
      </div>
      <b>{value}</b>
    </div>
  );
}

function firstText(values: string[], fallback: string) {
  return values.find((value) => value.trim()) ?? fallback;
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
