import { useEffect, useMemo, useState } from 'react';
import type { GameTimings } from '../../lib/gameApi';
import {
  phaseCountdownText,
  phaseDurationMs,
  phaseStatusText,
} from '../../lib/phaseDescriptor';

type GamePhaseHeaderProps = {
  phase: string | null;
  timings: GameTimings | null;
  speakerSeat?: number | null;
  speechComplete?: boolean;
};

export function GamePhaseHeader({
  phase,
  timings,
  speakerSeat,
  speechComplete = false,
}: GamePhaseHeaderProps) {
  const durationMs = useMemo(() => phaseDurationMs(phase, timings), [phase, timings]);
  const [remainingMs, setRemainingMs] = useState(durationMs);

  useEffect(() => {
    setRemainingMs(durationMs);
    if (durationMs <= 0 || speechComplete) {
      return undefined;
    }
    const startedAt = window.performance.now();
    const timer = window.setInterval(() => {
      const elapsed = window.performance.now() - startedAt;
      setRemainingMs(Math.max(0, durationMs - elapsed));
    }, 250);
    return () => window.clearInterval(timer);
  }, [durationMs, phase, speakerSeat, speechComplete]);

  const countdownText = phaseCountdownText(phase, durationMs, remainingMs, {
    speakerSeat,
    speechComplete,
  });

  return (
    <div className="game-phase-header" aria-live="polite">
      <span className="game-phase-countdown">{countdownText}</span>
      <span className="game-phase-status">
        {phaseStatusText(phase, speakerSeat, speechComplete)}
      </span>
    </div>
  );
}
