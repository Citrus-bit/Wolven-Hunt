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
        : '生成复盘报告';

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
  const modeLabel =
    report.generation_mode === 'real_ai' ? '真实AI生成' : '离线复盘';
  return (
    <section className="final-freeze-drawer final-freeze-report" aria-label="复盘报告">
      <div className="review-report-summary">
        <div>
          <span>结构化报告</span>
          <b
            className={[
              'review-report-mode',
              `review-report-mode--${report.generation_mode}`,
            ].join(' ')}
          >
            {modeLabel}
          </b>
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
          <h3>Leaderboard / 排行榜</h3>
        </div>
        <div className="review-leaderboard">
          {report.leaderboard.map((item) => (
            <article className="review-leaderboard-row" key={`${item.rank}-${item.seat}`}>
              <strong>#{item.rank}</strong>
              <div>
                <span>{item.seat}号 {item.nickname}</span>
                <small>{ROLE_LABELS[item.role] ?? item.role}</small>
                <p className="review-leaderboard-summary">{item.reason}</p>
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
              <div className="review-player-body">
                <RadarChart scores={player.scores} label={`${player.seat}号六边形评分`} />
                <div className="review-player-copy">
                  <p className="review-player-evaluation">{player.evaluation}</p>
                  <ReviewMiniList title="公开证据" items={player.evidence} />
                  <ReviewMiniList title="优点" items={player.strengths} />
                  <ReviewMiniList title="失误" items={player.mistakes} />
                  <ReviewMiniList title="下一局建议" items={player.suggestions} />
                </div>
              </div>
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

function RadarChart({
  scores,
  label,
}: {
  scores: ReviewReport['players'][number]['scores'];
  label: string;
}) {
  const safeScores = scores.slice(0, 6);
  const gridRings = [0.25, 0.5, 0.75, 1];
  const valuePoints = radarPoints(safeScores.map((score) => clampScore(score.value)));
  return (
    <div className="review-radar" aria-label={label}>
      <svg viewBox="0 0 160 160" role="img" aria-label={label}>
        {gridRings.map((ring) => (
          <polygon
            className="review-radar-grid"
            key={ring}
            points={radarPoints([100, 100, 100, 100, 100, 100], ring)}
          />
        ))}
        {safeScores.map((score, index) => (
          <line
            className="review-radar-axis"
            key={score.key}
            x1="80"
            y1="80"
            x2={axisPoint(index, 58).x}
            y2={axisPoint(index, 58).y}
          />
        ))}
        <polygon className="review-radar-value" points={valuePoints} />
        {safeScores.map((score, index) => {
          const point = axisPoint(index, (clampScore(score.value) / 100) * 58);
          return (
            <circle
              className="review-radar-dot"
              key={`${score.key}-dot`}
              cx={point.x}
              cy={point.y}
              r="3"
            />
          );
        })}
      </svg>
      <dl className="review-radar-list">
        {safeScores.map((score) => (
          <div key={score.key}>
            <dt>{score.label}</dt>
            <dd>{clampScore(score.value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ReviewMiniList({ title, items }: { title: string; items: string[] }) {
  const visible = items.filter((item) => item.trim()).slice(0, 2);
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className="review-mini-list">
      <strong>{title}</strong>
      <ul>
        {visible.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function radarPoints(values: number[], ringScale = 1) {
  return values
    .map((value, index) => {
      const radius = (clampScore(value) / 100) * 58 * ringScale;
      const point = axisPoint(index, radius);
      return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    })
    .join(' ');
}

function axisPoint(index: number, radius: number) {
  const angle = -Math.PI / 2 + index * (Math.PI / 3);
  return {
    x: 80 + Math.cos(angle) * radius,
    y: 80 + Math.sin(angle) * radius,
  };
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
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
