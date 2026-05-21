import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type LobbyModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  variant?: 'default' | 'settings';
  children: ReactNode;
};

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function LobbyModal({
  open,
  onClose,
  title,
  variant = 'default',
  children,
}: LobbyModalProps) {
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
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="lobby-modal-backdrop" onMouseDown={onClose}>
      <div
        ref={rootRef}
        className={`lobby-modal-frame lobby-modal-frame--${variant}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <img
          src="/assets/lobby/settings_panel_bg.png"
          alt=""
          className="lobby-modal-bg"
          loading="eager"
        />
        <button
          type="button"
          className="lobby-modal-close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X aria-hidden="true" size={20} strokeWidth={2.25} />
        </button>
        <div className="lobby-modal-content">
          <h2 id={titleId} className="lobby-modal-title">
            {title}
          </h2>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
