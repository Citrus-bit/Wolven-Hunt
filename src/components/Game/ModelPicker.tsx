import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeftRight, X } from 'lucide-react';
import { MODEL_SLOTS } from '../../lib/modelConfigs';

type ModelPickerProps = {
  open: boolean;
  onClose: () => void;
  currentAssignment: number | null;
  usedSlots: number[];
  onPick: (slotIndex: number) => void;
  onSwap: (slotIndex: number) => void;
};

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function ModelPicker({
  open,
  onClose,
  currentAssignment,
  usedSlots,
  onPick,
  onSwap,
}: ModelPickerProps) {
  const titleId = useId();
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    rootRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const root = rootRef.current;
      if (!root) {
        return;
      }

      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>(focusableSelector),
      ).filter((element) => !element.hasAttribute('disabled'));

      if (focusable.length === 0) {
        event.preventDefault();
        root.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener('keydown', onKeyDown);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      lastFocusedRef.current?.focus?.();
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="model-picker-backdrop" onMouseDown={onClose}>
      <div
        ref={rootRef}
        className="model-picker-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="model-picker-close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X size={18} strokeWidth={2.25} aria-hidden="true" />
        </button>
        <h2 id={titleId} className="model-picker-title">
          选择模型
        </h2>
        <div className="model-picker-grid" role="list">
          {MODEL_SLOTS.map((slot) => {
            const isCurrent = currentAssignment === slot.slot;
            const isUsedByOther = usedSlots.includes(slot.slot) && !isCurrent;
            const canSwap = isUsedByOther && currentAssignment !== null;

            return (
              <div
                key={slot.slot}
                className={`model-picker-card ${
                  isCurrent ? 'model-picker-card--current' : ''
                } ${isUsedByOther ? 'model-picker-card--disabled' : ''}`}
                role="listitem"
              >
                <button
                  type="button"
                  className="model-picker-card-main"
                  disabled={isUsedByOther}
                  aria-label={
                    isCurrent
                      ? `当前已选择 ${slot.nickname}`
                      : `选择 ${slot.nickname}`
                  }
                  onClick={() => {
                    onPick(slot.slot);
                  }}
                >
                  <img
                    src={slot.iconPath}
                    alt=""
                    className="model-picker-avatar"
                  />
                  <span className="model-picker-nickname">{slot.nickname}</span>
                </button>
                {canSwap && (
                  <button
                    type="button"
                    className="model-picker-swap"
                    aria-label={`将当前席位与 ${slot.nickname} 交换`}
                    onClick={() => onSwap(slot.slot)}
                  >
                    <ArrowLeftRight
                      size={12}
                      strokeWidth={2.6}
                      aria-hidden="true"
                    />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>,
    document.body,
  );
}
