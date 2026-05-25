import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  missingModelConfigResult,
  testModelConnection,
} from '../../src/lib/modelTest';

describe('modelTest', () => {
  afterEach(() => {
    vi.useRealTimers();
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
      timeout_seconds: 30,
      thinking_enabled: false,
    });
  });

  it('retries failed backend responses on the fixed schedule before passing', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'temporary' }))
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'still down' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, message: null }));
    vi.stubGlobal('fetch', fetchMock);

    const promise = testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'mimo-v2.5-pro',
      thinkingEnabled: true,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(1000);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await vi.advanceTimersByTimeAsync(3000);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    await expect(promise).resolves.toEqual({ status: 'pass' });
  });

  it('preserves the last backend failure message after all retries are exhausted', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'fail-1' }))
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'fail-2' }))
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'fail-3' }))
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'fail-4' }))
      .mockResolvedValueOnce(jsonResponse({ ok: false, message: 'final failure' }));
    vi.stubGlobal('fetch', fetchMock);

    const promise = testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'mimo-v2.5-pro',
      thinkingEnabled: true,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    for (const [index, delay] of [1000, 3000, 5000, 10000].entries()) {
      await vi.advanceTimersByTimeAsync(delay);
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(index + 2));
    }

    await expect(promise).resolves.toEqual({
      status: 'fail',
      errorMessage: 'final failure',
    });
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it('preserves backend failure messages for display when retries are disabled by success absence', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          ok: false,
          message: 'quota exhausted',
        }),
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const promise = testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'mimo-v2.5-pro',
      thinkingEnabled: true,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitForModelTestRetries();
    await expect(promise).resolves.toEqual({
      status: 'fail',
      errorMessage: 'quota exhausted',
    });
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it('uses a clear backend unavailable message for network failures', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchMock);

    vi.useFakeTimers();
    const promise = testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'glm-4.5-air',
      thinkingEnabled: true,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitForModelTestRetries();
    await expect(promise).resolves.toEqual({
      status: 'fail',
      errorMessage: '后端连通性测试接口不可用',
    });
  });

  it('uses a clear backend unavailable message for malformed responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
        new Response('not json', {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    vi.useFakeTimers();
    const promise = testModelConnection({
      baseUrl: 'https://example.test/v1',
      apiKey: 'secret',
      modelName: 'glm-4.5-air',
      thinkingEnabled: true,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitForModelTestRetries();
    await expect(promise).resolves.toEqual({
      status: 'fail',
      errorMessage: '后端连通性测试接口不可用',
    });
  });

  it('returns cancelled immediately and does not queue retries', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();
    controller.abort();

    await expect(
      testModelConnection(
        {
          baseUrl: 'https://example.test/v1',
          apiKey: 'secret',
          modelName: 'glm-4.5-air',
          thinkingEnabled: true,
        },
        controller.signal,
      ),
    ).resolves.toEqual({
      status: 'fail',
      errorMessage: '已取消',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps the shared missing config result text', () => {
    expect(missingModelConfigResult()).toEqual({
      status: 'fail',
      errorMessage: '配置缺失',
    });
  });
});

async function waitForModelTestRetries() {
  for (const delay of [1000, 3000, 5000, 10000]) {
    await vi.advanceTimersByTimeAsync(delay);
  }
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
