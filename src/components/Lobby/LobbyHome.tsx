import { useEffect, useState } from 'react';
import { useLobbyAudio } from '../../hooks/useLobbyAudio';
import { LobbyButtons, type LobbyAction } from './LobbyButtons';
import { LobbyVideo } from './LobbyVideo';
import { MuteToggle } from './MuteToggle';
import { HistoryModal } from './modals/HistoryModal';
import { SettingsModal } from './modals/SettingsModal';
import { StartModal } from './modals/StartModal';

type LobbyHomeProps = {
  onEnterGame: () => void;
  onEnterReplay: (gameId: string) => void;
};

export function LobbyHome({ onEnterGame, onEnterReplay }: LobbyHomeProps) {
  const { ensureUnlock } = useLobbyAudio();
  const [activeModal, setActiveModal] = useState<LobbyAction | null>(null);

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
      <LobbyButtons onAction={(kind) => setActiveModal(kind)} />
      <StartModal
        open={activeModal === 'start'}
        onClose={() => setActiveModal(null)}
        onEnterGame={onEnterGame}
      />
      <HistoryModal
        open={activeModal === 'history'}
        onClose={() => setActiveModal(null)}
        onEnterReplay={(gameId) => {
          setActiveModal(null);
          onEnterReplay(gameId);
        }}
      />
      <SettingsModal
        open={activeModal === 'settings'}
        onClose={() => setActiveModal(null)}
      />
    </main>
  );
}
