import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiClient, ApiError } from './client';

describe('apiClient', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('checkStatus', () => {
    it('should fetch status and return response', async () => {
      const mockResponse = {
        status: 'ok',
        movies_dir: '/movies',
        tv_dir: '/tv',
        anime_dir: '/anime',
        mpc_be_url: 'http://localhost:13579',
      };
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await apiClient.checkStatus();

      expect(fetchMock).toHaveBeenCalledWith('/api/status');
      expect(result).toEqual(mockResponse);
    });

    it('should throw error on HTTP error status', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Server error' }),
      });

      await expect(apiClient.checkStatus()).rejects.toThrow('Server error');
    });

    it('should use default message when error detail is unavailable', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({}),
      });

      try {
        await apiClient.checkStatus();
      } catch (error) {
        const apiError = error as ApiError;
        expect(apiError.status).toBe(503);
      }
    });
  });

  describe('searchMedia', () => {
    it('should send query and return search response', async () => {
      const mockResponse = {
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
        streams: [
          {
            index: 0,
            name: 'Breaking Bad S01E01',
            info_hash: 'hash123',
            download_url: 'http://example.com/download',
            size_bytes: 1073741824,
            seeders: 100,
            is_cached_rd: true,
            magnet: 'magnet:?xt=urn:btih:...',
            file_idx: 0,
          },
        ],
        warning: null,
      };
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await apiClient.searchMedia('Breaking Bad');

      expect(fetchMock).toHaveBeenCalledWith('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'Breaking Bad' }),
      });
      expect(result).toEqual(mockResponse);
    });

    it('should handle search error', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ error: 'Invalid query' }),
      });

      await expect(apiClient.searchMedia('invalid')).rejects.toThrow('Invalid query');
    });
  });

  describe('downloadStream', () => {
    it('should send snake_case keys in request body', async () => {
      const mockResponse = {
        job_id: 'job-123',
        status: 'queued',
        message: 'Download started',
      };
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await apiClient.downloadStream('search-123', 0);

      expect(fetchMock).toHaveBeenCalledWith('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_id: 'search-123', stream_index: 0 }),
      });
      expect(result).toEqual(mockResponse);
    });

    it('should return typed response', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: 'job-456',
          status: 'downloading',
          message: 'Download in progress',
        }),
      });

      const result = await apiClient.downloadStream('search-456', 1);

      expect(result.job_id).toBe('job-456');
      expect(result.status).toBe('downloading');
    });
  });

  describe('getJobs', () => {
    it('should unwrap jobs array from envelope', async () => {
      const mockJobs = [
        {
          id: 'job-1',
          query: 'test',
          title: 'Test Title',
          year: 2024,
          imdb_id: null,
          type: 'movie',
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
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ jobs: mockJobs }),
      });

      const result = await apiClient.getJobs();

      expect(fetchMock).toHaveBeenCalledWith('/api/jobs');
      expect(result).toEqual(mockJobs);
      expect(Array.isArray(result)).toBe(true);
    });

    it('should return empty array when no jobs', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ jobs: [] }),
      });

      const result = await apiClient.getJobs();

      expect(result).toEqual([]);
    });
  });

  describe('getLibrary', () => {
    it('should unwrap items array from envelope', async () => {
      const mockItems = [
        {
          title: 'Movie Title',
          year: 2024,
          type: 'movie' as const,
          path: '/path/to/movie',
          folder: 'movie-folder',
          file_count: 1,
          size_bytes: 1073741824,
          poster: 'http://example.com/poster.jpg',
          modified_at: 1711100400,
          storage: 'local',
        },
      ];
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: mockItems, count: 1 }),
      });

      const result = await apiClient.getLibrary();

      expect(fetchMock).toHaveBeenCalledWith('/api/library?force=false');
      expect(result).toEqual(mockItems);
    });

    it('should pass force parameter', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [], count: 0 }),
      });

      await apiClient.getLibrary(true);

      expect(fetchMock).toHaveBeenCalledWith('/api/library?force=true');
    });
  });

  describe('getPosterUrl', () => {
    it('should generate correct URL with encoded path', () => {
      const url = apiClient.getPosterUrl('/path/to/movie');
      expect(url).toBe('/api/library/poster?path=%2Fpath%2Fto%2Fmovie');
    });

    it('should encode special characters in path', () => {
      const url = apiClient.getPosterUrl('/path with spaces/movie & title');
      expect(url).toContain('%20');
      expect(url).toContain('%26');
    });

    it('should start with correct base path', () => {
      const url = apiClient.getPosterUrl('any/path');
      expect(url.startsWith('/api/library/poster?path=')).toBe(true);
    });
  });

  describe('error handling', () => {
    it('should include status code in error', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Not found' }),
      });

      try {
        await apiClient.checkStatus();
      } catch (error) {
        const apiError = error as ApiError;
        expect(apiError.status).toBe(404);
        expect(apiError.message).toBe('Not found');
      }
    });

    it('should handle JSON parse error gracefully', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      try {
        await apiClient.checkStatus();
      } catch (error) {
        const apiError = error as ApiError;
        expect(apiError.status).toBe(500);
        expect(apiError.message).toContain('HTTP 500');
      }
    });

    it('should handle network errors', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'));

      await expect(apiClient.checkStatus()).rejects.toThrow('Network error');
    });

    it('should prioritize detail over error message', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({
          detail: 'Detailed error message',
          error: 'Generic error message',
        }),
      });

      try {
        await apiClient.checkStatus();
      } catch (error) {
        const apiError = error as ApiError;
        expect(apiError.message).toBe('Detailed error message');
      }
    });
  });

  describe('retryJob', () => {
    it('should send POST to retry endpoint', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Job re-queued' }),
      });

      const result = await apiClient.retryJob('job-1');

      expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-1/retry', { method: 'POST' });
      expect(result.message).toBe('Job re-queued');
    });
  });

  describe('getTmdbPoster', () => {
    it('should fetch TMDB poster with required params', async () => {
      const mockResponse = { ok: true, json: async () => ({}) };
      fetchMock.mockResolvedValueOnce(mockResponse);

      const result = await apiClient.getTmdbPoster('Inception', 'Inception (2010)');

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/library/poster/tmdb?')
      );
      const url = fetchMock.mock.calls[0][0] as string;
      expect(url).toContain('title=Inception');
      expect(result).toBe(mockResponse);
    });

    it('should include optional year and type params', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      await apiClient.getTmdbPoster('Breaking Bad', 'bb-folder', 2008, 'tv');

      const url = fetchMock.mock.calls[0][0] as string;
      expect(url).toContain('year=2008');
      expect(url).toContain('type=tv');
    });
  });

  describe('getEpisodes', () => {
    it('should unwrap seasons from envelope', async () => {
      const mockSeasons = [{ season: 1, episodes: [] }];
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ seasons: mockSeasons }),
      });

      const result = await apiClient.getEpisodes('bb-folder');

      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/library/episodes?'));
      expect(result).toEqual(mockSeasons);
    });

    it('should include folder_archive when provided', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ seasons: [] }),
      });

      await apiClient.getEpisodes('bb-folder', '/archive/bb');

      const url = fetchMock.mock.calls[0][0] as string;
      expect(url).toContain('folder_archive=');
    });
  });

  describe('getProgress', () => {
    it('should fetch progress for a given path', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ position_ms: 60000, duration_ms: 120000 }),
      });

      const result = await apiClient.getProgress('/path/to/file.mkv');

      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/progress?path='));
      expect(result).toEqual({ position_ms: 60000, duration_ms: 120000 });
    });
  });

  describe('saveProgress', () => {
    it('should POST progress data', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

      await apiClient.saveProgress('/path/to/file.mkv', 60000, 120000);

      expect(fetchMock).toHaveBeenCalledWith('/api/progress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '/path/to/file.mkv', position_ms: 60000, duration_ms: 120000 }),
      });
    });
  });

  describe('getMpcStatus', () => {
    it('should fetch MPC status', async () => {
      const mockStatus = {
        reachable: true, file: '/path/movie.mkv', filename: 'movie.mkv',
        state: 'playing', is_playing: true, is_paused: false,
        position_ms: 30000, duration_ms: 120000,
        position_str: '0:30', duration_str: '2:00', volume: 75, muted: false,
      };
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => mockStatus });

      const result = await apiClient.getMpcStatus();

      expect(fetchMock).toHaveBeenCalledWith('/api/mpc/status');
      expect(result).toEqual(mockStatus);
    });
  });

  describe('sendMpcCommand', () => {
    it('should send command without position', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) });

      const result = await apiClient.sendMpcCommand(888);

      expect(fetchMock).toHaveBeenCalledWith('/api/mpc/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 888, position_ms: undefined }),
      });
      expect(result).toEqual({ ok: true });
    });

    it('should send command with position', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) });

      await apiClient.sendMpcCommand(889, 60000);

      expect(fetchMock).toHaveBeenCalledWith('/api/mpc/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 889, position_ms: 60000 }),
      });
    });
  });

  describe('openInMpc', () => {
    it('should open file in MPC without playlist', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, launched: true }) });

      const result = await apiClient.openInMpc('/path/movie.mkv');

      expect(fetchMock).toHaveBeenCalledWith('/api/mpc/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '/path/movie.mkv', playlist: undefined }),  // string path → path-based request
      });
      expect(result).toEqual({ ok: true, launched: true });
    });

    it('should open file with playlist', async () => {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, launched: false }) });

      await apiClient.openInMpc('/path/ep1.mkv', undefined, ['/path/ep1.mkv', '/path/ep2.mkv']);

      const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
      expect(body.playlist).toEqual(['/path/ep1.mkv', '/path/ep2.mkv']);
    });
  });

  describe('other API methods', () => {
    it('should get single job', async () => {
      const mockJob = {
        id: 'job-1',
        query: 'test',
        title: null,
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
      };
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockJob,
      });

      const result = await apiClient.getJob('job-1');

      expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-1');
      expect(result).toEqual(mockJob);
    });

    it('should refresh library', async () => {
      const mockResponse = {
        renamed: 5,
        posters_fetched: 10,
        errors: [],
        total_items: 50,
      };
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await apiClient.refreshLibrary();

      expect(fetchMock).toHaveBeenCalledWith('/api/library/refresh', { method: 'POST' });
      expect(result).toEqual(mockResponse);
    });

    it('should delete a job', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Job deleted' }),
      });

      const result = await apiClient.deleteJob('job-42');

      expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-42', { method: 'DELETE' });
      expect(result.message).toBe('Job deleted');
    });

  });
});
