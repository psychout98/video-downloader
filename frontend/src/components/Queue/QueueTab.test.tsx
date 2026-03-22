import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QueueTab from './QueueTab';
import * as apiClient from '../../api/client';

vi.mock('../../api/client');

describe('QueueTab', () => {
  let showToastMock: ReturnType<typeof vi.fn>;
  const mockApiClient = apiClient as any;

  beforeEach(() => {
    showToastMock = vi.fn();
    vi.clearAllMocks();

    // Default mocks
    mockApiClient.apiClient = {
      getJobs: vi.fn().mockResolvedValue([]),
      searchMedia: vi.fn(),
      downloadStream: vi.fn(),
      deleteJob: vi.fn(),
      retryJob: vi.fn(),
    };
  });

  describe('Search functionality', () => {
    it('should render search input and button', () => {
      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      const button = screen.getByRole('button', { name: /Search/i });

      expect(input).toBeInTheDocument();
      expect(button).toBeInTheDocument();
    });

    it('should disable search button when input is empty', () => {
      render(<QueueTab showToast={showToastMock} />);

      const button = screen.getByRole('button', { name: /Search/i });
      expect(button).toBeDisabled();
    });

    it('should enable search button when input has value', async () => {
      const user = userEvent.setup();
      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      const button = screen.getByRole('button', { name: /Search/i });

      await user.type(input, 'Breaking Bad');

      expect(button).not.toBeDisabled();
    });

    it('should call searchMedia on form submit', async () => {
      const user = userEvent.setup();
      const mockSearchResponse = {
        search_id: 'search-123',
        media: {
          title: 'Breaking Bad',
          year: 2008,
          imdb_id: 'tt0903747',
          tmdb_id: 1396,
          type: 'tv',
          season: null,
          episode: null,
          is_anime: false,
          episode_titles: {},
          overview: 'A chemistry teacher...',
          poster_path: '/path/to/poster.jpg',
          poster_url: 'http://example.com/poster.jpg',
        },
        streams: [],
        warning: null,
      };
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      const button = screen.getByRole('button', { name: /Search/i });

      await user.type(input, 'Breaking Bad');
      await user.click(button);

      await waitFor(() => {
        expect(mockApiClient.apiClient.searchMedia).toHaveBeenCalledWith('Breaking Bad');
      });
    });

    it('should show warning toast if search returns warning', async () => {
      const user = userEvent.setup();
      const mockSearchResponse = {
        search_id: 'search-123',
        media: { title: 'Test', type: 'movie', year: null, imdb_id: null, tmdb_id: null, season: null, episode: null, is_anime: false, episode_titles: {}, overview: null, poster_path: null, poster_url: null },
        streams: [],
        warning: 'Limited results available',
      };
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, 'Test');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Limited results available', 'info');
      });
    });

    it('should show error toast on search failure', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockRejectedValue(new Error('Network error'));

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, 'Test');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to search media', 'error');
      });
    });
  });

  describe('Job list rendering', () => {
    it('should render job list from polling', async () => {
      const mockJobs = [
        {
          id: 'job-1',
          query: 'Breaking Bad',
          title: 'Breaking Bad',
          year: 2008,
          imdb_id: 'tt0903747',
          type: 'tv',
          season: null,
          episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824,
          downloaded_bytes: 1073741824,
          quality: null,
          torrent_name: 'Breaking.Bad.S01E01',
          rd_torrent_id: null,
          file_path: '/path/to/file',
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Breaking Bad')).toBeInTheDocument();
      });
    });

    it('should show empty state when no jobs', () => {
      mockApiClient.apiClient.getJobs.mockResolvedValue([]);

      render(<QueueTab showToast={showToastMock} />);

      expect(screen.getByText(/No jobs found/i)).toBeInTheDocument();
    });
  });

  describe('Job status badges', () => {
    it('should show success badge for complete status', async () => {
      const mockJobs = [
        {
          id: 'job-1',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824,
          downloaded_bytes: 1073741824,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: '/path/to/file',
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('complete')).toBeInTheDocument();
      });
    });

    it('should show error badge for failed status', async () => {
      const mockJobs = [
        {
          id: 'job-2',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'failed',
          progress: 0,
          size_bytes: null,
          downloaded_bytes: 0,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: null,
          error: 'Download failed',
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('failed')).toBeInTheDocument();
      });
    });

    it('should show info badge for downloading status', async () => {
      const mockJobs = [
        {
          id: 'job-3',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'downloading',
          progress: 0.5,
          size_bytes: 1073741824,
          downloaded_bytes: 536870912,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: null,
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('downloading')).toBeInTheDocument();
      });
    });

    it('should show accent badge for pending status', async () => {
      const mockJobs = [
        {
          id: 'job-4',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'pending',
          progress: 0,
          size_bytes: null,
          downloaded_bytes: 0,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: null,
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('pending')).toBeInTheDocument();
      });
    });
  });

  describe('Progress bar', () => {
    it('should render progress bar for active jobs', async () => {
      const mockJobs = [
        {
          id: 'job-5',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'downloading',
          progress: 0.75,
          size_bytes: 1073741824,
          downloaded_bytes: 805306368,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: null,
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText(/75%/)).toBeInTheDocument();
      });
    });

    it('should not render progress bar for completed jobs', async () => {
      const mockJobs = [
        {
          id: 'job-6',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824,
          downloaded_bytes: 1073741824,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: '/path/to/file',
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.queryByText(/100%/)).not.toBeInTheDocument();
      });
    });
  });

  describe('Job actions', () => {
    it('should delete job when delete button clicked', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'job-7',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824,
          downloaded_bytes: 1073741824,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: '/path/to/file',
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);
      mockApiClient.apiClient.deleteJob.mockResolvedValue({ message: 'Deleted' });

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument();
      });

      const deleteButton = screen.getByRole('button', { name: /Delete/i });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockApiClient.apiClient.deleteJob).toHaveBeenCalledWith('job-7');
      });
    });

    it('should show error toast when delete fails', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'job-8',
          query: 'Test',
          title: 'Test',
          year: null,
          imdb_id: null,
          type: null,
          season: null,
          episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824,
          downloaded_bytes: 1073741824,
          quality: null,
          torrent_name: null,
          rd_torrent_id: null,
          file_path: '/path/to/file',
          error: null,
          log: '',
          stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);
      mockApiClient.apiClient.deleteJob.mockRejectedValue(new Error('Failed'));

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument();
      });

      const deleteButton = screen.getByRole('button', { name: /Delete/i });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to delete job', 'error');
      });
    });

    it('should cancel active job when Cancel button clicked', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'job-active',
          query: 'Active Download',
          title: 'Active Download',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'downloading',
          progress: 0.3,
          size_bytes: 1073741824,
          downloaded_bytes: 322122547,
          quality: null, torrent_name: null, rd_torrent_id: null, file_path: null,
          error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:01:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);
      mockApiClient.apiClient.deleteJob.mockResolvedValue({ message: 'Cancelled' });

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => screen.getByText('Active Download'));

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      await user.click(cancelButton);

      await waitFor(() => {
        expect(mockApiClient.apiClient.deleteJob).toHaveBeenCalledWith('job-active');
      });
    });

    it('should retry failed job when Retry button clicked', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'job-failed',
          query: 'Failed Download',
          title: 'Failed Download',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'failed',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: 'Download timed out',
          log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs
        .mockResolvedValueOnce(mockJobs)
        .mockResolvedValue(mockJobs);
      mockApiClient.apiClient.retryJob.mockResolvedValue({ message: 'Re-queued' });

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => screen.getByText('Failed Download'));

      const retryButton = screen.getByRole('button', { name: /Retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockApiClient.apiClient.retryJob).toHaveBeenCalledWith('job-failed');
        expect(showToastMock).toHaveBeenCalledWith('Job re-queued', 'success');
      });
    });

    it('should show error toast when retry fails', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'job-failed',
          query: 'Failed Download',
          title: 'Failed Download',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'failed',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: 'Timed out',
          log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);
      mockApiClient.apiClient.retryJob.mockRejectedValue(new Error('Retry failed'));

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => screen.getByText('Failed Download'));

      const retryButton = screen.getByRole('button', { name: /Retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to retry job', 'error');
      });
    });
  });

  describe('Download streams', () => {
    const mockSearchResponse = {
      search_id: 'search-123',
      media: {
        title: 'The Matrix',
        year: 1999,
        imdb_id: 'tt0133093',
        tmdb_id: 603,
        type: 'movie',
        season: null,
        episode: null,
        is_anime: false,
        episode_titles: {},
        overview: 'A computer hacker learns about the true nature of reality.',
        poster_path: null,
        poster_url: 'http://example.com/matrix.jpg',
      },
      streams: [
        {
          index: 0,
          name: 'The.Matrix.1999.BluRay.1080p',
          info_hash: 'abc123',
          download_url: null,
          size_bytes: 8589934592,
          seeders: 42,
          is_cached_rd: true,
          magnet: null,
          file_idx: null,
        },
        {
          index: 1,
          name: 'The.Matrix.1999.720p',
          info_hash: 'def456',
          download_url: null,
          size_bytes: null,
          seeders: 0,
          is_cached_rd: false,
          magnet: null,
          file_idx: null,
        },
      ],
      warning: null,
    };

    it('should render stream list after search', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(screen.getByText('The.Matrix.1999.BluRay.1080p')).toBeInTheDocument();
        expect(screen.getByText('The.Matrix.1999.720p')).toBeInTheDocument();
      });
    });

    it('should render RD Cached badge for cached streams', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(screen.getByText('RD Cached')).toBeInTheDocument();
      });
    });

    it('should render seeders badge for streams with seeders', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(screen.getByText('42 seeders')).toBeInTheDocument();
      });
    });

    it('should download stream when Download button clicked', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);
      mockApiClient.apiClient.downloadStream.mockResolvedValue({
        job_id: 'job-new',
        status: 'queued',
        message: 'Download started',
      });
      mockApiClient.apiClient.getJobs.mockResolvedValue([]);

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => screen.getAllByRole('button', { name: 'Download' }));

      const downloadButtons = screen.getAllByRole('button', { name: 'Download' });
      await user.click(downloadButtons[0]);

      await waitFor(() => {
        expect(mockApiClient.apiClient.downloadStream).toHaveBeenCalledWith('search-123', 0);
        expect(showToastMock).toHaveBeenCalledWith('Download started', 'success');
      });
    });

    it('should show error toast when download fails', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);
      mockApiClient.apiClient.downloadStream.mockRejectedValue(new Error('Download error'));

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => screen.getAllByRole('button', { name: 'Download' }));

      const downloadButtons = screen.getAllByRole('button', { name: 'Download' });
      await user.click(downloadButtons[0]);

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to start download', 'error');
      });
    });

    it('should show media poster when search result has poster_url', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        const img = screen.getByRole('img');
        expect(img).toBeInTheDocument();
      });
    });

    it('should show no streams message when streams list is empty', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.searchMedia.mockResolvedValue({
        ...mockSearchResponse,
        streams: [],
      });

      render(<QueueTab showToast={showToastMock} />);

      await user.type(screen.getByPlaceholderText(/Search for movies/i), 'The Matrix');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(screen.getByText('No streams found')).toBeInTheDocument();
      });
    });
  });

  describe('Search edge cases', () => {
    it('should not call searchMedia when query is only whitespace', async () => {
      const user = userEvent.setup();
      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, '   ');

      // Button should be disabled because query.trim() is empty
      const button = screen.getByRole('button', { name: /Search/i });
      expect(button).toBeDisabled();
    });

    it('should show Searching... text on button while loading', async () => {
      const user = userEvent.setup();
      // Never-resolving promise to keep loading state
      mockApiClient.apiClient.searchMedia.mockImplementation(() => new Promise(() => {}));

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, 'Test');
      await user.click(screen.getByRole('button', { name: /Search/i }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Searching/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Searching/i })).toBeDisabled();
      });
    });
  });

  describe('Download edge cases', () => {
    it('should not attempt download when no search result is present', async () => {
      // This tests the guard on line 57: if (!searchResult) return;
      // Since there's no search result, the download buttons won't render,
      // so this is implicitly guarded by the UI. Verify no download buttons exist.
      render(<QueueTab showToast={showToastMock} />);

      expect(screen.queryAllByRole('button', { name: 'Download' })).toHaveLength(0);
    });
  });

  describe('Job display details', () => {
    it('should show job query when title is null', async () => {
      const mockJobs = [
        {
          id: 'job-no-title',
          query: 'my search query',
          title: null,
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'pending',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('my search query')).toBeInTheDocument();
      });
    });

    it('should show download progress with bytes when available', async () => {
      const mockJobs = [
        {
          id: 'job-progress',
          query: 'Test',
          title: 'Test Movie',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'downloading',
          progress: 0.5,
          size_bytes: 1073741824,
          downloaded_bytes: 536870912,
          quality: null, torrent_name: null, rd_torrent_id: null, file_path: null,
          error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:01:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText(/50%/)).toBeInTheDocument();
        // Should show bytes: (512 MB / 1 GB) - parseFloat strips trailing zeros
        expect(screen.getByText(/512 MB/)).toBeInTheDocument();
        expect(screen.getByText(/1 GB/)).toBeInTheDocument();
      });
    });

    it('should filter to show only done/complete jobs', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'active-1',
          query: 'Active Job',
          title: 'Active Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'downloading',
          progress: 0.5,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
        {
          id: 'done-1',
          query: 'Done Job',
          title: 'Done Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824, downloaded_bytes: 1073741824, quality: null,
          torrent_name: null, rd_torrent_id: null, file_path: '/done',
          error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);
      await waitFor(() => screen.getByText('Active Job'));

      await user.click(screen.getByRole('button', { name: 'done' }));

      expect(screen.getByText('Done Job')).toBeInTheDocument();
      expect(screen.queryByText('Active Job')).not.toBeInTheDocument();
    });

  });

  describe('Search result display', () => {
    it('should show search result media info including overview and IMDb badge', async () => {
      const user = userEvent.setup();
      const mockSearchResponse = {
        search_id: 'search-456',
        media: {
          title: 'Inception',
          year: 2010,
          imdb_id: 'tt1375666',
          tmdb_id: 27205,
          type: 'movie',
          season: null,
          episode: null,
          is_anime: false,
          episode_titles: {},
          overview: 'A thief who steals corporate secrets...',
          poster_path: null,
          poster_url: null,
        },
        streams: [
          {
            index: 0,
            name: 'Inception.2010.BluRay',
            info_hash: 'xyz',
            download_url: null,
            size_bytes: 4294967296,
            seeders: 100,
            is_cached_rd: false,
            magnet: null,
            file_idx: null,
          },
        ],
        warning: null,
      };
      mockApiClient.apiClient.searchMedia.mockResolvedValue(mockSearchResponse);

      render(<QueueTab showToast={showToastMock} />);

      const input = screen.getByPlaceholderText(/Search for movies/i);
      await user.type(input, 'Inception');

      const searchButton = screen.getByRole('button', { name: /Search/i });
      expect(searchButton).not.toBeDisabled();
      await user.click(searchButton);

      await waitFor(() => {
        expect(mockApiClient.apiClient.searchMedia).toHaveBeenCalledWith('Inception');
      });

      await waitFor(() => {
        // Verify search result sections are rendered
        expect(screen.getByText('tt1375666')).toBeInTheDocument();
        expect(screen.getByText('movie')).toBeInTheDocument();
        expect(screen.getByText(/A thief who steals corporate secrets/)).toBeInTheDocument();
        // Stream size badge: 4 GB (parseFloat strips trailing zeros)
        expect(screen.getByText('4 GB')).toBeInTheDocument();
        // Stream name
        expect(screen.getByText('Inception.2010.BluRay')).toBeInTheDocument();
        // Available Streams count
        expect(screen.getByText(/Available Streams \(1\)/)).toBeInTheDocument();
      });
    });
  });

  describe('Polling error handling', () => {
    it('should log error when getJobs fetch fails', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      mockApiClient.apiClient.getJobs.mockRejectedValue(new Error('Network error'));

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to fetch jobs:',
          expect.any(Error)
        );
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Job filter tabs', () => {
    it('should filter to show only active jobs', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'active-1',
          query: 'Active Job',
          title: 'Active Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'pending',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
        {
          id: 'done-1',
          query: 'Done Job',
          title: 'Done Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'complete',
          progress: 1,
          size_bytes: 1073741824, downloaded_bytes: 1073741824, quality: null,
          torrent_name: null, rd_torrent_id: null, file_path: '/done',
          error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:05:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);
      await waitFor(() => screen.getByText('Active Job'));

      await user.click(screen.getByRole('button', { name: 'active' }));

      expect(screen.getByText('Active Job')).toBeInTheDocument();
      expect(screen.queryByText('Done Job')).not.toBeInTheDocument();
    });

    it('should filter to show only cancelled jobs under failed tab', async () => {
      const user = userEvent.setup();
      const mockJobs = [
        {
          id: 'cancelled-1',
          query: 'Cancelled Job',
          title: 'Cancelled Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'cancelled',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);
      await waitFor(() => screen.getByText('Cancelled Job'));

      await user.click(screen.getByRole('button', { name: 'failed' }));

      expect(screen.getByText('Cancelled Job')).toBeInTheDocument();
    });

    it('should show job error message when error field is set', async () => {
      const mockJobs = [
        {
          id: 'err-1',
          query: 'Error Job',
          title: 'Error Job',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'failed',
          progress: 0,
          size_bytes: null, downloaded_bytes: 0, quality: null, torrent_name: null,
          rd_torrent_id: null, file_path: null, error: 'Download timed out after 30s',
          log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:00:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Download timed out after 30s')).toBeInTheDocument();
      });
    });

    it('should show job torrent_name when available', async () => {
      const mockJobs = [
        {
          id: 'torrent-1',
          query: 'Some Query',
          title: 'Some Title',
          year: null, imdb_id: null, type: null, season: null, episode: null,
          status: 'downloading',
          progress: 0.5,
          size_bytes: 1073741824, downloaded_bytes: 536870912, quality: null,
          torrent_name: 'Some.Title.2024.BluRay.mkv',
          rd_torrent_id: null, file_path: null, error: null, log: '', stream_data: null,
          created_at: '2024-03-22T10:00:00Z',
          updated_at: '2024-03-22T10:01:00Z',
        },
      ];
      mockApiClient.apiClient.getJobs.mockResolvedValue(mockJobs);

      render(<QueueTab showToast={showToastMock} />);

      await waitFor(() => {
        expect(screen.getByText('Some.Title.2024.BluRay.mkv')).toBeInTheDocument();
      });
    });
  });
});
