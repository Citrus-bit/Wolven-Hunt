export type ModelConfigSlot = {
  slot: number;
  nickname: string;
  iconPath: string;
};

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
    nickname: '阿元替身版',
    iconPath: '/assets/lobby/model_icon_ayuan_tishenban.png',
  },
] as const;

export const EMPTY_USER_INPUT: ModelConfigUserInput = {
  baseUrl: '',
  apiKey: '',
  modelName: '',
  thinkingEnabled: true,
};

export const MODEL_CONFIG_DEFAULTS: readonly ModelConfigUserInput[] = [
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-6seLrmgf7fZgAyt3vF8XtdzeZtZn6msQnBiqOvyOpdvQPsTP',
    modelName: 'MiniMax-M2.7',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-hxPnpVvndFQNyNr3AcgxintDYBAIgPDZcjrls9V0o9THsZnQ',
    modelName: 'qwen3.6-plus',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-oYxZIF9K6UWfnodFX8mWoSer32fzlnTlFU18uLAznCC6UWOQ',
    modelName: 'kimi-k2.5',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://api.xiaomimimo.com/v1',
    apiKey: 'sk-sek59eyxlq0v7b4g3riaejerfdlyryyzp6go04umhts1q009',
    modelName: 'mimo-v2.5-pro',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-3xVFT4xdHR3DYvBf7haR7A1Fb1ndJznxwrs1onoZ5JrywzRV',
    modelName: 'glm-5.1',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-pM36Wb0voJI7mhfvgQSf5eGfXPvisvXSmiN6fm0ZrW2hmKUZ',
    modelName: 'doubao-seed-2-0-pro-260215',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-fsxGOvfC9bNdRPopgB1ldIwWIBLn6oTQPUlYPHNvb1VQfxHC',
    modelName: 'deepseek-v4-pro',
    thinkingEnabled: true,
  },
  {
    baseUrl: 'https://api.lkeap.cloud.tencent.com/plan/v3',
    apiKey: 'sk-tp-BU7lFgCBrhOAAUBy2kQSY4lvMbMqPPXUNiQoyska14l8iVRC',
    modelName: 'hy3-preview',
    thinkingEnabled: true,
  },
] as const;

export const VOLUME_DEFAULT = 80;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 100;
