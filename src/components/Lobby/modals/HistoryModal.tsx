import { useEffect, useState } from 'react';
import { listGames, type GameListItem } from '../../../lib/gameApi';
import { LobbyModal } from '../LobbyModal';

type HistoryModalProps = {
  open: boolean;
  onClose: () => void;
  onEnterReplay: (gameId: string) => void;
};

export function HistoryModal({ open, onClose, onEnterReplay }: HistoryModalProps) {
  const [games, setGames] = useState<GameListItem[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    let cancelled = false;
    setStatus('loading');
    setErrorMessage(null);
    listGames()
      .then((rows) => {
        if (!cancelled) {
          setGames(rows);
          setStatus('idle');
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setStatus('error');
          setErrorMessage(error instanceof Error ? error.message : '历史复盘加载失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  return (
    <LobbyModal open={open} onClose={onClose} title="历史复盘">
      <div className="history-list" aria-live="polite">
        {status === 'loading' && (
          <p className="lobby-modal-text">正在读取历史对局...</p>
        )}
        {status === 'error' && (
          <p className="lobby-modal-tip">历史复盘加载失败：{errorMessage}</p>
        )}
        {status === 'idle' && games.length === 0 && (
          <p className="lobby-modal-tip">还没有可复盘的对局。</p>
        )}
        {games.map((game) => (
          <article className="history-game-row" key={game.game_id}>
            <div>
              <strong>{shortGameId(game.game_id)}</strong>
              <span>{formatGameMeta(game)}</span>
            </div>
            <button
              type="button"
              className="history-replay-btn"
              onClick={() => onEnterReplay(game.game_id)}
            >
              复盘
            </button>
          </article>
        ))}
      </div>
    </LobbyModal>
  );
}

function shortGameId(gameId: string) {
  return gameId.length > 12 ? `${gameId.slice(0, 8)}...` : gameId;
}

function formatGameMeta(game: GameListItem) {
  const started = game.started_at ? new Date(game.started_at).toLocaleString() : '未知时间';
  const winner = game.winner === 'wolf' ? '狼人胜利' : game.winner === 'good' ? '好人胜利' : game.status;
  return `${started} / ${winner} / ${game.event_count} 事件`;
}
