import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { VoteHistogram } from '../../src/components/Game/VoteHistogram';

describe('VoteHistogram', () => {
  it('renders abstentions after seat targets without treating them as seats', () => {
    const html = renderToStaticMarkup(
      <VoteHistogram counts={{ '2': 3, '7': 1 }} abstainCount={2} />,
    );

    expect(html).toContain('2号');
    expect(html).toContain('7号');
    expect(html).toContain('弃票');
    expect(html).toContain('2票');
    expect(html.indexOf('7号')).toBeLessThan(html.indexOf('弃票'));
  });
});
