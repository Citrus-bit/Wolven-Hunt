import { BookOpen, X } from 'lucide-react';

type GameTopBarProps = {
  onClickRules: () => void;
  onClickExit: () => void;
};

export function GameTopBar({ onClickRules, onClickExit }: GameTopBarProps) {
  return (
    <div className="game-top-bar" role="toolbar" aria-label="游戏顶栏">
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
  );
}
