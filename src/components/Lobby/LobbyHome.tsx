import { useEffect } from 'react';
import { useLobbyAudio } from '../../hooks/useLobbyAudio';
import { LobbyButtons } from './LobbyButtons';
import { LobbyVideo } from './LobbyVideo';
import { MuteToggle } from './MuteToggle';

export function LobbyHome() {
  const { ensureUnlock } = useLobbyAudio();

  useEffect(() => {
    let removed = false;

    const removeUnlockListeners = () => {
      if (removed) {
        return;
      }

      removed = true;
      document.removeEventListener('pointerdown', handleFirstInteraction);
      document.removeEventListener('keydown', handleFirstInteraction);
    };

    const handleFirstInteraction = () => {
      ensureUnlock().then((unlocked) => {
        if (unlocked) {
          removeUnlockListeners();
        }
      });
    };

    document.addEventListener('pointerdown', handleFirstInteraction);
    document.addEventListener('keydown', handleFirstInteraction);

    return removeUnlockListeners;
  }, [ensureUnlock]);

  return (
    <main className="lobby-shell" aria-label="Wolven Hunt 大厅">
      <LobbyVideo />
      <div className="lobby-shade" aria-hidden="true" />
      <MuteToggle />
      <LobbyButtons />
    </main>
  );
}
