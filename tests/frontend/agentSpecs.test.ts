import { describe, expect, it } from 'vitest';
import {
  buildAgentSpecs,
  LIVE_LLM_TIMEOUT_SECONDS,
} from '../../src/lib/agentSpecs';
import type { ModelTestRequest } from '../../src/lib/modelTest';

describe('buildAgentSpecs', () => {
  it('adds the live LLM timeout to every real model spec', () => {
    const agents = buildAgentSpecs([0, 1], (slot) => modelConfig(slot));

    expect(agents).toEqual({
      1: {
        kind: 'llm',
        provider: 'litellm',
        model: 'model-0',
        base_url: 'https://example.test/0',
        api_key: 'key-0',
        timeout_seconds: LIVE_LLM_TIMEOUT_SECONDS,
        thinking_enabled: true,
      },
      2: {
        kind: 'llm',
        provider: 'litellm',
        model: 'model-1',
        base_url: 'https://example.test/1',
        api_key: 'key-1',
        timeout_seconds: LIVE_LLM_TIMEOUT_SECONDS,
        thinking_enabled: true,
      },
    });
  });

  it('rejects unassigned seats before creating a game', () => {
    expect(() => buildAgentSpecs([0, null], (slot) => modelConfig(slot))).toThrow(
      '第 2 号席位尚未分配模型',
    );
  });
});

function modelConfig(slot: number): ModelTestRequest {
  return {
    baseUrl: `https://example.test/${slot}`,
    apiKey: `key-${slot}`,
    modelName: `model-${slot}`,
    thinkingEnabled: true,
  };
}
