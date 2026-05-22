import { useEffect, useState } from 'react';
import { gameVideoPath } from '../../lib/audioAssets';

type KnightDuelBannerProps = {
  active: boolean;
  onDone: () => void;
};

export function KnightDuelBanner({ active, onDone }: KnightDuelBannerProps) {
  const [mode, setMode] = useState<'banner' | 'video'>('banner');

  useEffect(() => {
    if (!active) {
      setMode('banner');
      return undefined;
    }
    const timer = window.setTimeout(() => setMode('video'), 800);
    return () => window.clearTimeout(timer);
  }, [active]);

  if (!active) {
    return null;
  }

  return (
    <div className="knight-duel-overlay" role="presentation">
      {mode === 'banner' ? (
        <div className="knight-duel-title">骑士发起了对决！</div>
      ) : (
        <video
          className="knight-duel-video"
          src={gameVideoPath('knight_duel')}
          autoPlay
          playsInline
          onEnded={onDone}
          onError={onDone}
        />
      )}
    </div>
  );
}
