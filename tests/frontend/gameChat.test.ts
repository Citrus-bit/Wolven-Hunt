import {
  Children,
  createElement,
  isValidElement,
  type ComponentProps,
  type ReactElement,
  type ReactNode,
} from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  chatScrollBehavior,
  gameChatClassName,
  GeneralChatHeader,
  scrollChatBodyToBottom,
  shouldShowWolfNightDivider,
  wolfNightLabel,
} from '../../src/components/Game/GameChat';

describe('GameChat auto-scroll', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('scrolls a chat body to the newest row when enabled', () => {
    const element = mockChatBody(420);

    scrollChatBodyToBottom(element, true);

    expect(element.scrollTo).toHaveBeenCalledWith({
      top: 420,
      behavior: 'smooth',
    });
  });

  it('does not scroll when auto-scroll is disabled', () => {
    const element = mockChatBody(420);

    scrollChatBodyToBottom(element, false);

    expect(element.scrollTo).not.toHaveBeenCalled();
  });

  it('respects the auto-scroll setting during typewriter frames', () => {
    const element = mockChatBody(520);

    scrollChatBodyToBottom(element, true);
    scrollChatBodyToBottom(element, false);

    expect(element.scrollTo).toHaveBeenCalledTimes(1);
    expect(element.scrollTo).toHaveBeenCalledWith({
      top: 520,
      behavior: 'smooth',
    });
  });

  it('uses instant scrolling when reduced motion is requested', () => {
    vi.stubGlobal('window', {
      matchMedia: vi.fn(() => ({ matches: true })),
    });
    const element = mockChatBody(320);

    scrollChatBodyToBottom(element, true);

    expect(chatScrollBehavior()).toBe('auto');
    expect(element.scrollTo).toHaveBeenCalledWith({
      top: 320,
      behavior: 'auto',
    });
  });
});

describe('GameChat general panel expansion', () => {
  it('renders the default collapsed state with an accessible expand button', () => {
    const html = renderToStaticMarkup(
      createElement(GeneralChatHeader, {
        streamStatus: 'open',
        generalExpanded: false,
        onToggleGeneralExpanded: () => undefined,
      }),
    );

    expect(gameChatClassName(false)).toBe('game-chat');
    expect(html).toContain('aria-label="展开通用聊天框"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="game-chat-wolf-panel"');
    expect(html).toContain('已连接');
  });

  it('exposes the expanded state and toggle callback contract', () => {
    const onToggleGeneralExpanded = vi.fn();
    const expandedHeader = GeneralChatHeader({
      streamStatus: 'open',
      generalExpanded: true,
      onToggleGeneralExpanded,
    });
    const button = findByAriaLabel(expandedHeader, '还原通用聊天框');
    const html = renderToStaticMarkup(expandedHeader);

    expect(gameChatClassName(true)).toBe('game-chat game-chat--general-expanded');
    expect(html).toContain('aria-label="还原通用聊天框"');
    expect(html).toContain('aria-expanded="true"');
    expect(button).not.toBeNull();
    (button?.props as { onClick?: () => void }).onClick?.();
    expect(onToggleGeneralExpanded).toHaveBeenCalledTimes(1);
  });

  it('returns to the default state when rendered collapsed again', () => {
    const html = renderToStaticMarkup(
      createElement(GeneralChatHeader, {
        streamStatus: 'open',
        generalExpanded: false,
        onToggleGeneralExpanded: () => undefined,
      }),
    );

    expect(gameChatClassName(false)).toBe('game-chat');
    expect(html).toContain('aria-label="展开通用聊天框"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('还原通用聊天框');
  });
});

describe('GameChat wolf night divider', () => {
  it('shows a divider for the first wolf chat message', () => {
    const events = [{ day: 1 }];

    expect(shouldShowWolfNightDivider(events, 0)).toBe(true);
  });

  it('does not repeat the divider within the same night', () => {
    const events = [{ day: 1 }, { day: 1 }, { day: 1 }];

    expect(shouldShowWolfNightDivider(events, 1)).toBe(false);
    expect(shouldShowWolfNightDivider(events, 2)).toBe(false);
  });

  it('shows a divider when wolf chat crosses into a new night', () => {
    const events = [{ day: 1 }, { day: 1 }, { day: 2 }];

    expect(shouldShowWolfNightDivider(events, 2)).toBe(true);
  });

  it('falls back for invalid night values', () => {
    expect(wolfNightLabel(undefined)).toBe('夜晚');
    expect(wolfNightLabel(0)).toBe('夜晚');
    expect(wolfNightLabel(1.5)).toBe('夜晚');
  });

  it('formats valid night values', () => {
    expect(wolfNightLabel(1)).toBe('第1晚');
    expect(wolfNightLabel(12)).toBe('第12晚');
  });
});

function mockChatBody(scrollHeight: number) {
  return {
    scrollHeight,
    scrollTo: vi.fn(),
  } satisfies Pick<HTMLDivElement, 'scrollHeight' | 'scrollTo'>;
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
