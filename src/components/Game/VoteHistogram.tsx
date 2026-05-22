type VoteHistogramProps = {
  counts: Record<string, unknown>;
};

export function VoteHistogram({ counts }: VoteHistogramProps) {
  const rows = Object.entries(counts)
    .map(([seat, count]) => [seat, Number(count)] as const)
    .filter(([, count]) => Number.isFinite(count))
    .sort(([left], [right]) => Number(left) - Number(right));
  const max = Math.max(1, ...rows.map(([, count]) => count));

  if (rows.length === 0) {
    return null;
  }

  return (
    <div className="vote-histogram" aria-label="投票结果直方图">
      {rows.map(([seat, count]) => (
        <div className="vote-histogram-row" key={seat}>
          <span className="vote-histogram-label">{seat}号</span>
          <span className="vote-histogram-track">
            <span
              className="vote-histogram-bar"
              style={{ width: `${Math.round((count / max) * 100)}%` }}
            />
          </span>
          <span className="vote-histogram-count">{count}票</span>
        </div>
      ))}
    </div>
  );
}
