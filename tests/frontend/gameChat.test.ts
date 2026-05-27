import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  chatScrollBehavior,
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
