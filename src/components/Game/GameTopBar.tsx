import { BookOpen, Volume2, VolumeX, X } from 'lucide-react';

type GameTopBarProps = {
  onClickRules: () => void;
  onClickExit: () => void;
  streamStatus: 'idle' | 'connecting' | 'open' | 'error' | 'failed';
  reconnectAttempts: number;
  autoScrollEnabled: boolean;
  gameAudioMuted: boolean;
  gameAudioError: string | null;
  onToggleAutoScroll: () => void;
  onToggleGameAudio: () => void;
};

export function GameTopBar({
  onClickRules,
  onClickExit,
  streamStatus,
  reconnectAttempts,
  autoScrollEnabled,
  gameAudioMuted,
  gameAudioError,
  onToggleAutoScroll,
  onToggleGameAudio,
}: GameTopBarProps) {
  const statusText = statusMessage(streamStatus, reconnectAttempts);
  const autoScrollLabel = autoScrollEnabled ? '关闭自动滚动' : '开启自动滚动';
  const AudioIcon = gameAudioMuted ? VolumeX : Volume2;
  const audioLabel = gameAudioMuted
    ? '开启游戏语音'
    : gameAudioError
      ? '重试游戏语音'
      : '静音游戏语音';

  return (
    <div className="game-top-stack">
      {statusText && (
        <div className={`game-top-alert game-top-alert--${streamStatus}`} role="status">
          {statusText}
        </div>
      )}
      <div className="game-top-bar" role="toolbar" aria-label="游戏顶栏">
        <button
          type="button"
          className={[
            'game-top-btn',
            'game-top-btn--text',
            autoScrollEnabled ? 'game-top-btn--active' : '',
          ].join(' ')}
          aria-label={autoScrollLabel}
          aria-pressed={autoScrollEnabled}
          title={autoScrollLabel}
          onClick={onToggleAutoScroll}
        >
          自动滚动
        </button>
        <button
          type="button"
          className={[
            'game-top-btn',
            gameAudioError && !gameAudioMuted ? 'game-top-btn--warning' : '',
          ].join(' ')}
          aria-label={audioLabel}
          title={gameAudioError ?? audioLabel}
          onClick={onToggleGameAudio}
        >
          <AudioIcon size={20} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="game-top-btn"
          aria-label="查看游戏规则"
          onClick={onClickRules}
        >
          <BookOpen size={20} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="game-top-btn"
          aria-label="退出游戏返回大厅"
          onClick={onClickExit}
        >
          <X size={20} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function statusMessage(
  status: GameTopBarProps['streamStatus'],
  reconnectAttempts: number,
) {
  if (status === 'connecting' && reconnectAttempts > 0) {
    return `事件流断开，正在重连 ${reconnectAttempts}/5`;
  }
  if (status === 'error') {
    return reconnectAttempts >= 5
      ? '连接失败，请检查后端服务或刷新页面'
      : '事件流断开，正在重连...';
  }
  if (status === 'failed') {
    return '游戏运行失败，请返回大厅后重试';
  }
  return null;
}
