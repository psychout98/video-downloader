import { useState, useEffect } from 'react';
import { apiClient, Settings } from '../../api/client';

interface Props {
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

function SettingsTab({ showToast }: Props) {
  const [settings, setSettings] = useState<Settings>({});
  const [originalSettings, setOriginalSettings] = useState<Settings>({});
  const [loading, setLoading] = useState(true);
  const [testingRd, setTestingRd] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(true);

  // Load settings
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getSettings();
        setSettings(data);
        setOriginalSettings(data);
      } catch (error) {
        showToast('Failed to load settings', 'error');
        console.error('Settings error:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [showToast]);

  // Load logs
  useEffect(() => {
    const loadLogs = async () => {
      try {
        setLogsLoading(true);
        const data = await apiClient.getLogs(200);
        setLogs(data);
      } catch (error) {
        console.error('Logs error:', error);
      } finally {
        setLogsLoading(false);
      }
    };

    loadLogs();
    const interval = setInterval(loadLogs, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSettingChange = (key: string, value: string | number | boolean) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    try {
      const changes = Object.keys(settings).reduce<Record<string, string | number | boolean>>(
        (acc, key) => {
          if (settings[key] !== originalSettings[key]) {
            acc[key] = settings[key];
          }
          return acc;
        },
        {}
      );

      if (Object.keys(changes).length === 0) {
        showToast('No changes to save', 'info');
        return;
      }

      const result = await apiClient.saveSettings(changes);
      setOriginalSettings(settings);
      showToast(`Settings saved (${result.written.length} keys)`, 'success');
    } catch (error) {
      showToast('Failed to save settings', 'error');
      console.error('Save error:', error);
    }
  };

  const handleTestRd = async () => {
    try {
      setTestingRd(true);
      const result = await apiClient.testRdKey();
      if (result.ok) {
        showToast(`RD key valid — user: ${result.username} (${result.key_suffix})`, 'success');
      } else {
        showToast(`RD key invalid: ${result.error} (${result.key_suffix})`, 'error');
      }
    } catch (error) {
      showToast('Failed to test RD key', 'error');
    } finally {
      setTestingRd(false);
    }
  };

  const isModified = JSON.stringify(settings) !== JSON.stringify(originalSettings);

  // Group settings for display
  const settingGroups: Record<string, string[]> = {
    'API Keys': ['TMDB_API_KEY', 'REAL_DEBRID_API_KEY'],
    'Library Directories': ['MOVIES_DIR', 'TV_DIR', 'ANIME_DIR'],
    'Archive Directories': ['MOVIES_DIR_ARCHIVE', 'TV_DIR_ARCHIVE', 'ANIME_DIR_ARCHIVE'],
    'Other Paths': ['DOWNLOADS_DIR', 'POSTERS_DIR'],
    'MPC-BE': ['MPC_BE_URL', 'MPC_BE_EXE'],
    'Server': ['HOST', 'PORT', 'MAX_CONCURRENT_DOWNLOADS', 'WATCH_THRESHOLD'],
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Settings Form */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-6">Configuration</h2>

        {loading ? (
          <p className="text-dark-text/60">Loading settings...</p>
        ) : Object.keys(settings).length === 0 ? (
          <p className="text-dark-text/60">No settings available</p>
        ) : (
          <>
            {Object.entries(settingGroups).map(([groupName, keys]) => {
              const groupKeys = keys.filter((k) => k in settings);
              if (groupKeys.length === 0) return null;
              return (
                <div key={groupName} className="mb-6">
                  <h3 className="text-sm font-semibold text-dark-accent mb-3">{groupName}</h3>
                  <div className="space-y-3">
                    {groupKeys.map((key) => {
                      const value = settings[key];
                      const isPassword = key.includes('API_KEY') || key.includes('TOKEN');
                      return (
                        <div key={key} className="flex items-center gap-4">
                          <label className="text-sm text-dark-text/80 w-52 flex-shrink-0">
                            {key}
                          </label>
                          <input
                            type={isPassword ? 'password' : 'text'}
                            value={String(value ?? '')}
                            onChange={(e) => handleSettingChange(key, e.target.value)}
                            className="input flex-1"
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {/* Action Buttons */}
            <div className="flex gap-4 pt-6 border-t border-dark-text/10">
              <button
                onClick={handleSave}
                disabled={!isModified}
                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save Settings
              </button>
              <button
                onClick={handleTestRd}
                disabled={testingRd}
                className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testingRd ? 'Testing...' : 'Test RD Key'}
              </button>
              {isModified && (
                <button
                  onClick={() => setSettings(originalSettings)}
                  className="btn-secondary"
                >
                  Discard Changes
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {/* Logs */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Server Logs</h2>
        {logsLoading ? (
          <p className="text-dark-text/60">Loading logs...</p>
        ) : logs.length === 0 ? (
          <p className="text-dark-text/60">No logs available</p>
        ) : (
          <div className="bg-dark-bg rounded p-4 h-96 overflow-y-auto font-mono text-xs text-dark-text/80">
            {logs.map((line, idx) => (
              <div key={idx} className="break-words">
                {line}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SettingsTab;
