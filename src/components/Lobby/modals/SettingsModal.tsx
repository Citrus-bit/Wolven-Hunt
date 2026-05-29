import { LobbyModal } from '../LobbyModal';
import { ModelConfigList } from './ModelConfigList';
import { VolumeSlider } from './VolumeSlider';
import { useLocalStorage } from '../../../hooks/useLocalStorage';
import {
  PROMPT_EVOLUTION_STORAGE_KEY,
  PROMPT_EVOLUTION_WARNING,
  booleanLocalStorageSerializer,
} from '../../../lib/evolutionSettings';

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
};

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [evolutionEnabled, setEvolutionEnabled] = useLocalStorage<boolean>(
    PROMPT_EVOLUTION_STORAGE_KEY,
    false,
    booleanLocalStorageSerializer,
  );

  return (
    <LobbyModal open={open} onClose={onClose} title="系统设置" variant="settings">
      <section className="lobby-settings-volume" aria-labelledby="lobby-volume-title">
        <h3 id="lobby-volume-title">音量</h3>
        <VolumeSlider />
      </section>
      <section className="lobby-settings-evolution" aria-labelledby="lobby-evolution-title">
        <h3 id="lobby-evolution-title">提示词自进化</h3>
        <label className="lobby-evolution-toggle">
          <input
            type="checkbox"
            checked={evolutionEnabled}
            onChange={(event) => setEvolutionEnabled(event.target.checked)}
          />
          <span className="lobby-evolution-switch" aria-hidden="true" />
          <span className="lobby-evolution-label">开启自进化系统</span>
        </label>
        <p className="lobby-evolution-hint">{PROMPT_EVOLUTION_WARNING}</p>
      </section>
      <section className="lobby-settings-models" aria-labelledby="lobby-models-title">
        <h3 id="lobby-models-title">模型配置</h3>
        <ModelConfigList />
      </section>
    </LobbyModal>
  );
}
