import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FinalFreezeChrome } from '../../src/components/Game/FinalFreezeChrome';
import type { GameEvent } from '../../src/lib/gameApi';

describe('FinalFreezeChrome', () => {
  it('does not render before role reveal is available', () => {
    const html = renderToStaticMarkup(
      <FinalFreezeChrome
        gameId="game-1"
        events={[event(1, 'game_end', {})]}
        assignments={[]}
        seatPresentation={{}}
        isReplay={false}
        onExitGame={() => undefined}
      />,
    );

    expect(html).toBe('');
  });

  it('renders an unobtrusive frozen-game chrome with the drawer closed by default', () => {
    const html = renderToStaticMarkup(
      <FinalFreezeChrome
        gameId="game-1"
        events={[
          event(1, 'role_reveal', {
            winner: 'wolf',
            seats: [
              { seat: 1, role: 'wolf', alive: true },
              { seat: 2, role: 'villager', alive: false },
            ],
            highlights: [{ seq: 9, summary: '1号取得关键胜利' }],
          }),
        ]}
        assignments={[]}
        seatPresentation={{
          1: {
            nickname: 'GPT',
            icon_path: '/assets/lobby/model_icon_gpt.png',
          },
        }}
        isReplay={true}
        onExitGame={() => undefined}
      />,
    );

    expect(html).toContain('狼人胜利');
    expect(html).toContain('终局定格');
    expect(html).toContain('返回大厅');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('1号取得关键胜利');
    expect(html).not.toContain('raw');
    expect(html).not.toContain('pre');
  });
});

function event(
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): GameEvent {
  return {
    seq,
    day: 1,
    phase: 'GAME_END',
    type,
    actor: null,
    payload,
  };
}
