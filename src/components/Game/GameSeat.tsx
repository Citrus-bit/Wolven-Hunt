import { Check, Plus, X as XIcon } from 'lucide-react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import type { ModelTestStatus } from '../../lib/modelTest';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  testStatus?: ModelTestStatus;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  testStatus,
  onClickSeat,
}: GameSeatProps) {
  const isEmpty = assignment === null;
  const slot = isEmpty ? null : MODEL_SLOTS[assignment];
  const isTesting = testStatus === 'testing';
  const showBadge = testStatus === 'pass' || testStatus === 'fail';
  const resultLabel = testStatus === 'pass' ? '测试通过' : '测试失败';
  const label = slot
    ? `更换 ${slot.nickname}`
    : `添加第 ${seatIndex + 1} 号席位的模型`;

  return (
    <div className={`game-seat game-seat--${side}`} data-seat-index={seatIndex}>
      <button
        type="button"
        className={`game-seat-circle ${
          isTesting ? 'game-seat-circle--testing' : ''
        }`}
        aria-label={label}
        onClick={() => onClickSeat(seatIndex)}
        disabled={isTesting}
      >
        {slot ? (
          <img src={slot.iconPath} alt="" className="game-seat-avatar" />
        ) : (
          <Plus aria-hidden="true" size={36} strokeWidth={2.5} />
        )}
        <span className="game-seat-number">{seatIndex + 1}</span>
        {isTesting && (
          <span className="game-seat-dots" aria-hidden="true">
            <span className="dot dot-1" />
            <span className="dot dot-2" />
            <span className="dot dot-3" />
          </span>
        )}
      </button>
      {showBadge && (
        <span
          className={`game-seat-badge game-seat-badge--${testStatus}`}
          aria-label={resultLabel}
        >
          {testStatus === 'pass' ? (
            <Check size={16} strokeWidth={3} aria-hidden="true" />
          ) : (
            <XIcon size={16} strokeWidth={3} aria-hidden="true" />
          )}
        </span>
      )}
      <span className="game-seat-nickname">{slot?.nickname ?? ''}</span>
      <span className="game-seat-role" aria-label="身份" />
    </div>
  );
}
