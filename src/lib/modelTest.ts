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
};

const MODEL_CONFIG_STORAGE_PREFIX = 'wolven' + '_hunt.lobby.model_config.';

function isCompleteConfig(
  config: Partial<ModelConfigUserInput>,
): config is ModelConfigRequestInput {
  return Boolean(config.baseUrl && config.apiKey && config.modelName);
}

type ModelConfigRequestInput = Pick<
  ModelConfigUserInput,
  'baseUrl' | 'apiKey' | 'modelName'
>;

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
      body: JSON.stringify({
        model: req.modelName,
        messages: [{ role: 'user', content: 'ping' }],
        max_tokens: 1,
      }),
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
    };

    if (!isCompleteConfig(mergedConfig)) {
      return null;
    }

    return mergedConfig;
  } catch {
    return isCompleteConfig(defaultConfig) ? defaultConfig : null;
  }
}
