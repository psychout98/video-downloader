import { useState, useEffect, useRef } from 'react';
import { apiClient, MpcStatus, MPC_COMMANDS } from '../../api/client';

interface Props {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

function NowPlayingTab({ showToast }: Props) {
  const [status, setStatus] = useState<MpcStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval>>();

  const fetchStatus = async () => {
    try {
      const data = await apiClient.getMpcStatus();
      setStatus(data);
      setError(data.reachable ? null : 'MPC-BE not reachable');
    } catch {
      setError('MPC-BE not reachable');
      setStatus(null);
    }
  };

  useEffect(() => {
    fetchStatus();

    const handleVisibilityChange = () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      const interval = document.hidden ? 5000 : 1500;
      pollIntervalRef.current = setInterval(fetchStatus, interval);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    pollIntervalRef.current = setInterval(fetchStatus, 1500);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const handlePlayPause = async () => {
    try {
      const command = status?.is_playing ? MPC_COMMANDS.PAUSE : MPC_COMMANDS.PLAY;
      await apiClient.sendMpcCommand(command);
      await fetchStatus();
    } catch {
      showToast('Failed to control playback', 'error');
    }
  };

  const handleStop = async () => {
    try {
      await apiClient.sendMpcCommand(MPC_COMMANDS.STOP);
      await fetchStatus();
    } catch {
      showToast('Failed to stop playback', 'error');
    }
  };

  const handleSeek = async (newPositionMs: number) => {
    try {
      await apiClient.sendMpcCommand(MPC_COMMANDS.SEEK, newPositionMs);
      await fetchStatus();
    } catch {
      showToast('Failed to seek', 'error');
    }
  };

  const handleSkip = async (direction: 'forward' | 'back') => {
    if (!status) return;
    const delta = 30000;
    const newPosition = direction === 'forward'
      ? Math.min(status.position_ms + delta, status.duration_ms)
      : Math.max(status.position_ms - delta, 0);
    await handleSeek(newPosition);
  };

  if (error) {
    return (
      <div className="card text-center py-12">
        <p className="text-error text-lg mb-4">{error}</p>
        <p className="text-dark-text/60">Please ensure MPC-BE is running and accessible</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="card text-center py-12">
        <p className="text-dark-text/60">Loading...</p>
      </div>
    );
  }

  const progress = status.duration_ms > 0
    ? (status.position_ms / status.duration_ms) * 100
    : 0;

  return (
    <div className="card max-w-2xl mx-auto">
      {/* Current File Info */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dark-text truncate">
          {status.filename || 'No file loaded'}
        </h2>
        {status.file && status.file !== status.filename && (
          <p className="text-xs text-dark-text/50 truncate mt-1">{status.file}</p>
        )}
      </div>

      {/* Player Controls */}
      <div className="space-y-6">
        {/* Timeline */}
        <div>
          <div
            className="progress-bar cursor-pointer h-3"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const percent = (e.clientX - rect.left) / rect.width;
              handleSeek(Math.round(percent * status.duration_ms));
            }}
          >
            <div className="progress-fill h-full" style={{ width: `${progress}%` }} />
          </div>
          <div className="flex justify-between text-xs text-dark-text/60 mt-2">
            <span>{status.position_str}</span>
            <span>{status.duration_str}</span>
          </div>
        </div>

        {/* Main Controls */}
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => handleSkip('back')}
            className="btn-secondary p-3"
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
            className="btn-secondary p-3"
            title="Stop"
          >
            Stop
          </button>
          <button
            onClick={() => handleSkip('forward')}
            className="btn-secondary p-3"
            title="Skip forward 30s"
          >
            +30s
          </button>
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
            onChange={(e) => {
              const vol = Number(e.target.value);
              apiClient.sendMpcCommand(MPC_COMMANDS.VOLUME_UP, vol);
            }}
            className="flex-1 h-2 bg-dark-bg rounded appearance-none cursor-pointer accent-dark-accent"
          />
          <button
            onClick={() => apiClient.sendMpcCommand(MPC_COMMANDS.TOGGLE_MUTE)}
            className={`btn-sm-secondary text-xs ${status.muted ? 'text-error' : ''}`}
          >
            {status.muted ? 'Unmute' : 'Mute'}
          </button>
        </div>
      </div>

      {/* Status */}
      <div className="mt-6 pt-6 border-t border-dark-text/10">
        <p className="text-xs text-dark-text/60 text-center">
          Status: <span className="capitalize font-semibold">{status.state}</span>
        </p>
      </div>
    </div>
  );
}

export default NowPlayingTab;
