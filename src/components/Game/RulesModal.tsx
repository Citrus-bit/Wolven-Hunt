import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type RulesModalProps = {
  open: boolean;
  onClose: () => void;
};

type RuleBlock =
  | {
      id: string;
      type: 'heading';
      level: 1 | 2 | 3;
      text: string;
    }
  | {
      id: string;
      type: 'paragraph';
      text: string;
    }
  | {
      id: string;
      type: 'ul' | 'ol';
      items: string[];
    };

type RuleBlockInput =
  | Omit<Extract<RuleBlock, { type: 'heading' }>, 'id'>
  | Omit<Extract<RuleBlock, { type: 'paragraph' }>, 'id'>
  | Omit<Extract<RuleBlock, { type: 'ul' | 'ol' }>, 'id'>;

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function parseRulesMarkdown(content: string): RuleBlock[] {
  const blocks: RuleBlock[] = [];
  const paragraphLines: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];
  let nextId = 0;

  const pushBlock = (block: RuleBlockInput) => {
    blocks.push({ ...block, id: `rule-block-${nextId}` });
    nextId += 1;
  };

  const flushParagraph = () => {
    const text = paragraphLines.join(' ').trim();
    paragraphLines.length = 0;

    if (text) {
      pushBlock({ type: 'paragraph', text });
    }
  };

  const flushList = () => {
    if (listType && listItems.length > 0) {
      pushBlock({ type: listType, items: listItems });
    }

    listType = null;
    listItems = [];
  };

  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith('```')) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      pushBlock({
        type: 'heading',
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2].trim(),
      });
      continue;
    }

    const unorderedItem = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unorderedItem) {
      flushParagraph();

      if (listType !== 'ul') {
        flushList();
        listType = 'ul';
      }

      listItems.push(unorderedItem[1].trim());
      continue;
    }

    const orderedItem = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (orderedItem) {
      flushParagraph();

      if (listType !== 'ol') {
        flushList();
        listType = 'ol';
      }

      listItems.push(orderedItem[1].trim());
      continue;
    }

    flushList();
    paragraphLines.push(trimmed);
  }

  flushParagraph();
  flushList();

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);

  parts.forEach((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      nodes.push(<strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>);
    } else {
      nodes.push(part);
    }
  });

  return nodes;
}

function RulesDocument({ content }: { content: string }) {
  const blocks = useMemo(() => parseRulesMarkdown(content), [content]);

  return (
    <div className="rules-document">
      {blocks.map((block) => {
        if (block.type === 'heading') {
          if (block.level === 1) {
            return (
              <h3 key={block.id} className="rules-document-title">
                {renderInline(block.text)}
              </h3>
            );
          }

          if (block.level === 2) {
            return (
              <h4 key={block.id} className="rules-document-section">
                {renderInline(block.text)}
              </h4>
            );
          }

          return (
            <h5 key={block.id} className="rules-document-subsection">
              {renderInline(block.text)}
            </h5>
          );
        }

        if (block.type === 'paragraph') {
          return <p key={block.id}>{renderInline(block.text)}</p>;
        }

        const ListTag = block.type;

        return (
          <ListTag key={block.id}>
            {block.items.map((item, index) => (
              <li key={`${block.id}-${index}`}>{renderInline(item)}</li>
            ))}
          </ListTag>
        );
      })}
    </div>
  );
}

export function RulesModal({ open, onClose }: RulesModalProps) {
  const titleId = useId();
  const [content, setContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    let cancelled = false;
    setError(null);

    fetch('/assets/game/rules.md')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.text();
      })
      .then((text) => {
        if (!cancelled) {
          setContent(text);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : '加载失败');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

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
    <div className="rules-modal-backdrop" onMouseDown={onClose}>
      <div
        ref={rootRef}
        className="rules-modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="rules-modal-close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X aria-hidden="true" size={20} strokeWidth={2.25} />
        </button>
        <div className="rules-modal-header">
          <p className="rules-modal-eyebrow">Wolven Hunt</p>
          <h2 id={titleId}>规则手册</h2>
        </div>
        <article className="rules-modal-body">
          {error ? (
            <p className="rules-modal-error">规则加载失败：{error}</p>
          ) : content ? (
            <RulesDocument content={content} />
          ) : (
            <p className="rules-modal-loading">规则加载中...</p>
          )}
        </article>
      </div>
    </div>,
    document.body,
  );
}
