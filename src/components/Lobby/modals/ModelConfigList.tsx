import { useId } from 'react';
import { useLocalStorage } from '../../../hooks/useLocalStorage';
import {
  EMPTY_USER_INPUT,
  MODEL_CONFIG_DEFAULTS,
  MODEL_SLOTS,
  type ModelConfigSlot,
  type ModelConfigUserInput,
} from '../../../lib/modelConfigs';

const serializer = {
  read: (raw: string): ModelConfigUserInput => {
    const parsed: unknown = JSON.parse(raw);

    if (typeof parsed !== 'object' || parsed === null) {
      return EMPTY_USER_INPUT;
    }

    const input = parsed as Partial<ModelConfigUserInput>;

    return {
      baseUrl: typeof input.baseUrl === 'string' ? input.baseUrl : '',
      apiKey: typeof input.apiKey === 'string' ? input.apiKey : '',
      modelName: typeof input.modelName === 'string' ? input.modelName : '',
    };
  },
  write: (value: ModelConfigUserInput) => JSON.stringify(value),
};

function ModelConfigRow({ slot }: { slot: ModelConfigSlot }) {
  const inputId = useId();
  const defaultConfig = MODEL_CONFIG_DEFAULTS[slot.slot] ?? EMPTY_USER_INPUT;
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
        type="text"
        value={config.modelName}
        onChange={(event) => update({ modelName: event.target.value })}
        placeholder="model 名"
        aria-label={`${slot.nickname} model 名`}
        autoComplete="off"
      />
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
