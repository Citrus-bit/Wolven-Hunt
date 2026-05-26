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
    expect(html).toContain('生成复盘报告');
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('1号取得关键胜利');
    expect(html).not.toContain('raw');
    expect(html).not.toContain('pre');
  });

  it('renders the structured AI report drawer with leaderboard and player scores', () => {
    const html = renderToStaticMarkup(<ReviewReportDrawer report={reviewReport()} />);

    expect(html).toContain('复盘报告');
    expect(html).toContain('结构化报告');
    expect(html).toContain('真实AI生成');
    expect(html).toContain('Leaderboard / 排行榜');
    expect(html).toContain('玩家打分与建议');
    expect(html).toContain('关键决策复盘');
    expect(html).toContain('反事实推演');
    expect(html).toContain('发言质量');
    expect(html).toContain('票型执行');
    expect(html).toContain('查验价值');
    expect(html).toContain('平民职责');
    expect(html).toContain('review-radar-value');
    expect(html).toContain('公开证据');
    expect(html).toContain('下一局建议');
    expect(html).not.toContain('技能');
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
    schema_version: '1.1',
    game_id: 'game-1',
    generated_at: '2026-01-01T00:00:00Z',
    generation_mode: 'real_ai',
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
        scores: [
          { key: 'speech', label: '发言质量', value: 90 },
          { key: 'reasoning', label: '推理逻辑', value: 91 },
          { key: 'voting', label: '票型执行', value: 88 },
          { key: 'camp_contribution', label: '阵营贡献', value: 93 },
          { key: 'information_control', label: '信息控制', value: 87 },
          { key: 'role_duty', label: '查验价值', value: 95 },
        ],
        overall_score: 92,
        evaluation: '1号把查验链和公开票型绑定，形成了稳定推进。',
        evidence: ['第2天发言引用查验链。', '第2天投票集中到狼坑。'],
        strengths: ['发言清晰'],
        mistakes: ['中期可更早归票'],
        suggestions: ['下一局建议继续把查验链和票型绑定。'],
      },
      {
        seat: 2,
        nickname: '村民',
        role: 'villager',
        camp: 'good',
        alive: false,
        scores: [
          { key: 'speech', label: '发言质量', value: 70 },
          { key: 'reasoning', label: '推理逻辑', value: 68 },
          { key: 'voting', label: '票型执行', value: 72 },
          { key: 'camp_contribution', label: '阵营贡献', value: 74 },
          { key: 'information_control', label: '信息控制', value: 65 },
          { key: 'role_duty', label: '平民职责', value: 76 },
        ],
        overall_score: 71,
        evaluation: '2号按平民职责留下了站边和票型信息。',
        evidence: ['第1天参与公开投票。'],
        strengths: ['站边清楚'],
        mistakes: ['推理链还可以更完整'],
        suggestions: ['下一局建议把怀疑理由说得更具体。'],
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
