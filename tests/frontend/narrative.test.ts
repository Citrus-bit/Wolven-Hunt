import { describe, expect, it } from 'vitest';
import cases from '../fixtures/narrative_cases.json';
import type { GameEvent } from '../../src/lib/gameApi';
import { toNarrative } from '../../src/lib/narrative';

describe('toNarrative', () => {
  it('matches backend narrative fixtures', () => {
    for (const testCase of cases) {
      expect(toNarrative(testCase.event as GameEvent)).toEqual(testCase.expected);
    }
  });
});
