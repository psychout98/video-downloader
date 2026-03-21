// ── Types matching backend response shapes ──────────────────────────────────

export interface ApiError extends Error {
  status?: number;
}

export interface StatusResponse {
  status: string;
  movies_dir: string;
  tv_dir: string;
  anime_dir: string;
  mpc_be_url: string;
}

export interface SearchResponse {
  search_id: string;
  media: MediaMeta;
  streams: StreamOption[];
  warning: string | null;
}

export interface MediaMeta {
  title: string;
  year: number | null;
  imdb_id: string | null;
  tmdb_id: number | null;
  type: string;
  season: number | null;
  episode: number | null;
  is_anime: boolean;
  episode_titles: Record<number, string>;
  overview: string | null;
  poster_path: string | null;
  poster_url: string | null;
}

export interface StreamOption {
  index: number;
  name: string;
  info_hash: string | null;
  download_url: string | null;
  size_bytes: number | null;
  seeders: number;
  is_cached_rd: boolean;
  magnet: string | null;
  file_idx: number | null;
}

export interface Job {
  id: string;
  query: string;
  title: string | null;
  year: number | null;
  imdb_id: string | null;
  type: string | null;
  season: number | null;
  episode: number | null;
  status: string;
  progress: number;
  size_bytes: number | null;
  downloaded_bytes: number;
  quality: string | null;
  torrent_name: string | null;
  rd_torrent_id: string | null;
  file_path: string | null;
  error: string | null;
  log: string;
  stream_data: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryItem {
  title: string;
  year: number | null;
  type: 'movie' | 'tv' | 'anime';
  path: string;
  folder: string;
  folder_archive?: string;
  file_count: number;
  size_bytes: number;
  poster: string | null;
  modified_at: number;
  storage: string;
}

export interface SeasonGroup {
  season: number;
  episodes: EpisodeInfo[];
}

export interface EpisodeInfo {
  season: number;
  episode: number;
  title: string;
  filename: string;
  path: string;
  size_bytes: number;
  progress_pct: number;
  position_ms: number;
  duration_ms: number;
}

export interface MpcStatus {
  reachable: boolean;
  file: string | null;
  filename: string | null;
  state: string;
  is_playing: boolean;
  is_paused: boolean;
  position_ms: number;
  duration_ms: number;
  position_str: string;
  duration_str: string;
  volume: number;
  muted: boolean;
}

export interface Settings {
  [key: string]: string | number | boolean;
}

// ── MPC WM_COMMAND IDs ──────────────────────────────────────────────────────

export const MPC_COMMANDS = {
  PLAY:        887,
  PAUSE:       888,
  STOP:        890,
  SEEK:        889,
  NEXT:        920,
  PREV:        919,
  VOLUME_UP:   907,
  VOLUME_DOWN: 908,
  TOGGLE_MUTE: 909,
} as const;

// ── HTTP helpers ────────────────────────────────────────────────────────────

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error: ApiError = new Error(`HTTP ${response.status}`) as ApiError;
    error.status = response.status;
    try {
      const data = await response.json();
      error.message = data.detail || data.error || error.message;
    } catch {
      // Keep default message
    }
    throw error;
  }
  return response.json();
}

// ── API client ──────────────────────────────────────────────────────────────

export const apiClient = {
  // -- System --
  checkStatus: async (): Promise<StatusResponse> => {
    const response = await fetch('/api/status');
    return handleResponse(response);
  },

  // -- Search & Download --
  searchMedia: async (query: string): Promise<SearchResponse> => {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return handleResponse(response);
  },

  downloadStream: async (searchId: string, streamIndex: number): Promise<{ job_id: string; status: string; message: string }> => {
    const response = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ search_id: searchId, stream_index: streamIndex }),
    });
    return handleResponse(response);
  },

  // -- Jobs --
  getJobs: async (): Promise<Job[]> => {
    const response = await fetch('/api/jobs');
    const data = await handleResponse<{ jobs: Job[] }>(response);
    return data.jobs;
  },

  getJob: async (id: string): Promise<Job> => {
    const response = await fetch(`/api/jobs/${id}`);
    return handleResponse(response);
  },

  deleteJob: async (id: string): Promise<{ message: string }> => {
    const response = await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
    return handleResponse(response);
  },

  retryJob: async (id: string): Promise<{ message: string }> => {
    const response = await fetch(`/api/jobs/${id}/retry`, { method: 'POST' });
    return handleResponse(response);
  },

  // -- Library --
  getLibrary: async (force = false): Promise<LibraryItem[]> => {
    const response = await fetch(`/api/library?force=${force}`);
    const data = await handleResponse<{ items: LibraryItem[]; count: number }>(response);
    return data.items;
  },

  refreshLibrary: async (): Promise<{ renamed: number; posters_fetched: number; errors: string[]; total_items: number }> => {
    const response = await fetch('/api/library/refresh', { method: 'POST' });
    return handleResponse(response);
  },

  getPosterUrl: (path: string): string => {
    return `/api/library/poster?path=${encodeURIComponent(path)}`;
  },

  getTmdbPoster: async (
    title: string,
    folder: string,
    year?: number,
    type?: string
  ): Promise<Response> => {
    const params = new URLSearchParams({ title, folder });
    if (year) params.set('year', year.toString());
    if (type) params.set('type', type);
    return fetch(`/api/library/poster/tmdb?${params}`);
  },

  getEpisodes: async (folder: string, folderArchive?: string): Promise<SeasonGroup[]> => {
    const params = new URLSearchParams({ folder });
    if (folderArchive) params.set('folder_archive', folderArchive);
    const response = await fetch(`/api/library/episodes?${params}`);
    const data = await handleResponse<{ seasons: SeasonGroup[] }>(response);
    return data.seasons;
  },

  // -- Watch Progress --
  getProgress: async (path: string): Promise<{ position_ms?: number; duration_ms?: number }> => {
    const params = new URLSearchParams({ path });
    const response = await fetch(`/api/progress?${params}`);
    return handleResponse(response);
  },

  saveProgress: async (path: string, positionMs: number, durationMs: number): Promise<void> => {
    await fetch('/api/progress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, position_ms: positionMs, duration_ms: durationMs }),
    });
  },

  // -- MPC --
  getMpcStatus: async (): Promise<MpcStatus> => {
    const response = await fetch('/api/mpc/status');
    return handleResponse(response);
  },

  sendMpcCommand: async (command: number, positionMs?: number): Promise<{ ok: boolean }> => {
    const response = await fetch('/api/mpc/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, position_ms: positionMs }),
    });
    return handleResponse(response);
  },

  openInMpc: async (path: string, playlist?: string[]): Promise<{ ok: boolean; launched: boolean }> => {
    const response = await fetch('/api/mpc/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, playlist }),
    });
    return handleResponse(response);
  },

  // -- Settings --
  getSettings: async (): Promise<Settings> => {
    const response = await fetch('/api/settings');
    return handleResponse(response);
  },

  saveSettings: async (updates: Record<string, string | number | boolean>): Promise<{ ok: boolean; written: string[] }> => {
    const response = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates }),
    });
    return handleResponse(response);
  },

  testRdKey: async (): Promise<{ ok: boolean; key_suffix: string; username?: string; error?: string }> => {
    const response = await fetch('/api/settings/test-rd');
    return handleResponse(response);
  },

  // -- Logs --
  getLogs: async (lines = 100): Promise<string[]> => {
    const response = await fetch(`/api/logs?lines=${lines}`);
    const data = await handleResponse<{ lines: string[]; total?: number; note?: string }>(response);
    return data.lines;
  },
};
