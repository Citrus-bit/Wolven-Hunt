import { useCallback, useState } from 'react';
import { GamePage } from './components/Game/GamePage';
import { LobbyHome } from './components/Lobby/LobbyHome';
import { useLobbyAudio } from './hooks/useLobbyAudio';

type Page = 'lobby' | 'game';
type TransitionPhase = 'idle' | 'fade-out' | 'fade-in';

export default function App() {
  const [page, setPage] = useState<Page>('lobby');
  const [phase, setPhase] = useState<TransitionPhase>('idle');
  const { muted, toggleMute } = useLobbyAudio();

  const handleEnterGame = useCallback(() => {
    if (phase !== 'idle') {
      return;
    }

    if (!muted) {
      toggleMute();
    }

    setPhase('fade-out');
  }, [muted, phase, toggleMute]);

  const handleTransitionEnd = () => {
    if (phase === 'fade-out') {
      setPage('game');
      requestAnimationFrame(() => {
        setPhase('fade-in');
      });
      return;
    }

    if (phase === 'fade-in') {
      setPhase('idle');
    }
  };

  return (
    <>
      {page === 'lobby' && <LobbyHome onEnterGame={handleEnterGame} />}
      {page === 'game' && <GamePage />}
      <div
        className={`page-transition-overlay ${
          phase !== 'idle' ? `page-transition-overlay--${phase}` : ''
        }`}
        onTransitionEnd={handleTransitionEnd}
      />
    </>
  );
}
