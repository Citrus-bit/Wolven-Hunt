import { useCallback, useRef, useState } from 'react';
import { GamePage } from './components/Game/GamePage';
import { LobbyHome } from './components/Lobby/LobbyHome';
import { useLobbyAudio } from './hooks/useLobbyAudio';
import { readLiveGameSession } from './lib/liveGameSession';

type Page = 'lobby' | 'game';
type TransitionPhase = 'idle' | 'fade-out' | 'fade-in';

export default function App() {
  const [restoredLiveSession] = useState(() => readLiveGameSession());
  const [page, setPage] = useState<Page>(
    restoredLiveSession ? 'game' : 'lobby',
  );
  const [phase, setPhase] = useState<TransitionPhase>('idle');
  const [replayGameId, setReplayGameId] = useState<string | null>(null);
  const targetPageRef = useRef<Page | null>(null);
  const { pauseForGame } = useLobbyAudio();

  const handleEnterGame = useCallback(() => {
    if (phase !== 'idle') {
      return;
    }

    pauseForGame();

    targetPageRef.current = 'game';
    setReplayGameId(null);
    setPhase('fade-out');
  }, [pauseForGame, phase]);

  const handleEnterReplay = useCallback((gameId: string) => {
    if (phase !== 'idle') {
      return;
    }
    pauseForGame();
    setReplayGameId(gameId);
    targetPageRef.current = 'game';
    setPhase('fade-out');
  }, [pauseForGame, phase]);

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
      {page === 'lobby' && (
        <LobbyHome
          onEnterGame={handleEnterGame}
          onEnterReplay={handleEnterReplay}
        />
      )}
      {page === 'game' && (
        <GamePage onExitGame={handleExitGame} replayGameId={replayGameId} />
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
