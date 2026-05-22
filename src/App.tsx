import { useCallback, useRef, useState } from 'react';
import { GamePage } from './components/Game/GamePage';
import { LobbyHome } from './components/Lobby/LobbyHome';
import { useLobbyAudio } from './hooks/useLobbyAudio';

type Page = 'lobby' | 'game';
type TransitionPhase = 'idle' | 'fade-out' | 'fade-in';

export default function App() {
  const [page, setPage] = useState<Page>('lobby');
  const [phase, setPhase] = useState<TransitionPhase>('idle');
  const [gameId, setGameId] = useState<string | null>(null);
  const targetPageRef = useRef<Page | null>(null);
  const { muted, toggleMute } = useLobbyAudio();

  const handleEnterGame = useCallback((nextGameId: string) => {
    if (phase !== 'idle') {
      return;
    }

    setGameId(nextGameId);
    if (!muted) {
      toggleMute();
    }

    targetPageRef.current = 'game';
    setPhase('fade-out');
  }, [muted, phase, toggleMute]);

  const handleExitGame = useCallback(() => {
    if (phase !== 'idle') {
      return;
    }

    targetPageRef.current = 'lobby';
    setPhase('fade-out');
  }, [phase]);

  const handleTransitionEnd = () => {
    if (phase === 'fade-out' && targetPageRef.current) {
      setPage(targetPageRef.current);
      targetPageRef.current = null;
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
      {page === 'game' && (
        <GamePage gameId={gameId} onExitGame={handleExitGame} />
      )}
      <div
        className={`page-transition-overlay ${
          phase !== 'idle' ? `page-transition-overlay--${phase}` : ''
        }`}
        onTransitionEnd={handleTransitionEnd}
      />
    </>
  );
}
