import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type ExitConfirmModalProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function ExitConfirmModal({
  open,
  onClose,
  onConfirm,
}: ExitConfirmModalProps) {
  const titleId = useId();
  const descriptionId = useId();
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
    <div className="exit-confirm-backdrop" onMouseDown={onClose}>
      <div
        ref={rootRef}
        className="exit-confirm-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="exit-confirm-close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X aria-hidden="true" size={18} strokeWidth={2.25} />
        </button>
        <p className="exit-confirm-kicker">返回大厅</p>
        <h2 id={titleId} className="exit-confirm-title">
          退出游戏
        </h2>
        <p id={descriptionId} className="exit-confirm-text">
          确定要退出当前游戏返回大厅吗？当前席位分配与测试结果不会被保存。
        </p>
        <div className="exit-confirm-actions">
          <button
            type="button"
            className="exit-confirm-btn exit-confirm-btn--cancel"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="exit-confirm-btn exit-confirm-btn--confirm"
            onClick={onConfirm}
          >
            确认退出
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
