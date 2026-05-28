import {
  Children,
  isValidElement,
  type ComponentProps,
  type ReactElement,
  type ReactNode,
} from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { GameTopBar } from '../../src/components/Game/GameTopBar';

describe('GameTopBar', () => {
  it('renders an auto-scroll button instead of the pacing selector', () => {
    const html = renderToStaticMarkup(topBar({ autoScrollEnabled: true }));

    expect(html).toContain('自动滚动');
    expect(html).toContain('aria-label="关闭自动滚动"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('game-top-btn--text');
    expect(html).not.toContain('节奏');
    expect(html).not.toContain('<select');
    expect(html).not.toContain('lucide-arrow-down-to-line');
  });

  it('updates the auto-scroll button label when disabled', () => {
    const html = renderToStaticMarkup(topBar({ autoScrollEnabled: false }));

    expect(html).toContain('aria-label="开启自动滚动"');
    expect(html).toContain('aria-pressed="false"');
  });

  it('calls the auto-scroll toggle handler when the button is clicked', () => {
    const onToggleAutoScroll = vi.fn();
    const button = findByAriaLabel(
      GameTopBar({
        ...defaultProps(),
        autoScrollEnabled: true,
        onToggleAutoScroll,
      }),
      '关闭自动滚动',
    );

    expect(button).not.toBeNull();
    (button?.props as { onClick?: () => void }).onClick?.();
    expect(onToggleAutoScroll).toHaveBeenCalledTimes(1);
  });

  it('renders transient reconnects as recovery instead of a hard disconnect', () => {
    const html = renderToStaticMarkup(
      topBar({ streamStatus: 'connecting', reconnectAttempts: 3 }),
    );

    expect(html).toContain('正在恢复事件流 3/4');
  });

  it('renders a failed connection message after fixed retries are exhausted', () => {
    const html = renderToStaticMarkup(
      topBar({ streamStatus: 'error', reconnectAttempts: 5 }),
    );

    expect(html).toContain('连接失败，请检查后端服务或刷新页面');
  });
});

function topBar(overrides: Partial<ComponentProps<typeof GameTopBar>> = {}) {
  return <GameTopBar {...defaultProps()} {...overrides} />;
}

function defaultProps(): ComponentProps<typeof GameTopBar> {
  return {
    onClickRules: () => undefined,
    onClickExit: () => undefined,
    streamStatus: 'idle',
    reconnectAttempts: 0,
    autoScrollEnabled: true,
    gameAudioMuted: false,
    gameAudioError: null,
    onToggleAutoScroll: () => undefined,
    onToggleGameAudio: () => undefined,
  };
}

function findByAriaLabel(
  node: ReactNode,
  label: string,
): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) {
    return null;
  }
  const element = node as ReactElement<Record<string, unknown>>;
  if (element.props['aria-label'] === label) {
    return element;
  }
  for (const child of Children.toArray(element.props.children as ReactNode)) {
    const match = findByAriaLabel(child, label);
    if (match) {
      return match;
    }
  }
  return null;
}
