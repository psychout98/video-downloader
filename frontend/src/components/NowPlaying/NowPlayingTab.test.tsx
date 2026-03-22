import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NowPlayingTab from './NowPlayingTab';
import * as apiClientModule from '../../api/client';
import { MPC_COMMANDS } from '../../api/client';

vi.mock('../../api/client');

const makeMockStatus = (overrides = {}) => ({
  reachable: true,
  file: '/movies/action/movie.mkv',
  filename: 'movie.mkv',
  state: 'playing',
  is_playing: true,
  is_paused: false,
  position_ms: 30000,
  duration_ms: 120000,
  position_str: '0:30',
  duration_str: '2:00',
  volume: 75,
  muted: false,
  media: null,
  ...overrides,
});

describe('NowPlayingTab', () => {
  let showToastMock: ReturnType<typeof vi.fn>;
  const mockApiClient = apiClientModule as any;

  beforeEach(() => {
    showToastMock = vi.fn();
    vi.clearAllMocks();
    mockApiClient.apiClient = {
      getMpcStatus: vi.fn().mockResolvedValue(makeMockStatus()),
      sendMpcCommand: vi.fn().mockResolvedValue({ ok: true }),
      openInMpc: vi.fn().mockResolvedValue({ ok: true, launched: true }),
      mpcNext: vi.fn().mockResolvedValue({ ok: true }),
      mpcPrev: vi.fn().mockResolvedValue({ ok: true }),
    };
    mockApiClient.MPC_COMMANDS = MPC_COMMANDS;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Error states', () => {
    it('should show error when getMpcStatus rejects', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockRejectedValue(new Error('Connection failed'));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('MPC-BE not reachable')).toBeInTheDocument();
      });
    });

    it('should show error when status is not reachable', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockResolvedValue(
        makeMockStatus({ reachable: false })
      );

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('MPC-BE not reachable')).toBeInTheDocument();
      });
    });

    it('should show help text in error state', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockRejectedValue(new Error('Failed'));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText(/Please ensure MPC-BE is running/i)).toBeInTheDocument();
      });
    });
  });

  describe('Player rendering', () => {
    it('should render filename when status is loaded', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('movie.mkv')).toBeInTheDocument();
      });
    });

    it('should render No file loaded when filename is null', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockResolvedValue(
        makeMockStatus({ filename: null, file: null })
      );

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('No file loaded')).toBeInTheDocument();
      });
    });

    it('should show Pause button when playing', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument();
      });
    });

    it('should show Play button when paused', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockResolvedValue(
        makeMockStatus({ is_playing: false, is_paused: true })
      );

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
      });
    });

    it('should show volume level', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Vol: 75')).toBeInTheDocument();
      });
    });

    it('should show Mute button when not muted', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Mute' })).toBeInTheDocument();
      });
    });

    it('should show Unmute button when muted', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockResolvedValue(
        makeMockStatus({ muted: true })
      );

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Unmute' })).toBeInTheDocument();
      });
    });

    it('should show playback state', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText(/Status:/i)).toBeInTheDocument();
        expect(screen.getByText('playing')).toBeInTheDocument();
      });
    });
  });

  describe('Playback controls', () => {
    it('should send PAUSE command when Pause button clicked while playing', async () => {
      const user = userEvent.setup();
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Pause' }));
      await user.click(screen.getByRole('button', { name: 'Pause' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(MPC_COMMANDS.PAUSE);
    });

    it('should send PLAY command when Play button clicked while paused', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.getMpcStatus = vi.fn()
        .mockResolvedValueOnce(makeMockStatus({ is_playing: false }))
        .mockResolvedValue(makeMockStatus({ is_playing: false }));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Play' }));
      await user.click(screen.getByRole('button', { name: 'Play' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(MPC_COMMANDS.PLAY);
    });

    it('should show toast on play/pause error', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.sendMpcCommand = vi.fn().mockRejectedValue(new Error('Command failed'));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Pause' }));
      await user.click(screen.getByRole('button', { name: 'Pause' }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to control playback', 'error');
      });
    });

    it('should send STOP command when Stop button clicked', async () => {
      const user = userEvent.setup();
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Stop' }));
      await user.click(screen.getByRole('button', { name: 'Stop' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(MPC_COMMANDS.STOP);
    });

    it('should show toast on stop error', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.sendMpcCommand = vi.fn().mockRejectedValue(new Error('Failed'));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Stop' }));
      await user.click(screen.getByRole('button', { name: 'Stop' }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to stop', 'error');
      });
    });

    it('should skip forward 30 seconds', async () => {
      const user = userEvent.setup();
      // position_ms=30000, duration_ms=120000, delta=30000 → new=60000
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: '+30s' }));
      await user.click(screen.getByRole('button', { name: '+30s' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(
        MPC_COMMANDS.SEEK, 60000
      );
    });

    it('should cap skip forward at duration', async () => {
      const user = userEvent.setup();
      // position=100000, duration=120000, delta=30000 → min(130000, 120000)=120000
      mockApiClient.apiClient.getMpcStatus = vi.fn()
        .mockResolvedValueOnce(makeMockStatus({ position_ms: 100000, duration_ms: 120000 }))
        .mockResolvedValue(makeMockStatus());

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: '+30s' }));
      await user.click(screen.getByRole('button', { name: '+30s' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(
        MPC_COMMANDS.SEEK, 120000
      );
    });

    it('should skip back 30 seconds', async () => {
      const user = userEvent.setup();
      // position_ms=30000, delta=30000 → max(0, 0)=0
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: '-30s' }));
      await user.click(screen.getByRole('button', { name: '-30s' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(
        MPC_COMMANDS.SEEK, 0
      );
    });

    it('should skip back but not go below 0', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.getMpcStatus = vi.fn()
        .mockResolvedValueOnce(makeMockStatus({ position_ms: 10000 }))
        .mockResolvedValue(makeMockStatus());

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: '-30s' }));
      await user.click(screen.getByRole('button', { name: '-30s' }));

      // max(10000 - 30000, 0) = 0
      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(
        MPC_COMMANDS.SEEK, 0
      );
    });

    it('should not skip when status is null', async () => {
      mockApiClient.apiClient.getMpcStatus = vi.fn().mockResolvedValue(
        makeMockStatus({ reachable: false })
      );

      render(<NowPlayingTab showToast={showToastMock} />);

      // In error state, skip buttons don't render — so no skip command is sent
      await waitFor(() => {
        expect(screen.getByText('MPC-BE not reachable')).toBeInTheDocument();
      });
      expect(mockApiClient.apiClient.sendMpcCommand).not.toHaveBeenCalled();
    });

    it('should show toast on seek error', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.sendMpcCommand = vi.fn().mockRejectedValue(new Error('Seek failed'));

      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: '+30s' }));
      await user.click(screen.getByRole('button', { name: '+30s' }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to seek', 'error');
      });
    });
  });

  describe('Volume control', () => {
    it('should send VOLUME_UP command when slider changes', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByText('Vol: 75'));

      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '80' } });

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(MPC_COMMANDS.VOLUME_UP, 80);
    });

    it('should send TOGGLE_MUTE when Mute button clicked', async () => {
      const user = userEvent.setup();
      render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => screen.getByRole('button', { name: 'Mute' }));
      await user.click(screen.getByRole('button', { name: 'Mute' }));

      expect(mockApiClient.apiClient.sendMpcCommand).toHaveBeenCalledWith(MPC_COMMANDS.TOGGLE_MUTE);
    });
  });

  describe('Polling and cleanup', () => {
    it('should call getMpcStatus after SSE falls back to polling', async () => {
      render(<NowPlayingTab showToast={showToastMock} />);

      // After SSE fails, it falls back to polling which calls getMpcStatus
      await waitFor(() => {
        expect(mockApiClient.apiClient.getMpcStatus).toHaveBeenCalled();
      });
    });

    it('should clean up on unmount', async () => {
      const { unmount } = render(<NowPlayingTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(mockApiClient.apiClient.getMpcStatus).toHaveBeenCalled();
      });

      const callsBefore = mockApiClient.apiClient.getMpcStatus.mock.calls.length;
      unmount();
      // After unmount, no more calls should be made
      await act(async () => { await new Promise(r => setTimeout(r, 100)); });
      expect(mockApiClient.apiClient.getMpcStatus.mock.calls.length).toBe(callsBefore);
    });
  });
});
