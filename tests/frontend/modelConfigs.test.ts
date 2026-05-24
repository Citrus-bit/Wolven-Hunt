import { describe, expect, it } from 'vitest';
import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
} from '../../src/lib/modelConfigs';

describe('modelConfigs', () => {
  it('defaults thinking mode off for every model slot', () => {
    expect(EMPTY_USER_INPUT.thinkingEnabled).toBe(false);
    expect(MODEL_CONFIG_DEFAULTS).toHaveLength(10);
    expect(
      MODEL_CONFIG_DEFAULTS.every((config) => config.thinkingEnabled === false),
    ).toBe(true);
  });
});
