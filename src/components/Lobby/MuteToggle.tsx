import { Volume2, VolumeX } from 'lucide-react';
import { useLobbyAudio } from '../../hooks/useLobbyAudio';

export function MuteToggle() {
  const { muted, toggleMute } = useLobbyAudio();
  const Icon = muted ? VolumeX : Volume2;

  return (
    <button
      type="button"
      className="mute-toggle"
      aria-label={muted ? '开启声音' : '静音'}
      onClick={toggleMute}
    >
      <Icon aria-hidden="true" size={24} strokeWidth={2.25} />
    </button>
  );
}
