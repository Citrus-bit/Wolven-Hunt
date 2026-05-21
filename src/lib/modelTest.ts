import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  type ModelConfigUserInput,
} from './modelConfigs';

export type ModelTestStatus = 'idle' | 'testing' | 'pass' | 'fail';

export type ModelTestResult = {
  status: ModelTestStatus;
  errorMessage?: string;
};

export type ModelTestRequest = {
  baseUrl: string;
  apiKey: string;
  modelName: string;
  thinkingEnabled: boolean;
};

const MODEL_CONFIG_STORAGE_PREFIX = 'wolven' + '_hunt.lobby.model_config.';

function isCompleteConfig(
  config: Partial<ModelConfigUserInput>,
): config is ModelConfigRequestInput {
  return Boolean(config.baseUrl && config.apiKey && config.modelName);
}

type ModelConfigRequestInput = Pick<
  ModelConfigUserInput,
  'baseUrl' | 'apiKey' | 'modelName' | 'thinkingEnabled'
>;

type ChatCompletionRequestBody = {
  model: string;
  messages: { role: 'user'; content: string }[];
  max_tokens: number;
  enable_thinking?: true;
  thinking?: { type: 'enabled' };
  chat_template_kwargs?: {
    thinking: true;
    reasoning_effort: 'medium';
  };
  reasoning_effort?: 'medium';
};

export function buildThinkingPayload(
  modelName: string,
  enabled: boolean,
): Partial<ChatCompletionRequestBody> {
  if (!enabled) {
    return {};
  }

  const normalizedModelName = modelName.trim().toLowerCase();

  if (normalizedModelName.startsWith('qwen')) {
    return { enable_thinking: true };
  }

  if (
    normalizedModelName.startsWith('kimi') ||
    normalizedModelName.startsWith('mimo') ||
    normalizedModelName.startsWith('deepseek') ||
    normalizedModelName.startsWith('glm') ||
    normalizedModelName.startsWith('doubao')
  ) {
    return { thinking: { type: 'enabled' } };
  }

  if (normalizedModelName.startsWith('hy3')) {
    return {
      chat_template_kwargs: {
        thinking: true,
        reasoning_effort: 'medium',
      },
    };
  }

  if (normalizedModelName.startsWith('minimax')) {
    return { reasoning_effort: 'medium' };
  }

  return {};
}

function buildChatCompletionRequestBody(
  req: ModelTestRequest,
): ChatCompletionRequestBody {
  return {
    model: req.modelName,
    messages: [{ role: 'user', content: 'ping' }],
    max_tokens: 1,
    ...buildThinkingPayload(req.modelName, req.thinkingEnabled),
  };
}

export async function testModelConnection(
  req: ModelTestRequest,
  signal?: AbortSignal,
): Promise<ModelTestResult> {
  const url = req.baseUrl.replace(/\/+$/, '') + '/chat/completions';
  const controller = new AbortController();
  const abortFromSignal = () => controller.abort();
  const timeoutId = window.setTimeout(() => controller.abort(), 15000);

  signal?.addEventListener('abort', abortFromSignal, { once: true });

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${req.apiKey}`,
      },
      body: JSON.stringify(buildChatCompletionRequestBody(req)),
      signal: controller.signal,
    });

    if (!res.ok) {
      return { status: 'fail', errorMessage: `HTTP ${res.status}` };
    }

    const data: unknown = await res.json();
    if (typeof data !== 'object' || data === null) {
      return { status: 'fail', errorMessage: '非 JSON 响应' };
    }

    return { status: 'pass' };
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    return { status: 'fail', errorMessage: message.slice(0, 80) };
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener('abort', abortFromSignal);
  }
}

export function readModelConfig(slot: number): ModelTestRequest | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const defaultConfig = MODEL_CONFIG_DEFAULTS[slot] ?? EMPTY_USER_INPUT;

  try {
    const raw = window.localStorage.getItem(
      `${MODEL_CONFIG_STORAGE_PREFIX}${slot}`,
    );
    if (!raw) {
      return isCompleteConfig(defaultConfig) ? defaultConfig : null;
    }

    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return isCompleteConfig(defaultConfig) ? defaultConfig : null;
    }

    const input = parsed as Partial<ModelTestRequest>;
    const mergedConfig = {
      baseUrl:
        typeof input.baseUrl === 'string' ? input.baseUrl : defaultConfig.baseUrl,
      apiKey:
        typeof input.apiKey === 'string' ? input.apiKey : defaultConfig.apiKey,
      modelName:
        typeof input.modelName === 'string'
          ? input.modelName
          : defaultConfig.modelName,
      thinkingEnabled:
        typeof input.thinkingEnabled === 'boolean'
          ? input.thinkingEnabled
          : defaultConfig.thinkingEnabled,
    };

    if (!isCompleteConfig(mergedConfig)) {
      return null;
    }

    return mergedConfig;
  } catch {
    return isCompleteConfig(defaultConfig) ? defaultConfig : null;
  }
}
