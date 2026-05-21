import { Moon, Sun } from 'lucide-react';
import type { GameStage } from '../../lib/gameStage';

type StageIndicatorProps = {
  stage: GameStage;
};

export function StageIndicator({ stage }: StageIndicatorProps) {
  const Icon = stage.phase === 'day' ? Sun : Moon;
  const label = `第 ${stage.dayNumber} 天 ${
    stage.phase === 'day' ? '白天' : '黑夜'
  }`;

  return (
    <div className="game-stage-indicator" aria-label={label}>
      <Icon
        size={36}
        strokeWidth={2.2}
        className={`game-stage-icon game-stage-icon--${stage.phase}`}
        aria-hidden="true"
      />
      <span className="game-stage-day-label" aria-hidden="true">
        第{stage.dayNumber}天
      </span>
    </div>
  );
}
