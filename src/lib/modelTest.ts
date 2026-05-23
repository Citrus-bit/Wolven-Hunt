import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  type ModelConfigUserInput,
} from './modelConfigs';
import { testModelConnection as testModelConnectionViaApi } from './gameApi';

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

export function missingModelConfigResult(): ModelTestResult {
  return { status: 'fail', errorMessage: '配置缺失' };
}

export async function testModelConnection(
  req: ModelTestRequest,
  signal?: AbortSignal,
): Promise<ModelTestResult> {
  try {
    if (signal?.aborted) {
      return { status: 'fail', errorMessage: '已取消' };
    }
    const result = await testModelConnectionViaApi({
      provider: 'litellm',
      model: req.modelName,
      base_url: req.baseUrl,
      api_key: req.apiKey,
      timeout_seconds: 15,
      thinking_enabled: req.thinkingEnabled,
    }, signal);
    if (typeof result.ok !== 'boolean') {
      return {
        status: 'fail',
        errorMessage: '后端连通性测试接口不可用',
      };
    }
    return result.ok
      ? { status: 'pass' }
      : {
          status: 'fail',
          errorMessage: formatModelTestError(result.message ?? '模型测试失败'),
        };
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误';
    return {
      status: 'fail',
      errorMessage: isModelTestInterfaceError(message)
        ? '后端连通性测试接口不可用'
        : formatModelTestError(message),
    };
  }
}

function isModelTestInterfaceError(message: string) {
  return (
    /^HTTP \d+/.test(message) ||
    message.toLowerCase().includes('failed to fetch') ||
    message.toLowerCase().includes('fetch failed') ||
    message.toLowerCase().includes('networkerror')
  );
}

function formatModelTestError(message: string) {
  const normalized = message.trim() || '模型测试失败';
  return normalized.length > 120 ? `${normalized.slice(0, 117)}...` : normalized;
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
