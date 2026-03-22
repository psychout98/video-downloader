import { apiClient, MpcStatus, MPC_COMMANDS } from '../../api/client';

interface Props {
  status: MpcStatus;
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  onStatusChange: () => void;
}

function PlayerControls({ status, showToast, onStatusChange }: Props) {
  const isShow = status.media?.type === 'tv' || status.media?.type === 'anime';

  const handlePlayPause = async () => {
    try {
      const cmd = status.is_playing ? MPC_COMMANDS.PAUSE : MPC_COMMANDS.PLAY;
      await apiClient.sendMpcCommand(cmd);
      onStatusChange();
    } catch {
      showToast('Failed to control playback', 'error');
    }
  };

  const handleStop = async () => {
    try {
      await apiClient.sendMpcCommand(MPC_COMMANDS.STOP);
      onStatusChange();
    } catch {
      showToast('Failed to stop', 'error');
    }
  };

  const handleSkip = async (direction: 'forward' | 'back') => {
    const delta = 30000;
    const newPos =
      direction === 'forward'
        ? Math.min(status.position_ms + delta, status.duration_ms)
        : Math.max(status.position_ms - delta, 0);
    try {
      await apiClient.sendMpcCommand(MPC_COMMANDS.SEEK, newPos);
      onStatusChange();
    } catch {
      showToast('Failed to seek', 'error');
    }
  };

  const handleNext = async () => {
    try {
      await apiClient.mpcNext();
      onStatusChange();
      showToast('Next episode', 'info');
    } catch {
      showToast('No next episode available', 'error');
    }
  };

  const handlePrev = async () => {
    try {
      await apiClient.mpcPrev();
      onStatusChange();
      showToast('Previous episode', 'info');
    } catch {
      showToast('No previous episode available', 'error');
    }
  };

  const handleVolumeChange = (vol: number) => {
    apiClient.sendMpcCommand(MPC_COMMANDS.VOLUME_UP, vol);
  };

  const handleToggleMute = () => {
    apiClient.sendMpcCommand(MPC_COMMANDS.TOGGLE_MUTE);
  };

  return (
    <div className="space-y-5">
      {/* Main transport controls */}
      <div className="flex items-center justify-center gap-3">
        {/* Prev episode */}
        {isShow && (
          <button
            onClick={handlePrev}
            className="btn-secondary p-3 text-sm"
            title="Previous episode"
          >
            &#x23EE;
          </button>
        )}

        <button
          onClick={() => handleSkip('back')}
          className="btn-secondary p-3 text-sm"
          title="Skip back 30s"
        >
          -30s
        </button>

        <button
          onClick={handlePlayPause}
          className="btn-primary px-8 py-3 text-lg"
        >
          {status.is_playing ? 'Pause' : 'Play'}
        </button>

        <button
          onClick={handleStop}
          className="btn-secondary p-3 text-sm"
          title="Stop"
        >
          Stop
        </button>

        <button
          onClick={() => handleSkip('forward')}
          className="btn-secondary p-3 text-sm"
          title="Skip forward 30s"
        >
          +30s
        </button>

        {/* Next episode */}
        {isShow && (
          <button
            onClick={handleNext}
            className="btn-secondary p-3 text-sm"
            title="Next episode"
          >
            &#x23ED;
          </button>
        )}
      </div>

      {/* Volume */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-dark-text/60 w-14">
          Vol: {status.volume}
        </span>
        <input
          type="range"
          min="0"
          max="100"
          value={status.volume}
          onChange={(e) => handleVolumeChange(Number(e.target.value))}
          className="flex-1 h-2 bg-dark-bg rounded appearance-none cursor-pointer accent-dark-accent"
        />
        <button
          onClick={handleToggleMute}
          className={`btn-sm-secondary text-xs ${status.muted ? 'text-error' : ''}`}
        >
          {status.muted ? 'Unmute' : 'Mute'}
        </button>
      </div>
    </div>
  );
}

export default PlayerControls;
