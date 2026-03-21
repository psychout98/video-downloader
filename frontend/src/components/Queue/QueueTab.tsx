import { useState, useEffect } from 'react';
import { apiClient, Job, SearchResponse, StreamOption } from '../../api/client';
import { formatSize, timeAgo } from '../../utils/format';

interface Props {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

type JobFilter = 'all' | 'active' | 'done' | 'failed';

function QueueTab({ showToast }: Props) {
  const [query, setQuery] = useState('');
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobFilter, setJobFilter] = useState<JobFilter>('all');
  const [loading, setLoading] = useState(false);

  // Poll for job updates
  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const data = await apiClient.getJobs();
        setJobs(data);
      } catch (error) {
        console.error('Failed to fetch jobs:', error);
      }
    };

    fetchJobs();
    const interval = setInterval(fetchJobs, 3000);
    return () => clearInterval(interval);
  }, []);

  const performSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    try {
      setLoading(true);
      const result = await apiClient.searchMedia(searchQuery);
      setSearchResult(result);
      if (result.warning) {
        showToast(result.warning, 'info');
      }
    } catch (error) {
      showToast('Failed to search media', 'error');
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(query);
  };

  const handleDownload = async (streamIndex: number) => {
    if (!searchResult) return;
    try {
      const result = await apiClient.downloadStream(searchResult.search_id, streamIndex);
      showToast(result.message, 'success');
      const data = await apiClient.getJobs();
      setJobs(data);
    } catch (error) {
      showToast('Failed to start download', 'error');
      console.error('Download error:', error);
    }
  };

  const handleDeleteJob = async (id: string) => {
    try {
      await apiClient.deleteJob(id);
      setJobs((prev) => prev.filter((j) => j.id !== id));
      showToast('Job deleted', 'success');
    } catch (error) {
      showToast('Failed to delete job', 'error');
    }
  };

  const handleRetryJob = async (id: string) => {
    try {
      await apiClient.retryJob(id);
      showToast('Job re-queued', 'success');
      const data = await apiClient.getJobs();
      setJobs(data);
    } catch (error) {
      showToast('Failed to retry job', 'error');
    }
  };

  const isActiveStatus = (status: string) =>
    ['pending', 'downloading', 'searching', 'found', 'adding_to_rd', 'waiting_for_rd', 'organizing'].includes(status);

  const filteredJobs = jobs.filter((job) => {
    if (jobFilter === 'active') return isActiveStatus(job.status);
    if (jobFilter === 'done') return job.status === 'complete';
    if (jobFilter === 'failed') return job.status === 'failed' || job.status === 'cancelled';
    return true;
  });

  const progressPct = (job: Job) => Math.round((job.progress || 0) * 100);

  return (
    <div className="space-y-6">
      {/* Search Section */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Search & Download</h2>
        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for movies, TV shows, or anime... (e.g. Breaking Bad S01E03)"
            className="input flex-1"
          />
          <button
            type="submit"
            disabled={!query.trim() || loading}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </div>

      {/* Search Results */}
      {searchResult && (
        <div className="card">
          <div className="flex items-start gap-4 mb-4">
            {searchResult.media.poster_url && (
              <img
                src={searchResult.media.poster_url}
                alt={searchResult.media.title}
                className="w-24 h-36 rounded object-cover flex-shrink-0"
              />
            )}
            <div>
              <h3 className="text-lg font-semibold">
                {searchResult.media.title}
                {searchResult.media.year && ` (${searchResult.media.year})`}
              </h3>
              <div className="flex gap-2 mt-1">
                <span className="badge badge-accent capitalize">{searchResult.media.type}</span>
                {searchResult.media.imdb_id && (
                  <span className="badge badge-info">{searchResult.media.imdb_id}</span>
                )}
              </div>
              {searchResult.media.overview && (
                <p className="text-sm text-dark-text/70 mt-2 line-clamp-3">
                  {searchResult.media.overview}
                </p>
              )}
            </div>
          </div>

          <h4 className="font-semibold mb-3">
            Available Streams ({searchResult.streams.length})
          </h4>
          <div className="space-y-2">
            {searchResult.streams.map((stream: StreamOption) => (
              <div key={stream.index} className="flex items-center justify-between bg-dark-bg p-3 rounded border border-dark-text/10">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-dark-text truncate">{stream.name}</p>
                  <div className="flex gap-2 mt-1 flex-wrap">
                    {stream.is_cached_rd && (
                      <span className="badge badge-success">RD Cached</span>
                    )}
                    {stream.size_bytes && (
                      <span className="badge badge-accent">{formatSize(stream.size_bytes)}</span>
                    )}
                    {stream.seeders > 0 && (
                      <span className="badge badge-info">{stream.seeders} seeders</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDownload(stream.index)}
                  className="btn-sm-primary ml-4 whitespace-nowrap"
                >
                  Download
                </button>
              </div>
            ))}
            {searchResult.streams.length === 0 && (
              <p className="text-dark-text/60 text-center py-4">No streams found</p>
            )}
          </div>
        </div>
      )}

      {/* Job Queue */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Download Queue</h2>
        </div>

        <div className="flex gap-2 mb-4">
          {(['all', 'active', 'done', 'failed'] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setJobFilter(filter)}
              className={`btn-sm capitalize ${
                jobFilter === filter ? 'btn-sm-primary' : 'btn-sm-secondary'
              }`}
            >
              {filter}
            </button>
          ))}
        </div>

        {filteredJobs.length === 0 ? (
          <p className="text-dark-text/60 text-center py-8">No jobs found</p>
        ) : (
          <div className="space-y-3">
            {filteredJobs.map((job) => (
              <div key={job.id} className="bg-dark-bg p-4 rounded border border-dark-text/10">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-dark-text truncate">{job.title || job.query}</p>
                    {job.torrent_name && (
                      <p className="text-xs text-dark-text/50 truncate">{job.torrent_name}</p>
                    )}
                    <p className="text-xs text-dark-text/60">{timeAgo(job.created_at)}</p>
                  </div>
                  <div className="flex gap-2 ml-4">
                    {isActiveStatus(job.status) ? (
                      <button
                        onClick={() => handleDeleteJob(job.id)}
                        className="btn-sm-secondary text-xs"
                      >
                        Cancel
                      </button>
                    ) : (
                      <>
                        {(job.status === 'failed' || job.status === 'cancelled') && (
                          <button
                            onClick={() => handleRetryJob(job.id)}
                            className="btn-sm-primary text-xs"
                          >
                            Retry
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteJob(job.id)}
                          className="btn-sm-secondary text-xs"
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div className="mb-2">
                  <span className={`badge ${
                    job.status === 'complete' ? 'badge-success' :
                    job.status === 'downloading' ? 'badge-info' :
                    job.status === 'failed' || job.status === 'cancelled' ? 'badge-error' :
                    'badge-accent'
                  }`}>
                    {job.status}
                  </span>
                </div>

                {isActiveStatus(job.status) && (
                  <>
                    <div className="progress-bar mb-1">
                      <div className="progress-fill" style={{ width: `${progressPct(job)}%` }} />
                    </div>
                    <div className="text-xs text-dark-text/60">
                      {progressPct(job)}%
                      {job.downloaded_bytes > 0 && job.size_bytes && (
                        <> ({formatSize(job.downloaded_bytes)} / {formatSize(job.size_bytes)})</>
                      )}
                    </div>
                  </>
                )}

                {job.error && (
                  <p className="text-xs text-error mt-2">{job.error}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default QueueTab;
