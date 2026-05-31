import type { AgentSpec } from './gameApi';
import { MODEL_SLOTS } from './modelConfigs';
import { readModelConfig, type ModelTestRequest } from './modelTest';

export const LIVE_LLM_TIMEOUT_SECONDS = 15;

export function buildAgentSpecs(
  assignments: (number | null)[],
  readConfig: (slot: number) => ModelTestRequest | null = readModelConfig,
  opts: { humanSeatIndex?: number | null; humanFallbackSlot?: number } = {},
): Record<number, AgentSpec> {
  const agents: Record<number, AgentSpec> = {};
  assignments.forEach((slotIndex, seatIndex) => {
    const effectiveSlotIndex =
      slotIndex ?? (opts.humanSeatIndex === seatIndex ? opts.humanFallbackSlot ?? 0 : null);
    if (effectiveSlotIndex === null) {
      throw new Error(`第 ${seatIndex + 1} 号席位尚未分配模型`);
    }
    const config = readConfig(effectiveSlotIndex);
    if (!config) {
      throw new Error(`${MODEL_SLOTS[effectiveSlotIndex]?.nickname ?? '模型'} 配置缺失`);
    }
    agents[seatIndex + 1] = {
      kind: 'llm',
      provider: 'litellm',
      model: config.modelName,
      base_url: config.baseUrl,
      api_key: config.apiKey,
      timeout_seconds: LIVE_LLM_TIMEOUT_SECONDS,
      thinking_enabled: config.thinkingEnabled,
    };
  });
  return agents;
}
