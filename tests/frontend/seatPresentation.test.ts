import { describe, expect, it } from 'vitest';
import {
  buildSeatPresentation,
  resolveSeatDisplay,
} from '../../src/lib/seatPresentation';

describe('seatPresentation', () => {
  it('builds spectator-safe seat presentation from assignments', () => {
    const presentation = buildSeatPresentation([9, null, 0]);

    expect(presentation).toEqual({
      1: {
        nickname: 'GPT',
        icon_path: '/assets/lobby/model_icon_gpt.png',
      },
      3: {
        nickname: 'minimax老师',
        icon_path: '/assets/lobby/model_icon_minimax_laoshi.png',
      },
    });
    expect(JSON.stringify(presentation)).not.toContain('api');
    expect(JSON.stringify(presentation)).not.toContain('modelName');
  });

  it('prefers live assignments and falls back to replay presentation', () => {
    expect(
      resolveSeatDisplay(2, [null, null], {
        2: {
          nickname: '历史席位',
          icon_path: '/assets/lobby/model_icon_gpt.png',
        },
      }),
    ).toEqual({
      nickname: '历史席位',
      iconPath: '/assets/lobby/model_icon_gpt.png',
    });

    expect(
      resolveSeatDisplay(1, [7], {
        1: {
          nickname: '旧展示',
          icon_path: '/assets/lobby/model_icon_gpt.png',
        },
      }),
    ).toEqual({
      nickname: 'Gemini',
      iconPath: '/assets/lobby/model_icon_gemini.png',
    });
  });
});
