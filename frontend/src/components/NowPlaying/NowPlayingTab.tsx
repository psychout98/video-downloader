import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient, MpcStatus, MPC_COMMANDS } from '../../api/client';
import SeekBar from './SeekBar';
import MediaInfo from './MediaInfo';
import PlayerControls from './PlayerControls';

interface Props {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

type ConnectionState = 'connected' | 'reconnecting' | 'disconnected';

function NowPlayingTab({ showToast }: Props) {
  const [status, setStatus] = useState<MpcStatus | null>(null);
  const [connState, setConnState] = useState<ConnectionState>('disconnected');
  const isDraggingRef = useRef(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const pollIntervalRef = useRef<ReturnType<typeof setInterval>>();

  // Track whether the user is dragging the seek bar so we don't
  // overwrite their drag position with incoming SSE data.
  const handleDraggingChange = useCallback((dragging: boolean) => {
    isDraggingRef.current = dragging;
  }, []);

  // ---- SSE connection with fallback to polling ----

  const connectSSE = useCallback(() => {
    // Clean up any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = undefined;
    }

    const es = new EventSource('/api/mpc/stream');
    eventSourceRef.current = es;

    es.addEventListener('status', (event) => {
      try {
        const data: MpcStatus = JSON.parse(event.data);
        if (!isDraggingRef.current) {
          setStatus(data);
        }
        setConnState('connected');
      } catch {
        // Ignore malformed events
      }
    });

    es.onopen = () => {
      setConnState('connected');
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      setConnState('reconnecting');

      // Fall back to polling while SSE is unavailable
      startPolling();

      // Try to reconnect SSE after a delay
      reconnectTimerRef.current = setTimeout(() => {
        connectSSE();
      }, 5000);
    };
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiClient.getMpcStatus();
      if (!isDraggingRef.current) {
        setStatus(data);
      }
      if (connState === 'disconnected') {
        setConnState('reconnecting');
      }
    } catch {
      setStatus(null);
      setConnState('disconnected');
    }
  }, [connState]);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return;
    fetchStatus();
    pollIntervalRef.current = setInterval(fetchStatus, 2000);
  }, [fetchStatus]);

  useEffect(() => {
    // Try SSE first; if the endpoint doesn't exist, the onerror
    // handler will fall back to polling.
    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [connectSSE]);

  // ---- Seek handler ----

  const handleSeek = useCallback(async (positionMs: number) => {
    try {
      await apiClient.sendMpcCommand(MPC_COMMANDS.SEEK, positionMs);
    } catch {
      showToast('Failed to seek', 'error');
    }
  }, [showToast]);

  const handleStatusChange = useCallback(() => {
    // After a command, do an immediate poll to get fresh state
    fetchStatus();
  }, [fetchStatus]);

  // ---- Visibility-based throttling for polling fallback ----

  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden && pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = setInterval(fetchStatus, 5000);
      } else if (!document.hidden && pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = setInterval(fetchStatus, 2000);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [fetchStatus]);

  // ---- Render ----

  if (!status || !status.reachable) {
    return (
      <div className="card text-center py-12 max-w-2xl mx-auto">
        <p className="text-error text-lg mb-4">MPC-BE not reachable</p>
        <p className="text-dark-text/60">
          Please ensure MPC-BE is running and accessible
        </p>
        {connState === 'reconnecting' && (
          <div className="mt-4 flex items-center justify-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-dark-accent animate-pulse" />
            <span className="text-sm text-dark-text/50">Reconnecting...</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card max-w-2xl mx-auto space-y-6">
      {/* Connection indicator */}
      {connState === 'reconnecting' && (
        <div className="flex items-center gap-2 text-sm text-dark-accent">
          <span className="inline-block w-2 h-2 rounded-full bg-dark-accent animate-pulse" />
          Reconnecting to player...
        </div>
      )}

      {/* Media info: poster + title + episode */}
      <MediaInfo media={status.media} filename={status.filename} />

      {/* Seek bar */}
      <SeekBar
        positionMs={status.position_ms}
        durationMs={status.duration_ms}
        onSeek={handleSeek}
        onDraggingChange={handleDraggingChange}
      />

      {/* Transport controls + volume */}
      <PlayerControls
        status={status}
        showToast={showToast}
        onStatusChange={handleStatusChange}
      />

      {/* Status footer */}
      <div className="pt-4 border-t border-dark-text/10">
        <p className="text-xs text-dark-text/60 text-center">
          Status:{' '}
          <span className="capitalize font-semibold">{status.state}</span>
          {' \u00B7 '}
          {connState === 'connected' ? 'SSE connected' : 'Polling'}
        </p>
      </div>
    </div>
  );
}

export default NowPlayingTab;
