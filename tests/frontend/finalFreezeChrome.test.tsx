import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  FinalFreezeChrome,
  ReviewReportDrawer,
} from '../../src/components/Game/FinalFreezeChrome';
import type { GameEvent, ReviewReport } from '../../src/lib/gameApi';

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
    expect(html).toContain('AI一键生成复盘报告');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('1号取得关键胜利');
    expect(html).not.toContain('raw');
    expect(html).not.toContain('pre');
  });

  it('renders the structured AI report drawer with leaderboard and player scores', () => {
    const html = renderToStaticMarkup(<ReviewReportDrawer report={reviewReport()} />);

    expect(html).toContain('AI复盘报告');
    expect(html).toContain('结构化报告');
    expect(html).toContain('Leaderboard');
    expect(html).toContain('玩家打分与建议');
    expect(html).toContain('关键决策复盘');
    expect(html).toContain('反事实推演');
    expect(html).toContain('发言');
    expect(html).toContain('投票');
    expect(html).toContain('技能');
    expect(html).toContain('下一局建议');
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

function reviewReport(): ReviewReport {
  return {
    schema_version: '1.0',
    game_id: 'game-1',
    generated_at: '2026-01-01T00:00:00Z',
    summary: {
      winner: 'good',
      verdict: '好人胜利',
      turning_points: ['第2天票型收束'],
      overall_assessment: '好人阵营通过公开发言和票型建立优势。',
    },
    leaderboard: [
      {
        rank: 1,
        seat: 1,
        nickname: 'GPT',
        role: 'seer',
        camp: 'good',
        overall_score: 92,
        reason: '查验链和发言节奏稳定。',
      },
    ],
    players: [
      {
        seat: 1,
        nickname: 'GPT',
        role: 'seer',
        camp: 'good',
        alive: true,
        speech_score: 90,
        vote_score: 88,
        skill_score: 95,
        overall_score: 92,
        strengths: ['发言清晰'],
        mistakes: ['中期可更早归票'],
        suggestions: ['下一局建议继续把查验链和票型绑定。'],
      },
    ],
    key_decisions: [
      {
        day: 2,
        phase: 'DAY_VOTE',
        seq: 42,
        title: '关键放逐',
        analysis: '好人阵营集中票型。',
        impact: '压缩狼人操作空间。',
      },
    ],
    counterfactuals: [
      {
        premise: '如果第2天没有集中归票',
        likely_outcome: '狼人可能拖入下一夜。',
        lesson: '优势轮次需要明确执行。',
      },
    ],
  };
}
