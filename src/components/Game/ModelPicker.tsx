import { MODEL_SLOTS } from '../../lib/modelConfigs';
import { LobbyModal } from '../Lobby/LobbyModal';

type ModelPickerProps = {
  open: boolean;
  onClose: () => void;
  currentAssignment: number | null;
  usedSlots: number[];
  onPick: (slotIndex: number) => void;
};

export function ModelPicker({
  open,
  onClose,
  currentAssignment,
  usedSlots,
  onPick,
}: ModelPickerProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="选择模型">
      <div className="model-picker-grid" role="list">
        {MODEL_SLOTS.map((slot) => {
          const isCurrent = currentAssignment === slot.slot;
          const isUsedByOther = usedSlots.includes(slot.slot) && !isCurrent;

          return (
            <button
              key={slot.slot}
              type="button"
              className={`model-picker-card ${
                isCurrent ? 'model-picker-card--current' : ''
              } ${isUsedByOther ? 'model-picker-card--disabled' : ''}`}
              role="listitem"
              disabled={isUsedByOther}
              onClick={() => {
                if (!isUsedByOther) {
                  onPick(slot.slot);
                }
              }}
            >
              <img src={slot.iconPath} alt="" className="model-picker-avatar" />
              <span className="model-picker-nickname">{slot.nickname}</span>
            </button>
          );
        })}
      </div>
    </LobbyModal>
  );
}
