import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GameSeat } from '../../src/components/Game/GameSeat';

describe('GameSeat', () => {
  it('uses a numbered placeholder for old replay seats without presentation data', () => {
    const html = renderToStaticMarkup(
      <GameSeat
        seatIndex={0}
        side="left"
        assignment={null}
        showTestBadge={false}
        disabled={true}
        onClickSeat={() => undefined}
      />,
    );

    expect(html).toContain('game-seat-placeholder-avatar');
    expect(html).toContain('1号席位 1号');
    expect(html).not.toContain('lucide-plus');
  });
});
