import { LobbyModal } from '../LobbyModal';

type HistoryModalProps = {
  open: boolean;
  onClose: () => void;
};

export function HistoryModal({ open, onClose }: HistoryModalProps) {
  return (
    <LobbyModal open={open} onClose={onClose} title="历史复盘">
      <p className="lobby-modal-text">功能开发中，敬请期待。</p>
      <p className="lobby-modal-tip">
        未来可让用户以上帝视角逐步还原推理过程。
      </p>
    </LobbyModal>
  );
}
