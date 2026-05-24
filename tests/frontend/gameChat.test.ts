import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  chatScrollBehavior,
  scrollChatBodyToBottom,
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

function mockChatBody(scrollHeight: number) {
  return {
    scrollHeight,
    scrollTo: vi.fn(),
  } satisfies Pick<HTMLDivElement, 'scrollHeight' | 'scrollTo'>;
}
