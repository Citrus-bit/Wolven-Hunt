import { Plus } from 'lucide-react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  onClickSeat,
}: GameSeatProps) {
  const isEmpty = assignment === null;
  const slot = isEmpty ? null : MODEL_SLOTS[assignment];
  const label = slot
    ? `更换 ${slot.nickname}`
    : `添加第 ${seatIndex + 1} 号席位的模型`;

  return (
    <div className={`game-seat game-seat--${side}`} data-seat-index={seatIndex}>
      <button
        type="button"
        className="game-seat-circle"
        aria-label={label}
        onClick={() => onClickSeat(seatIndex)}
      >
        {slot ? (
          <img src={slot.iconPath} alt="" className="game-seat-avatar" />
        ) : (
          <Plus aria-hidden="true" size={36} strokeWidth={2.5} />
        )}
        <span className="game-seat-number">{seatIndex + 1}</span>
      </button>
      <span className="game-seat-nickname">{slot?.nickname ?? ''}</span>
      <span className="game-seat-role" aria-label="身份" />
    </div>
  );
}
