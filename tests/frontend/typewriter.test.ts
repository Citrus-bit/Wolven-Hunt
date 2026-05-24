import { describe, expect, it } from 'vitest';
import {
  typewriterVisibleLength,
  typewriterVisibleText,
} from '../../src/lib/typewriter';

describe('typewriter helpers', () => {
  it('reveals text at the start, midpoint, and end of the animation', () => {
    const text = '1234567890';

    expect(
      typewriterVisibleText(text, { elapsedMs: 0, durationMs: 1000 }),
    ).toBe('');
    expect(
      typewriterVisibleText(text, { elapsedMs: 500, durationMs: 1000 }),
    ).toBe('12345');
    expect(
      typewriterVisibleText(text, { elapsedMs: 1000, durationMs: 1000 }),
    ).toBe(text);
  });

  it('handles empty, short, and long Chinese text without overflowing', () => {
    const longText = '我是预言家，昨晚查验的信息需要谨慎公开。'.repeat(12);

    expect(typewriterVisibleLength('', { elapsedMs: 500 })).toBe(0);
    expect(
      typewriterVisibleText('狼', { elapsedMs: 1, durationMs: 1000 }),
    ).toBe('狼');
    expect(
      typewriterVisibleText(longText, { elapsedMs: 2000, durationMs: 1000 }),
    ).toBe(longText);
  });

  it('returns full text when disabled or reduced motion is requested', () => {
    const text = '7号：我先关注公开发言';

    expect(typewriterVisibleText(text, { elapsedMs: 0, enabled: false })).toBe(text);
    expect(
      typewriterVisibleText(text, { elapsedMs: 0, reducedMotion: true }),
    ).toBe(text);
  });
});
