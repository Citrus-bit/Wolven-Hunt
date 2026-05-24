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

  it('renders spectator seat effect icons with their assets', () => {
    const html = renderToStaticMarkup(
      <GameSeat
        seatIndex={2}
        side="left"
        assignment={null}
        showTestBadge={false}
        disabled={true}
        effects={{
          guardShield: true,
          guardShieldSeq: 10,
          wolfAttack: true,
          wolfAttackSeq: 11,
          seerVisionSeq: 12,
          outBadge: true,
          outBadgeSeq: 13,
        }}
        onClickSeat={() => undefined}
      />,
    );

    expect(html).toContain('game-seat-effect--guard');
    expect(html).toContain('/assets/game/effects/guard_shield.png');
    expect(html).toContain('game-seat-effect--wolf');
    expect(html).toContain('/assets/game/effects/wolf_attack.png');
    expect(html).toContain('game-seat-effect--seer');
    expect(html).toContain('/assets/game/effects/seer_vision.png');
    expect(html).toContain('game-seat-effect--out');
    expect(html).toContain('/assets/game/effects/out_badge.png');
  });
});
