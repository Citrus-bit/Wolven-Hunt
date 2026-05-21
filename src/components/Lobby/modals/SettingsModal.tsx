import { LobbyModal } from '../LobbyModal';
import { ModelConfigList } from './ModelConfigList';
import { VolumeSlider } from './VolumeSlider';

type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
};

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="系统设置" variant="settings">
      <section className="lobby-settings-volume" aria-labelledby="lobby-volume-title">
        <h3 id="lobby-volume-title">音量</h3>
        <VolumeSlider />
      </section>
      <section className="lobby-settings-models" aria-labelledby="lobby-models-title">
        <h3 id="lobby-models-title">模型配置</h3>
        <ModelConfigList />
      </section>
    </LobbyModal>
  );
}
