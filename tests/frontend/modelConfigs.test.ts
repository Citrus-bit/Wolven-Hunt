import { describe, expect, it } from 'vitest';
import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  MODEL_SLOTS,
} from '../../src/lib/modelConfigs';

describe('modelConfigs', () => {
  it('defaults thinking mode off for every model slot', () => {
    expect(EMPTY_USER_INPUT.thinkingEnabled).toBe(false);
    expect(MODEL_CONFIG_DEFAULTS).toHaveLength(10);
    expect(
      MODEL_CONFIG_DEFAULTS.every((config) => config.thinkingEnabled === false),
    ).toBe(true);
  });

  it('uses qwen3.6-flash for the Qwen model slot', () => {
    const slot = MODEL_SLOTS.find((candidate) => candidate.nickname === '万问');
    expect(slot).toBeDefined();
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.modelName).toBe(
      'qwen3.6-flash',
    );
  });

  it('uses glm-4-flash for the Zhipu model slot', () => {
    const slot = MODEL_SLOTS.find((candidate) => candidate.nickname === '学霸');
    expect(slot).toBeDefined();
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.modelName).toBe('glm-4-flash');
  });

  it('uses the Ark Doubao endpoint for the Doubao model slot', () => {
    const slot = MODEL_SLOTS.find((candidate) => candidate.nickname === '小豆包儿');
    expect(slot).toBeDefined();
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.baseUrl).toBe(
      'https://ark.cn-beijing.volces.com/api/plan/v3',
    );
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.modelName).toBe(
      'doubao-seed-2.0-pro',
    );
  });

  it('uses deepseek-v4-flash for the DeepSeek model slot', () => {
    const slot = MODEL_SLOTS.find(
      (candidate) => candidate.nickname === '海瑟音',
    );
    expect(slot).toBeDefined();
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.modelName).toBe(
      'deepseek-v4-flash',
    );
  });

  it('uses gemini-3-flash-preview for the Gemini model slot', () => {
    const slot = MODEL_SLOTS.find((candidate) => candidate.nickname === 'Gemini');
    expect(slot).toBeDefined();
    expect(MODEL_CONFIG_DEFAULTS[slot?.slot ?? -1]?.modelName).toBe(
      'gemini-3-flash-preview',
    );
  });
});
