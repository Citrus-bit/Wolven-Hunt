export type ModelConfigSlot = {
  slot: number;
  nickname: string;
  iconPath: string;
};

// NOTE: The default apiKey values are author-funded rotating keys for the
// clone-and-play experience. Users can override them in the settings UI; those
// overrides stay in browser localStorage and take precedence over these values.

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
    apiKey: 'sk-cp-J9LpYlhs5Q8issU-lrXNRA_hxvpTptheFq7h75UQYVHXMwgkcM1Vo9XNk2CQ5EWerz5cyN4OqKZQDQ7lOag-a6kwbYDS77LP5fDD3qt1UcrdDsDwAhk5IlQ',
    modelName: 'MiniMax-M2.7-highspeed',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
    apiKey: 'sk-sp-D.HDXRM.WBYB.MEUCIQDsTRWgINcmA5E+3jY2ESrb/zPm3LwWcbPBQ6HxCxq6lAIgLWMi8mhr+FFH3q6fQxCqWSp4UUQEOLWLK1zHgnCQKj0=',
    modelName: 'qwen3.6-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-oYxZIF9K6UWfnodFX8mWoSer32fzlnTlFU18uLAznCC6UWOQ',
    modelName: 'kimi-k2.5',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://token-plan-sgp.xiaomimimo.com/v1',
    apiKey: 'tp-snbqlbrzy2c08jcyumrk4bs166tzbl02u5focufi7kqry1g6',
    modelName: 'mimo-v2.5-pro',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-3xVFT4xdHR3DYvBf7haR7A1Fb1ndJznxwrs1onoZ5JrywzRV',
    modelName: 'glm-4.5-air',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-pM36Wb0voJI7mhfvgQSf5eGfXPvisvXSmiN6fm0ZrW2hmKUZ',
    modelName: 'doubao-seed-2-0-pro-260215',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://api.deepseek.com',
    apiKey: 'sk-303313d10b7149bf831b7909bf70ad4f',
    modelName: 'deepseek-v4-flash',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-rp77BMMBfwtVUhSdRFEpjBf7OHXPFzodJvO0vQLFwKabnSDa',
    modelName: 'gemini-3.1-pro-preview',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-iXCFTRD3WI7v1xTc6zwPOSqA9uQMDq0tevGh7J2P1QjvoJoz',
    modelName: 'claude-sonnet-4-6',
    thinkingEnabled: false,
  },
  {
    baseUrl: 'https://yunwu.ai/v1',
    apiKey: 'sk-E6zcCAknXsLSLTL51m74vwDyn09cBnVYTx7X0xmXyuOdojZM',
    modelName: 'gpt-5.4',
    thinkingEnabled: false,
  },
] as const;

export const VOLUME_DEFAULT = 80;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 100;
