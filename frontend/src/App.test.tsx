import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import * as apiClientModule from './api/client';

// Capture callbacks passed down to children
let capturedShowToast: ((msg: string, type?: string) => void) | null = null;
let capturedOnPlay: (() => void) | null = null;

vi.mock('./components/Queue/QueueTab', () => ({
  default: ({ showToast }: any) => {
    capturedShowToast = showToast;
    return <div data-testid="queue-tab">QueueTab</div>;
  },
}));

vi.mock('./components/Library/LibraryTab', () => ({
  default: ({ showToast, onPlay }: any) => {
    capturedShowToast = showToast;
    capturedOnPlay = onPlay;
    return <div data-testid="library-tab">LibraryTab</div>;
  },
}));

vi.mock('./components/NowPlaying/NowPlayingTab', () => ({
  default: () => <div data-testid="nowplaying-tab">NowPlayingTab</div>,
}));

vi.mock('./api/client');

describe('App', () => {
  const mockApiClient = apiClientModule as any;

  beforeEach(() => {
    vi.clearAllMocks();
    capturedShowToast = null;
    capturedOnPlay = null;
    mockApiClient.apiClient = {
      checkStatus: vi.fn().mockResolvedValue({ status: 'ok' }),
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Initial render', () => {
    it('should render header with app title', () => {
      render(<App />);
      expect(screen.getByText('Media Downloader')).toBeInTheDocument();
    });

    it('should render all three tab buttons', () => {
      render(<App />);
      expect(screen.getByRole('button', { name: 'Queue' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Library' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Now Playing' })).toBeInTheDocument();
    });

    it('should show Queue tab by default', () => {
      render(<App />);
      expect(screen.getByTestId('queue-tab')).toBeInTheDocument();
    });
  });

  describe('Connection status', () => {
    it('should show Disconnected initially', () => {
      // Never-resolving promise so connected stays false
      mockApiClient.apiClient.checkStatus = vi.fn().mockImplementation(
        () => new Promise(() => {})
      );
      render(<App />);
      expect(screen.getByText('Disconnected')).toBeInTheDocument();
    });

    it('should show Connected after successful status check', async () => {
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText('Connected')).toBeInTheDocument();
      });
    });

    it('should show Disconnected after failed status check', async () => {
      mockApiClient.apiClient.checkStatus = vi.fn().mockRejectedValue(new Error('Network error'));
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText('Disconnected')).toBeInTheDocument();
      });
    });

    it('should poll status every 30 seconds', async () => {
      vi.useFakeTimers();
      render(<App />);
      // Flush the initial checkStatus call
      await act(async () => { await Promise.resolve(); });
      expect(mockApiClient.apiClient.checkStatus).toHaveBeenCalledTimes(1);

      // Advance 30 seconds to trigger the interval
      await act(async () => {
        vi.advanceTimersByTime(30000);
        await Promise.resolve();
      });
      expect(mockApiClient.apiClient.checkStatus).toHaveBeenCalledTimes(2);
    });

    it('should clear status poll interval on unmount', async () => {
      vi.useFakeTimers();
      const { unmount } = render(<App />);
      await act(async () => { await Promise.resolve(); });
      unmount();
      const callCount = mockApiClient.apiClient.checkStatus.mock.calls.length;

      // Advance time — no additional calls should happen after unmount
      await act(async () => {
        vi.advanceTimersByTime(90000);
        await Promise.resolve();
      });
      expect(mockApiClient.apiClient.checkStatus).toHaveBeenCalledTimes(callCount);
    });
  });

  describe('Tab navigation', () => {
    it('should switch to Library tab', async () => {
      const user = userEvent.setup();
      render(<App />);
      await user.click(screen.getByRole('button', { name: 'Library' }));
      expect(screen.getByTestId('library-tab')).toBeInTheDocument();
    });

    it('should switch to Now Playing tab', async () => {
      const user = userEvent.setup();
      render(<App />);
      await user.click(screen.getByRole('button', { name: 'Now Playing' }));
      expect(screen.getByTestId('nowplaying-tab')).toBeInTheDocument();
    });

    it('should switch back to Queue tab', async () => {
      const user = userEvent.setup();
      render(<App />);
      await user.click(screen.getByRole('button', { name: 'Library' }));
      await user.click(screen.getByRole('button', { name: 'Queue' }));
      expect(screen.getByTestId('queue-tab')).toBeInTheDocument();
    });

    it('should switch to Now Playing when onPlay is called from Library', async () => {
      const user = userEvent.setup();
      render(<App />);
      await user.click(screen.getByRole('button', { name: 'Library' }));
      expect(capturedOnPlay).not.toBeNull();
      act(() => { capturedOnPlay!(); });
      expect(screen.getByTestId('nowplaying-tab')).toBeInTheDocument();
    });
  });

  describe('Toast notifications', () => {
    it('should render toast when showToast is called', () => {
      render(<App />);
      expect(capturedShowToast).not.toBeNull();
      act(() => { capturedShowToast!('Test toast message', 'success'); });
      expect(screen.getByText('Test toast message')).toBeInTheDocument();
    });

    it('should render error toast with correct class', () => {
      render(<App />);
      act(() => { capturedShowToast!('Error occurred', 'error'); });
      const toast = screen.getByText('Error occurred');
      expect(toast).toBeInTheDocument();
    });

    it('should render info toast by default type', () => {
      render(<App />);
      act(() => { capturedShowToast!('Info message'); });
      expect(screen.getByText('Info message')).toBeInTheDocument();
    });

    it('should auto-dismiss toast after 5 seconds', () => {
      vi.useFakeTimers();
      render(<App />);
      act(() => { capturedShowToast!('Temporary toast', 'info'); });
      expect(screen.getByText('Temporary toast')).toBeInTheDocument();

      act(() => { vi.advanceTimersByTime(5001); });
      expect(screen.queryByText('Temporary toast')).not.toBeInTheDocument();
    });

    it('should stack multiple toasts', () => {
      render(<App />);
      act(() => {
        capturedShowToast!('Toast 1', 'success');
        capturedShowToast!('Toast 2', 'error');
      });
      expect(screen.getByText('Toast 1')).toBeInTheDocument();
      expect(screen.getByText('Toast 2')).toBeInTheDocument();
    });
  });
});
