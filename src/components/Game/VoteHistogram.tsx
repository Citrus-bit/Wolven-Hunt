type VoteHistogramProps = {
  counts: Record<string, unknown>;
  abstainCount?: unknown;
};

export function VoteHistogram({ counts, abstainCount = 0 }: VoteHistogramProps) {
  const rows = Object.entries(counts)
    .map(([seat, count]) => [seat, Number(count)] as const)
    .filter(([seat, count]) => Number.isFinite(Number(seat)) && Number.isFinite(count))
    .sort(([left], [right]) => Number(left) - Number(right));
  const abstainNumber = Number(abstainCount);
  const showAbstain = Number.isFinite(abstainNumber) && abstainNumber > 0;
  const max = Math.max(
    1,
    ...rows.map(([, count]) => count),
    showAbstain ? abstainNumber : 0,
  );

  if (rows.length === 0 && !showAbstain) {
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
      {showAbstain && (
        <div className="vote-histogram-row" key="abstain">
          <span className="vote-histogram-label">弃票</span>
          <span className="vote-histogram-track">
            <span
              className="vote-histogram-bar"
              style={{ width: `${Math.round((abstainNumber / max) * 100)}%` }}
            />
          </span>
          <span className="vote-histogram-count">{abstainNumber}票</span>
        </div>
      )}
    </div>
  );
}
