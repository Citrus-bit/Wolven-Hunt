import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GamePhaseHeader } from '../../src/components/Game/GamePhaseHeader';

describe('GamePhaseHeader', () => {
  it('renders the startup waiting message with a loading indicator', () => {
    const html = renderToStaticMarkup(
      <GamePhaseHeader
        phase={null}
        timings={null}
        startupPending={true}
        startupMessage="正在启动对局"
      />,
    );

    expect(html).toContain('正在启动对局');
    expect(html).toContain('已等待 0s');
    expect(html).toContain('game-phase-spinner');
    expect(html).not.toContain('class="game-phase-countdown">--</span>');
  });

  it('hides the startup waiting message after normal phase rendering resumes', () => {
    const html = renderToStaticMarkup(
      <GamePhaseHeader phase="NIGHT_START" timings={{ night_start_ms: 1000 }} />,
    );

    expect(html).toContain('夜幕降临');
    expect(html).not.toContain('正在启动对局');
    expect(html).not.toContain('game-phase-spinner');
  });
});
