import { useId, useMemo } from 'react';
import { useLocalStorage } from '../../../hooks/useLocalStorage';
import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  MODEL_SLOTS,
  type ModelConfigSlot,
  type ModelConfigUserInput,
} from '../../../lib/modelConfigs';

function createSerializer(defaultConfig: ModelConfigUserInput) {
  return {
    read: (raw: string): ModelConfigUserInput => {
      const parsed: unknown = JSON.parse(raw);

      if (typeof parsed !== 'object' || parsed === null) {
        return defaultConfig;
      }

      const input = parsed as Partial<ModelConfigUserInput>;

      return {
        baseUrl:
          typeof input.baseUrl === 'string'
            ? input.baseUrl
            : defaultConfig.baseUrl,
        apiKey:
          typeof input.apiKey === 'string' ? input.apiKey : defaultConfig.apiKey,
        modelName:
          typeof input.modelName === 'string'
            ? input.modelName
            : defaultConfig.modelName,
        thinkingEnabled:
          typeof input.thinkingEnabled === 'boolean'
            ? input.thinkingEnabled
            : defaultConfig.thinkingEnabled,
      };
    },
    write: (value: ModelConfigUserInput) => JSON.stringify(value),
  };
}

function ModelConfigRow({ slot }: { slot: ModelConfigSlot }) {
  const inputId = useId();
  const defaultConfig = MODEL_CONFIG_DEFAULTS[slot.slot] ?? EMPTY_USER_INPUT;
  const serializer = useMemo(
    () => createSerializer(defaultConfig),
    [defaultConfig],
  );
  const [config, setConfig] = useLocalStorage<ModelConfigUserInput>(
    `wolven_hunt.lobby.model_config.${slot.slot}`,
    defaultConfig,
    serializer,
    { debounceMs: 300 },
  );

  const update = (patch: Partial<ModelConfigUserInput>) => {
    setConfig({
      ...config,
      ...patch,
    });
  };

  return (
    <div className="lobby-model-row">
      <img src={slot.iconPath} alt={slot.nickname} className="lobby-model-icon" />
      <span className="lobby-model-nickname">{slot.nickname}</span>
      <label className="lobby-sr-only" htmlFor={`${inputId}-base-url`}>
        {slot.nickname} baseurl
      </label>
      <input
        id={`${inputId}-base-url`}
        className="lobby-model-input lobby-model-input--base"
        type="text"
        value={config.baseUrl}
        onChange={(event) => update({ baseUrl: event.target.value })}
        placeholder="baseurl"
        aria-label={`${slot.nickname} baseurl`}
        autoComplete="off"
      />
      <label className="lobby-sr-only" htmlFor={`${inputId}-api-key`}>
        {slot.nickname} apikey
      </label>
      <input
        id={`${inputId}-api-key`}
        className="lobby-model-input lobby-model-input--api"
        type="password"
        value={config.apiKey}
        onChange={(event) => update({ apiKey: event.target.value })}
        placeholder="apikey"
        aria-label={`${slot.nickname} apikey`}
        autoComplete="off"
      />
      <label className="lobby-sr-only" htmlFor={`${inputId}-model-name`}>
        {slot.nickname} model 名
      </label>
      <input
        id={`${inputId}-model-name`}
        className="lobby-model-input lobby-model-input--model"
        type="text"
        value={config.modelName}
        onChange={(event) => update({ modelName: event.target.value })}
        placeholder="model 名"
        aria-label={`${slot.nickname} model 名`}
        autoComplete="off"
      />
      <label className="lobby-model-thinking" htmlFor={`${inputId}-thinking`}>
        <input
          id={`${inputId}-thinking`}
          type="checkbox"
          checked={config.thinkingEnabled}
          onChange={(event) =>
            update({ thinkingEnabled: event.target.checked })
          }
        />
        <span className="lobby-model-thinking-label">思考模式</span>
        {config.thinkingEnabled && (
          <span className="lobby-model-thinking-hint">响应会更慢</span>
        )}
      </label>
    </div>
  );
}

export function ModelConfigList() {
  return (
    <div className="lobby-model-list">
      {MODEL_SLOTS.map((slot) => (
        <ModelConfigRow key={slot.slot} slot={slot} />
      ))}
    </div>
  );
}
