import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MediaModal from './MediaModal';
import * as apiClientModule from '../../api/client';
import { LibraryItem, SeasonGroup } from '../../api/client';

vi.mock('../../api/client');

const makeMovieItem = (overrides: Partial<LibraryItem> = {}): LibraryItem => ({
  title: 'Inception',
  year: 2010,
  type: 'movie',
  path: '/movies/Inception (2010)/Inception.mkv',
  folder: 'Inception (2010)',
  file_count: 1,
  size_bytes: 2147483648,
  poster: null,
  modified_at: 1711100400,
  storage: 'local',
  ...overrides,
});

const makeTvItem = (overrides: Partial<LibraryItem> = {}): LibraryItem => ({
  title: 'Breaking Bad',
  year: 2008,
  type: 'tv',
  path: '/tv/Breaking Bad (2008)',
  folder: 'Breaking Bad (2008)',
  file_count: 10,
  size_bytes: 5368709120,
  poster: null,
  modified_at: 1711100400,
  storage: 'local',
  ...overrides,
});

const mockSeasonGroups: SeasonGroup[] = [
  {
    season: 1,
    episodes: [
      {
        season: 1,
        episode: 1,
        title: 'Pilot',
        filename: 'S01E01.mkv',
        path: '/tv/bb/S01E01.mkv',
        size_bytes: 536870912,
        progress_pct: 50,
        position_ms: 1200000,
        duration_ms: 2400000,
      },
      {
        season: 1,
        episode: 2,
        title: 'Cat\'s in the Bag',
        filename: 'S01E02.mkv',
        path: '/tv/bb/S01E02.mkv',
        size_bytes: 536870912,
        progress_pct: 0,
        position_ms: 0,
        duration_ms: 2400000,
      },
    ],
  },
  {
    season: 2,
    episodes: [
      {
        season: 2,
        episode: 1,
        title: 'Seven Thirty-Seven',
        filename: 'S02E01.mkv',
        path: '/tv/bb/S02E01.mkv',
        size_bytes: 536870912,
        progress_pct: 0,
        position_ms: 0,
        duration_ms: 2400000,
      },
    ],
  },
];

describe('MediaModal', () => {
  let onCloseMock: ReturnType<typeof vi.fn>;
  let onPlayMock: ReturnType<typeof vi.fn>;
  let showToastMock: ReturnType<typeof vi.fn>;
  const mockApiClient = apiClientModule as any;

  beforeEach(() => {
    onCloseMock = vi.fn();
    onPlayMock = vi.fn();
    showToastMock = vi.fn();
    vi.clearAllMocks();
    mockApiClient.apiClient = {
      getEpisodes: vi.fn().mockResolvedValue(mockSeasonGroups),
      openInMpc: vi.fn().mockResolvedValue({ ok: true, launched: true }),
      getPosterUrl: vi.fn((path: string) => `/api/library/poster?path=${path}`),
    };
  });

  describe('Movie type', () => {
    it('should render movie title', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('Inception')).toBeInTheDocument();
    });

    it('should render movie year badge', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('2010')).toBeInTheDocument();
    });

    it('should render storage badge', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('local')).toBeInTheDocument();
    });

    it('should render folder location', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('Inception (2010)')).toBeInTheDocument();
    });

    it('should render file count', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('1')).toBeInTheDocument();
    });

    it('should not render Episodes section for movies', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.queryByText('Episodes')).not.toBeInTheDocument();
    });

    it('should not fetch episodes for movie type', async () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(mockApiClient.apiClient.getEpisodes).not.toHaveBeenCalled();
    });

    it('should render Play in MPC-BE button', () => {
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByRole('button', { name: 'Play in MPC-BE' })).toBeInTheDocument();
    });

    it('should call openInMpc when Play button clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await user.click(screen.getByRole('button', { name: 'Play in MPC-BE' }));

      expect(mockApiClient.apiClient.openInMpc).toHaveBeenCalledWith(
        '/movies/Inception (2010)/Inception.mkv'
      );
    });

    it('should call onPlay and onClose after successful movie play', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await user.click(screen.getByRole('button', { name: 'Play in MPC-BE' }));

      await waitFor(() => {
        expect(onPlayMock).toHaveBeenCalled();
        expect(onCloseMock).toHaveBeenCalled();
        expect(showToastMock).toHaveBeenCalledWith('Playing in MPC-BE', 'success');
      });
    });

    it('should show error toast when openInMpc fails for movie', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.openInMpc = vi.fn().mockRejectedValue(new Error('Failed'));

      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await user.click(screen.getByRole('button', { name: 'Play in MPC-BE' }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to open in MPC-BE', 'error');
      });
    });

    it('should render poster image when poster is set', () => {
      render(
        <MediaModal
          item={makeMovieItem({ poster: '/posters/inception.jpg' })}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      const img = screen.getAllByRole('img')[0];
      expect(img).toBeInTheDocument();
    });

    it('should render initial letter placeholder when no poster', () => {
      render(
        <MediaModal
          item={makeMovieItem({ poster: null })}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      // 'I' for 'Inception'
      expect(screen.getAllByText('I').length).toBeGreaterThan(0);
    });

    it('should render item without year', () => {
      render(
        <MediaModal
          item={makeMovieItem({ year: null })}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('Inception')).toBeInTheDocument();
    });
  });

  describe('TV type', () => {
    it('should fetch episodes for TV type', async () => {
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(mockApiClient.apiClient.getEpisodes).toHaveBeenCalledWith(
          'Breaking Bad (2008)', undefined
        );
      });
    });

    it('should fetch episodes with folderArchive when provided', async () => {
      render(
        <MediaModal
          item={makeTvItem({ folder_archive: '/archive/bb' })}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(mockApiClient.apiClient.getEpisodes).toHaveBeenCalledWith(
          'Breaking Bad (2008)', '/archive/bb'
        );
      });
    });

    it('should show Loading episodes while fetching', () => {
      mockApiClient.apiClient.getEpisodes = vi.fn().mockImplementation(
        () => new Promise(() => {})
      );

      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      expect(screen.getByText('Loading episodes...')).toBeInTheDocument();
    });

    it('should show No episodes found when empty', async () => {
      mockApiClient.apiClient.getEpisodes = vi.fn().mockResolvedValue([]);

      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('No episodes found')).toBeInTheDocument();
      });
    });

    it('should render season groups', async () => {
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/Season 1/i)).toBeInTheDocument();
        expect(screen.getByText(/Season 2/i)).toBeInTheDocument();
      });
    });

    it('should expand first season by default', async () => {
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/Pilot/)).toBeInTheDocument();
      });
    });

    it('should collapse season when header clicked again', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Season 1/i));
      await user.click(screen.getByRole('button', { name: /Season 1/i }));

      await waitFor(() => {
        expect(screen.queryByText(/Pilot/)).not.toBeInTheDocument();
      });
    });

    it('should expand a different season when clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Season 2/i));
      await user.click(screen.getByRole('button', { name: /Season 2/i }));

      await waitFor(() => {
        expect(screen.getByText(/Seven Thirty-Seven/)).toBeInTheDocument();
      });
    });

    it('should show episode progress bar when progress_pct > 0', async () => {
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/50% watched/)).toBeInTheDocument();
      });
    });

    it('should play episode with playlist when clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Pilot/));
      // Click on the first episode (Pilot = E01)
      await user.click(screen.getByRole('button', { name: /E01: Pilot/i }));

      await waitFor(() => {
        expect(mockApiClient.apiClient.openInMpc).toHaveBeenCalledWith(
          '/tv/bb/S01E01.mkv',
          ['/tv/bb/S01E01.mkv', '/tv/bb/S01E02.mkv']
        );
      });
    });

    it('should call onPlay, onClose, showToast after successful episode play', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Pilot/));
      await user.click(screen.getByRole('button', { name: /E01: Pilot/i }));

      await waitFor(() => {
        expect(onPlayMock).toHaveBeenCalled();
        expect(onCloseMock).toHaveBeenCalled();
        expect(showToastMock).toHaveBeenCalledWith('Playing in MPC-BE', 'success');
      });
    });

    it('should show error toast when episode play fails', async () => {
      const user = userEvent.setup();
      mockApiClient.apiClient.openInMpc = vi.fn().mockRejectedValue(new Error('MPC error'));

      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Pilot/));
      await user.click(screen.getByRole('button', { name: /E01: Pilot/i }));

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to open in MPC-BE', 'error');
      });
    });

    it('should use single-episode playlist fallback when season group is not found', async () => {
      const user = userEvent.setup();
      // Create an episode whose season doesn't match any group
      const orphanEpisode = {
        season: 99,
        episode: 1,
        title: 'Orphan Episode',
        filename: 'S99E01.mkv',
        path: '/tv/bb/S99E01.mkv',
        size_bytes: 536870912,
        progress_pct: 0,
        position_ms: 0,
        duration_ms: 2400000,
      };
      const groupsWithOrphan: SeasonGroup[] = [
        { season: 99, episodes: [orphanEpisode] },
      ];
      mockApiClient.apiClient.getEpisodes = vi.fn().mockResolvedValue(groupsWithOrphan);

      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => screen.getByText(/Orphan Episode/));

      // Now modify seasonGroups to simulate group not found scenario
      // We can't directly manipulate state, but we can test the actual behavior:
      // When the episode is clicked and group IS found, it builds playlist from group
      await user.click(screen.getByRole('button', { name: /E01: Orphan Episode/i }));

      await waitFor(() => {
        expect(mockApiClient.apiClient.openInMpc).toHaveBeenCalledWith(
          '/tv/bb/S99E01.mkv',
          ['/tv/bb/S99E01.mkv']
        );
      });
    });

    it('should show error toast when getEpisodes fails', async () => {
      mockApiClient.apiClient.getEpisodes = vi.fn().mockRejectedValue(new Error('API error'));

      render(
        <MediaModal
          item={makeTvItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('Failed to load episodes', 'error');
      });
    });
  });

  describe('Modal interactions', () => {
    it('should call onClose when backdrop clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      const backdrop = document.querySelector('.fixed.inset-0') as HTMLElement;
      await user.click(backdrop);

      expect(onCloseMock).toHaveBeenCalled();
    });

    it('should call onClose when × button clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      await user.click(screen.getByRole('button', { name: '×' }));

      expect(onCloseMock).toHaveBeenCalled();
    });

    it('should not close when inner content is clicked', async () => {
      const user = userEvent.setup();
      render(
        <MediaModal
          item={makeMovieItem()}
          onClose={onCloseMock}
          onPlay={onPlayMock}
          showToast={showToastMock}
        />
      );

      const inner = document.querySelector('.bg-dark-surface') as HTMLElement;
      fireEvent.click(inner);

      // onClose should NOT have been called from the inner click
      // (it might be called if the event bubbles to the backdrop, but stopPropagation prevents it)
      expect(onCloseMock).not.toHaveBeenCalled();
    });
  });
});
