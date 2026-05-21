import { useLobbyAudio } from '../../../hooks/useLobbyAudio';

export function VolumeSlider() {
  const { volume, setVolume } = useLobbyAudio();
  const updateVolume = (value: string) => setVolume(Number(value));

  return (
    <div className="lobby-volume-slider">
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={volume}
        onInput={(event) => updateVolume(event.currentTarget.value)}
        onChange={(event) => updateVolume(event.currentTarget.value)}
        aria-label="BGM 音量"
      />
      <span className="lobby-volume-value" aria-live="polite">
        {volume}
      </span>
    </div>
  );
}
