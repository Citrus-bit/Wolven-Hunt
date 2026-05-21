export type ModelConfigSlot = {
  slot: number;
  nickname: string;
  iconPath: string;
};

export type ModelConfigUserInput = {
  baseUrl: string;
  apiKey: string;
  modelName: string;
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
};

export const VOLUME_DEFAULT = 80;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 100;
