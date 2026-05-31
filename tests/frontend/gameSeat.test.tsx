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

  it('marks seats that have thinking mode enabled', () => {
    const html = renderToStaticMarkup(
      <GameSeat
        seatIndex={4}
        side="left"
        assignment={0}
        thinkingEnabled={true}
        onClickSeat={() => undefined}
      />,
    );

    expect(html).toContain('game-seat-thinking-badge');
    expect(html).toContain('思考模式开启，响应更慢');
  });

  it('renders the human role picker on a selected human setup seat', () => {
    const html = renderToStaticMarkup(
      <GameSeat
        seatIndex={1}
        side="left"
        assignment={null}
        isHuman={true}
        pickRoleEnabled={true}
        humanRole="witch"
        presentation={{ nickname: '你自己', icon_path: '/assets/lobby/human_player.png' }}
        onClickSeat={() => undefined}
      />,
    );

    expect(html).toContain('game-seat-role-picker');
    expect(html).toContain('选择你的角色，当前女巫');
    expect(html).toContain('game-seat-role-picker-button');
    expect(html).toContain('你自己');
  });

  it('renders the witch split action overlay with disabled halves', () => {
    const html = renderToStaticMarkup(
      <GameSeat
        seatIndex={2}
        side="left"
        assignment={0}
        selectedAsTarget={true}
        witchSplit={{
          active: true,
          canSave: false,
          canPoison: true,
          onSave: () => undefined,
          onPoison: () => undefined,
        }}
        onClickSeat={() => undefined}
      />,
    );

    expect(html).toContain('game-seat-witch-split');
    expect(html).toContain('game-seat-witch-half--save');
    expect(html).toContain('disabled=""');
    expect(html).toContain('game-seat-witch-half--poison');
  });
});
