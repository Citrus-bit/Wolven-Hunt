export type ModelConfigSlot = {
  slot: number;
  nickname: string;
  iconPath: string;
};

// API keys are intentionally not committed. Users can enter them in the
// settings UI; those overrides stay in browser localStorage.

export type ModelConfigUserInput = {
  baseUrl: string;
  apiKey: string;
  modelName: string;
  thinkingEnabled: boolean;
};

export const MODEL_SLOTS: readonly ModelConfigSlot[] = [
  {
    slot: 0,
    nickname: 'minimax老师',
    iconPath: '/assets/lobby/model_icon_minimax_laoshi.png',
  },
  {
    slot: 1,
    nickname: '万问',
    iconPath: '/assets/lobby/model_icon_wanwen.png',
  },
  {
    slot: 2,
    nickname: '光之明面',
    iconPath: '/assets/lobby/model_icon_guangzhimingmian.png',
  },
  {
    slot: 3,
    nickname: '大米',
    iconPath: '/assets/lobby/model_icon_dami.png',
  },
  {
    slot: 4,
    nickname: '学霸',
    iconPath: '/assets/lobby/model_icon_xueba.png',
  },
  {
    slot: 5,
    nickname: '小豆包儿',
    iconPath: '/assets/lobby/model_icon_xiaodoubao.png',
  },
  {
    slot: 6,
    nickname: '海瑟音',
    iconPath: '/assets/lobby/model_icon_haiseyin.png',
  },
  {
    slot: 7,
    nickname: 'Gemini',
    iconPath: '/assets/lobby/model_icon_gemini.png',
  },
  {
    slot: 8,
    nickname: '克劳德',
    iconPath: '/assets/lobby/model_icon_claude.png',
  },
  {
    slot: 9,
    nickname: 'GPT',
    iconPath: '/assets/lobby/model_icon_gpt.png',
  },
] as const;

export const EMPTY_USER_INPUT: ModelConfigUserInput = {
  baseUrl: '',
  apiKey: '',
  modelName: '',
  thinkingEnabled: false,
};

export const MODEL_CONFIG_DEFAULTS: readonly ModelConfigUserInput[] = [
  {
    baseUrl: 'https://api.minimaxi.com/v1',
    apiKey: '',
    modelName: 'MiniMax-M2.7-highspeed',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
    apiKey: '',
    modelName: 'qwen3.6-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: '',
    modelName: 'kimi-k2.5',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://token-plan-sgp.xiaomimimo.com/v1',
    apiKey: '',
    modelName: 'mimo-v2.5-pro',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: '',
    modelName: 'glm-4-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://ark.cn-beijing.volces.com/api/plan/v3',
    apiKey: '',
    modelName: 'doubao-seed-2.0-pro',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://api.deepseek.com',
    apiKey: '',
    modelName: 'deepseek-v4-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: '',
    modelName: 'gemini-3.5-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: '',
    modelName: 'claude-sonnet-4-6',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: '',
    modelName: 'gpt-5.4',
    thinkingEnabled: false,
  },
] as const;

export const VOLUME_DEFAULT = 80;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 100;
