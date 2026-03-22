import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LibraryTab from './LibraryTab';
import * as apiClient from '../../api/client';

vi.mock('../../api/client');

describe('LibraryTab', () => {
  let showToastMock: ReturnType<typeof vi.fn>;
  let onPlayMock: ReturnType<typeof vi.fn>;
  const mockApiClient = apiClient as any;

  beforeEach(() => {
    showToastMock = vi.fn();
    onPlayMock = vi.fn();
    vi.clearAllMocks();

    mockApiClient.apiClient = {
      getLibrary: vi.fn().mockResolvedValue([]),
      refreshLibrary: vi.fn(),
      getPosterUrl: vi.fn((path: string) => `/api/library/poster?path=${encodeURIComponent(path)}`),
    };
  });

  describe('Library grid rendering', () => {
    it('should render library grid from API data', async () => {
      const mockItems = [
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: '/posters/breaking-bad.jpg',
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });
    });

    it('should show empty state when library is empty', async () => {
      mockApiClient.apiClient.getLibrary.mockResolvedValue([]);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText(/Library is empty/i)).toBeInTheDocument();
      });
    });

    it('should display item title, type, year, and size', async () => {
      const mockItems = [
        {
          title: 'Inception',
          year: 2010,
          type: 'movie' as const,
          path: '/movies/Inception',
          folder: 'inception',
          file_count: 1,
          size_bytes: 2147483648,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Inception')).toBeInTheDocument();
        // Use exact text to avoid matching the "movies" filter button
        expect(screen.getByText('movie')).toBeInTheDocument();
        expect(screen.getByText('2010')).toBeInTheDocument();
        expect(screen.getByText(/2 GB/)).toBeInTheDocument();
      });
    });
  });

  describe('Filter buttons', () => {
    it('should render filter buttons for all/movies/tv/anime', async () => {
      mockApiClient.apiClient.getLibrary.mockResolvedValue([]);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      expect(screen.getByRole('button', { name: /all/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /movies/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /tv/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /anime/i })).toBeInTheDocument();
    });

    it('should filter by movies', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Inception',
          year: 2010,
          type: 'movie' as const,
          path: '/movies/Inception',
          folder: 'inception',
          file_count: 1,
          size_bytes: 2147483648,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Inception')).toBeInTheDocument();
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });

      const moviesButton = screen.getByRole('button', { name: /movies/i });
      await user.click(moviesButton);

      await waitFor(() => {
        expect(screen.getByText('Inception')).toBeInTheDocument();
        expect(screen.queryByText('Breaking Bad')).not.toBeInTheDocument();
      });
    });

    it('should filter by tv', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Inception',
          year: 2010,
          type: 'movie' as const,
          path: '/movies/Inception',
          folder: 'inception',
          file_count: 1,
          size_bytes: 2147483648,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });

      // Use exact name to avoid matching card buttons whose accessible name includes "tv"
      const tvButton = screen.getByRole('button', { name: 'tv' });
      await user.click(tvButton);

      await waitFor(() => {
        expect(screen.queryByText('Inception')).not.toBeInTheDocument();
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });
    });

    it('should filter by anime', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Attack on Titan',
          year: 2013,
          type: 'anime' as const,
          path: '/anime/Attack on Titan',
          folder: 'attack-on-titan',
          file_count: 12,
          size_bytes: 10737418240,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Attack on Titan')).toBeInTheDocument();
      });

      // Use exact name to avoid matching card buttons whose accessible name includes "anime"
      const animeButton = screen.getByRole('button', { name: 'anime' });
      await user.click(animeButton);

      await waitFor(() => {
        expect(screen.getByText('Attack on Titan')).toBeInTheDocument();
        expect(screen.queryByText('Breaking Bad')).not.toBeInTheDocument();
      });
    });

    it('should reset to all when all button clicked', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Inception',
          year: 2010,
          type: 'movie' as const,
          path: '/movies/Inception',
          folder: 'inception',
          file_count: 1,
          size_bytes: 2147483648,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Inception')).toBeInTheDocument();
      });

      const moviesButton = screen.getByRole('button', { name: /movies/i });
      await user.click(moviesButton);

      await waitFor(() => {
        expect(screen.queryByText('Breaking Bad')).not.toBeInTheDocument();
      });

      const allButton = screen.getByRole('button', { name: /all/i });
      await user.click(allButton);

      await waitFor(() => {
        expect(screen.getByText('Inception')).toBeInTheDocument();
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });
    });
  });

  describe('Search input', () => {
    it('should filter items by title', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Better Call Saul',
          year: 2015,
          type: 'tv' as const,
          path: '/tv/Better Call Saul',
          folder: 'better-call-saul',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
        {
          title: 'Inception',
          year: 2010,
          type: 'movie' as const,
          path: '/movies/Inception',
          folder: 'inception',
          file_count: 1,
          size_bytes: 2147483648,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/Search library/i);
      await user.type(searchInput, 'breaking');

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
        expect(screen.queryByText('Better Call Saul')).not.toBeInTheDocument();
        expect(screen.queryByText('Inception')).not.toBeInTheDocument();
      });
    });

    it('should be case insensitive', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/Search library/i);
      await user.type(searchInput, 'BREAKING');

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });
    });

    it('should show no results message when search has no matches', async () => {
      const user = userEvent.setup();
      const mockItems = [
        {
          title: 'Breaking Bad',
          year: 2008,
          type: 'tv' as const,
          path: '/tv/Breaking Bad',
          folder: 'breaking-bad',
          file_count: 5,
          size_bytes: 5368709120,
          poster: null,
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      mockApiClient.apiClient.getLibrary.mockResolvedValue(mockItems);

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/Search library/i);
      await user.type(searchInput, 'xyz');

      await waitFor(() => {
        expect(screen.getByText(/No results found/i)).toBeInTheDocument();
      });
    });
  });

  describe('Refresh button', () => {
    it('should call refreshLibrary then getLibrary', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.getLibrary.mockResolvedValue([]);
      mockApiClient.apiClient.refreshLibrary.mockResolvedValue({
        renamed: 2,
        posters_fetched: 5,
        errors: [],
        total_items: 20,
      });

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      // Wait for initial load to complete (button starts as "Refreshing..." while loading)
      const refreshButton = await screen.findByRole('button', { name: /Refresh Library/i });
      await user.click(refreshButton);

      await waitFor(() => {
        expect(mockApiClient.apiClient.refreshLibrary).toHaveBeenCalled();
        expect(mockApiClient.apiClient.getLibrary).toHaveBeenCalledWith(true);
      });
    });

    it('should show success toast after refresh', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.getLibrary.mockResolvedValue([]);
      mockApiClient.apiClient.refreshLibrary.mockResolvedValue({
        renamed: 2,
        posters_fetched: 5,
        errors: [],
        total_items: 20,
      });

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      const refreshButton = await screen.findByRole('button', { name: /Refresh Library/i });
      await user.click(refreshButton);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith(
          'Refreshed: 2 renamed, 5 posters fetched',
          'success'
        );
      });
    });

    it('should show error toast on refresh failure', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.getLibrary.mockResolvedValue([]);
      mockApiClient.apiClient.refreshLibrary.mockRejectedValue(new Error('Refresh failed'));

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      const refreshButton = await screen.findByRole('button', { name: /Refresh Library/i });
      await user.click(refreshButton);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to refresh library', 'error');
      });
    });

    it('should disable refresh button while loading', async () => {
      const user = userEvent.setup();
      // Initial load resolves quickly so we can get to the idle state
      mockApiClient.apiClient.getLibrary
        .mockResolvedValueOnce([])  // fast initial load
        .mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve([]), 100)));
      mockApiClient.apiClient.refreshLibrary.mockResolvedValue({
        renamed: 0, posters_fetched: 0, errors: [], total_items: 0,
      });

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      // Wait for initial load to complete
      const refreshButton = await screen.findByRole('button', { name: /Refresh Library/i });
      expect(refreshButton).not.toBeDisabled();

      await user.click(refreshButton);

      // During the slow getLibrary call after refresh, button should be disabled
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Refreshing\.\.\./i })).toBeDisabled();
      });
    });
  });

  describe('Error handling', () => {
    it('should show error toast when failing to load library', async () => {
      mockApiClient.apiClient.getLibrary.mockRejectedValue(new Error('Network error'));

      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to load library', 'error');
      });
    });
  });

  describe('MediaModal integration', () => {
    const mockItem = {
      title: 'Inception',
      year: 2010,
      type: 'movie' as const,
      path: '/movies/Inception.mkv',
      folder: 'Inception (2010)',
      file_count: 1,
      size_bytes: 2147483648,
      poster: null,
      modified_at: 1711100400,
      storage: 'local',
    };

    beforeEach(() => {
      mockApiClient.apiClient.getLibrary.mockResolvedValue([mockItem]);
      mockApiClient.apiClient.getEpisodes = vi.fn().mockResolvedValue([]);
      mockApiClient.apiClient.openInMpc = vi.fn().mockResolvedValue({ ok: true, launched: true });
    });

    it('should open MediaModal when a library item is clicked', async () => {
      const user = userEvent.setup();
      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      // Wait for items to load
      await waitFor(() => screen.getByText('Inception'));

      // Click the card
      await user.click(screen.getByRole('button', { name: /Inception/i }));

      // Modal should appear
      await waitFor(() => {
        expect(screen.getByRole('button', { name: '×' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Play in MPC-BE' })).toBeInTheDocument();
      });
    });

    it('should close MediaModal when × button is clicked', async () => {
      const user = userEvent.setup();
      render(<LibraryTab showToast={showToastMock} onPlay={onPlayMock} />);

      await waitFor(() => screen.getByText('Inception'));
      await user.click(screen.getByRole('button', { name: /Inception/i }));
      await waitFor(() => screen.getByRole('button', { name: '×' }));

      await user.click(screen.getByRole('button', { name: '×' }));

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: '×' })).not.toBeInTheDocument();
      });
    });
  });
});
