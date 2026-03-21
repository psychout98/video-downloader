import { useState, useEffect } from 'react';
import { apiClient } from './api/client';
import QueueTab from './components/Queue/QueueTab';
import LibraryTab from './components/Library/LibraryTab';
import NowPlayingTab from './components/NowPlaying/NowPlayingTab';
import SettingsTab from './components/Settings/SettingsTab';

type TabType = 'queue' | 'library' | 'playing' | 'settings';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('queue');
  const [connected, setConnected] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Check server status
  useEffect(() => {
    const checkStatus = async () => {
      try {
        await apiClient.checkStatus();
        setConnected(true);
      } catch {
        setConnected(false);
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = Date.now().toString();
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  };

  return (
    <div className="min-h-screen bg-dark-bg flex flex-col">
      {/* Header */}
      <header className="bg-dark-surface border-b border-dark-text/10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-dark-accent">Media Downloader</h1>
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full transition-colors ${
                  connected ? 'bg-success' : 'bg-error'
                }`}
              />
              <span className="text-xs text-dark-text/60">
                {connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="bg-dark-surface border-b border-dark-text/10 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 flex">
          <button
            onClick={() => setActiveTab('queue')}
            className={
              activeTab === 'queue'
                ? 'tab-button-active text-dark-accent border-b-2 border-dark-accent px-4 py-3'
                : 'tab-button-inactive text-dark-text/60 hover:text-dark-text px-4 py-3'
            }
          >
            Queue
          </button>
          <button
            onClick={() => setActiveTab('library')}
            className={
              activeTab === 'library'
                ? 'tab-button-active text-dark-accent border-b-2 border-dark-accent px-4 py-3'
                : 'tab-button-inactive text-dark-text/60 hover:text-dark-text px-4 py-3'
            }
          >
            Library
          </button>
          <button
            onClick={() => setActiveTab('playing')}
            className={
              activeTab === 'playing'
                ? 'tab-button-active text-dark-accent border-b-2 border-dark-accent px-4 py-3'
                : 'tab-button-inactive text-dark-text/60 hover:text-dark-text px-4 py-3'
            }
          >
            Now Playing
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={
              activeTab === 'settings'
                ? 'tab-button-active text-dark-accent border-b-2 border-dark-accent px-4 py-3'
                : 'tab-button-inactive text-dark-text/60 hover:text-dark-text px-4 py-3'
            }
          >
            Settings
          </button>
        </div>
      </nav>

      {/* Tab Content */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-4 py-6">
          {activeTab === 'queue' && <QueueTab showToast={showToast} />}
          {activeTab === 'library' && <LibraryTab showToast={showToast} onPlay={() => setActiveTab('playing')} />}
          {activeTab === 'playing' && <NowPlayingTab showToast={showToast} />}
          {activeTab === 'settings' && <SettingsTab showToast={showToast} />}
        </div>
      </main>

      {/* Toast Notifications */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type}`}>
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
