import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  GameBottomActions,
  type ModelTestTimingRow,
} from '../../src/components/Game/GameBottomActions';

describe('GameBottomActions', () => {
  it('renders model test timings from slowest to fastest and marks the slowest row', () => {
    const html = renderToStaticMarkup(
      bottomActions({
        testTimings: [
          timing({ seat: 1, nickname: '万问', modelName: 'qwen3.6-flash', durationMs: 1240 }),
          timing({
            seat: 2,
            nickname: '小豆包儿',
            modelName: 'doubao-seed-2.0-pro',
            status: 'fail',
            durationMs: 8650,
          }),
          timing({ seat: 3, nickname: 'GPT', modelName: 'gpt-5.4', durationMs: 3320 }),
        ],
      }),
    );

    expect(html).toContain('aria-label="模型连通性耗时表"');
    expect(html.indexOf('小豆包儿')).toBeLessThan(html.indexOf('GPT'));
    expect(html.indexOf('GPT')).toBeLessThan(html.indexOf('万问'));
    expect(html).toContain('8.65s');
    expect(html).toContain('失败');
    expect(html).toContain('最慢');
    expect(html.indexOf('最慢')).toBeLessThan(html.indexOf('GPT'));
  });

  it('shows pass and fail timings without rendering an empty table by default', () => {
    const emptyHtml = renderToStaticMarkup(bottomActions());
    expect(emptyHtml).not.toContain('模型连通性耗时表');

    const html = renderToStaticMarkup(
      bottomActions({
        testTimings: [
          timing({ status: 'pass', durationMs: 820 }),
          timing({ seat: 2, status: 'fail', durationMs: 510 }),
        ],
      }),
    );

    expect(html).toContain('通过');
    expect(html).toContain('失败');
    expect(html).toContain('0.82s');
    expect(html).toContain('0.51s');
  });

  it('can show the service connection label while startup is in progress', () => {
    const html = renderToStaticMarkup(
      bottomActions({
        isStartingGame: true,
        startingLabel: '正在连接本地服务',
      }),
    );

    expect(html).toContain('正在连接本地服务');
    expect(html).not.toContain('正在创建对局');
  });
});

function bottomActions(overrides: Partial<Parameters<typeof GameBottomActions>[0]> = {}) {
  return (
    <GameBottomActions
      allSeatsAssigned={true}
      allTestsPassed={false}
      canStartWithWarnings={true}
      isTesting={false}
      onClickTest={() => undefined}
      onClickEnterNight={() => undefined}
      {...overrides}
    />
  );
}

function timing(overrides: Partial<ModelTestTimingRow> = {}): ModelTestTimingRow {
  const durationMs = overrides.durationMs ?? 1000;
  const startedOffsetMs = overrides.startedOffsetMs ?? 0;

  return {
    seat: 1,
    nickname: '模型',
    modelName: 'model-test',
    status: 'pass',
    durationMs,
    startedOffsetMs,
    finishedOffsetMs: overrides.finishedOffsetMs ?? startedOffsetMs + durationMs,
    ...overrides,
  };
}
