import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  missingModelConfigResult,
  testModelConnection,
} from '../../src/lib/modelTest';

describe('modelTest', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends thinkingEnabled to the backend model test endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        ok: true,
        message: null,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'qwen3.6-flash',
      thinkingEnabled: false,
    });

    expect(result).toEqual({ status: 'pass' });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      provider: 'litellm',
      model: 'qwen3.6-flash',
      base_url: 'https://example.test/v1',
      api_key: 'secret',
      timeout_seconds: 15,
      thinking_enabled: false,
    });
  });

  it('preserves backend failure messages for display', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          ok: false,
          message: 'quota exhausted',
        }),
      ),
    );

    await expect(
      testModelConnection({
        baseUrl: 'https://example.test/v1',
        apiKey: 'secret',
        modelName: 'mimo-v2.5-pro',
        thinkingEnabled: true,
      }),
    ).resolves.toEqual({
      status: 'fail',
      errorMessage: 'quota exhausted',
    });
  });

  it('uses a clear backend unavailable message for network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(
      testModelConnection({
        baseUrl: 'https://example.test/v1',
        apiKey: 'secret',
        modelName: 'glm-4.5-air',
        thinkingEnabled: true,
      }),
    ).resolves.toEqual({
      status: 'fail',
      errorMessage: '后端连通性测试接口不可用',
    });
  });

  it('uses a clear backend unavailable message for malformed responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('not json', {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        }),
      ),
    );

    await expect(
      testModelConnection({
        baseUrl: 'https://example.test/v1',
        apiKey: 'secret',
        modelName: 'glm-4.5-air',
        thinkingEnabled: true,
      }),
    ).resolves.toEqual({
      status: 'fail',
      errorMessage: '后端连通性测试接口不可用',
    });
  });

  it('keeps the shared missing config result text', () => {
    expect(missingModelConfigResult()).toEqual({
      status: 'fail',
      errorMessage: '配置缺失',
    });
  });
});

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
