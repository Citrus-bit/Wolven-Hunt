import { useState } from 'react';
import { GameSeat } from './GameSeat';
import { ModelPicker } from './ModelPicker';

const SEAT_COUNT = 8;
const leftSeats = [0, 1, 2, 3];
const rightSeats = [4, 5, 6, 7];

export function GamePage() {
  const [assignments, setAssignments] = useState<(number | null)[]>(() =>
    Array.from({ length: SEAT_COUNT }, () => null),
  );
  const [pickerSeat, setPickerSeat] = useState<number | null>(null);

  const handleClickSeat = (seatIndex: number) => {
    setPickerSeat(seatIndex);
  };

  const handlePickModel = (slotIndex: number) => {
    if (pickerSeat === null) {
      return;
    }

    setAssignments((prev) => {
      const next = [...prev];
      next[pickerSeat] = slotIndex;
      return next;
    });
    setPickerSeat(null);
  };

  return (
    <main className="game-page" aria-label="Wolven Hunt 游戏准备">
      <img
        src="/assets/game/day_bg.png"
        alt=""
        className="game-bg"
        loading="eager"
      />
      <div className="game-seats" aria-label="席位区">
        <div className="game-seats-col game-seats-col--left">
          {leftSeats.map((seatIndex) => (
            <GameSeat
              key={seatIndex}
              seatIndex={seatIndex}
              side="left"
              assignment={assignments[seatIndex]}
              onClickSeat={handleClickSeat}
            />
          ))}
        </div>
        <div className="game-seats-col game-seats-col--right">
          {rightSeats.map((seatIndex) => (
            <GameSeat
              key={seatIndex}
              seatIndex={seatIndex}
              side="right"
              assignment={assignments[seatIndex]}
              onClickSeat={handleClickSeat}
            />
          ))}
        </div>
      </div>
      <ModelPicker
        open={pickerSeat !== null}
        onClose={() => setPickerSeat(null)}
        currentAssignment={pickerSeat !== null ? assignments[pickerSeat] : null}
        usedSlots={assignments.filter((slot): slot is number => slot !== null)}
        onPick={handlePickModel}
      />
    </main>
  );
}
