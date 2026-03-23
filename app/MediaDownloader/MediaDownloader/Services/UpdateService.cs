using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;

namespace MediaDownloader.Services;

public record ReleaseInfo(string TagName, string Name, string AssetUrl, long AssetSize, DateTime PublishedAt);

public record UpdateCheckResult(ReleaseInfo? Release, string? Error);

/// <summary>
/// Checks GitHub Releases for updates and applies them.
/// </summary>
public class UpdateService
{
    private const string DefaultOwner = "psychout98";
    private const string DefaultRepo = "video-downloader";

    private readonly string _installDir;
    private readonly HttpClient _httpClient;

    public string RepoOwner { get; set; } = DefaultOwner;
    public string RepoName { get; set; } = DefaultRepo;

    public string? CurrentVersion => ReadVersionFile();

    public event Action<double>? DownloadProgress;

    public UpdateService(string installDir)
    {
        _installDir = installDir;
        _httpClient = new HttpClient();
        _httpClient.DefaultRequestHeaders.UserAgent.Add(
            new ProductInfoHeaderValue("MediaDownloader", "1.0"));
    }

    public async Task<UpdateCheckResult> CheckForUpdateAsync()
    {
        try
        {
            var url = $"https://api.github.com/repos/{RepoOwner}/{RepoName}/releases/latest";
            var response = await _httpClient.GetAsync(url);

            if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
                return new UpdateCheckResult(null, "No releases published yet.");

            if (response.StatusCode == System.Net.HttpStatusCode.Forbidden ||
                response.StatusCode == System.Net.HttpStatusCode.Unauthorized)
                return new UpdateCheckResult(null, "Repository access denied. Check permissions.");

            if (!response.IsSuccessStatusCode)
                return new UpdateCheckResult(null, $"GitHub returned HTTP {(int)response.StatusCode}.");

            var json = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            var tagName = root.GetProperty("tag_name").GetString() ?? "";
            var name = root.GetProperty("name").GetString() ?? tagName;
            var publishedAt = root.GetProperty("published_at").GetDateTime();

            // Look for the update zip asset
            string? assetUrl = null;
            long assetSize = 0;

            foreach (var asset in root.GetProperty("assets").EnumerateArray())
            {
                var assetName = asset.GetProperty("name").GetString() ?? "";
                if (assetName.Contains("update", StringComparison.OrdinalIgnoreCase) &&
                    assetName.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                {
                    assetUrl = asset.GetProperty("browser_download_url").GetString();
                    assetSize = asset.GetProperty("size").GetInt64();
                    break;
                }
            }

            if (assetUrl == null)
                return new UpdateCheckResult(null, "Release found but no update package attached.");

            var release = new ReleaseInfo(tagName, name, assetUrl, assetSize, publishedAt);
            return new UpdateCheckResult(release, null);
        }
        catch (HttpRequestException)
        {
            return new UpdateCheckResult(null, "Could not reach GitHub. Check your internet connection.");
        }
        catch (TaskCanceledException)
        {
            return new UpdateCheckResult(null, "Request timed out. Check your internet connection.");
        }
        catch (Exception ex)
        {
            return new UpdateCheckResult(null, $"Unexpected error: {ex.Message}");
        }
    }

    public bool IsNewerVersion(ReleaseInfo release)
    {
        var current = CurrentVersion;
        if (string.IsNullOrEmpty(current)) return true;
        return !string.Equals(current, release.TagName, StringComparison.OrdinalIgnoreCase);
    }

    public async Task ApplyUpdateAsync(ReleaseInfo release, ServerManager serverManager)
    {
        var tempZip = Path.Combine(Path.GetTempPath(), $"MediaDownloader-update-{Guid.NewGuid()}.zip");
        var tempExtract = Path.Combine(Path.GetTempPath(), $"MediaDownloader-update-{Guid.NewGuid()}");

        try
        {
            // Download the update zip with progress
            await DownloadWithProgressAsync(release.AssetUrl, tempZip, release.AssetSize);

            // Stop the server before applying
            await serverManager.StopAsync();

            // Extract to temp directory
            ZipFile.ExtractToDirectory(tempZip, tempExtract, overwriteFiles: true);

            // Try direct copy first; if it fails due to permissions, use elevated process
            try
            {
                CopyDirectory(tempExtract, _installDir);
                WriteVersionFile(release.TagName);
            }
            catch (UnauthorizedAccessException)
            {
                ApplyUpdateElevated(tempExtract, _installDir, release.TagName);
            }

            // Check if requirements changed and reinstall
            await UpdatePipDependenciesAsync();

            // Restart server
            await serverManager.StartAsync();
        }
        finally
        {
            // Cleanup temp files
            try { File.Delete(tempZip); } catch { }
            try { if (Directory.Exists(tempExtract)) Directory.Delete(tempExtract, true); } catch { }
        }
    }

    private static void ApplyUpdateElevated(string sourceDir, string installDir, string version)
    {
        // Build a batch script that copies files and writes the version
        var scriptPath = Path.Combine(Path.GetTempPath(), $"MediaDownloader-update-{Guid.NewGuid()}.bat");
        var exeName = "MediaDownloader.exe";

        var script = $"""
            @echo off
            xcopy "{sourceDir}\*" "{installDir}\" /E /Y /I /EXCLUDE:{scriptPath}.exclude
            echo {version}> "{Path.Combine(installDir, ".version")}"
            del "%~f0.exclude" 2>nul
            del "%~f0" 2>nul
            """;

        // Exclude the running exe from being overwritten
        File.WriteAllText(scriptPath + ".exclude", $@"\{exeName}" + Environment.NewLine);
        File.WriteAllText(scriptPath, script);

        var psi = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c \"{scriptPath}\"",
            Verb = "runas",
            UseShellExecute = true,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
        };

        var process = Process.Start(psi)
            ?? throw new InvalidOperationException("Failed to start elevated update process.");
        process.WaitForExit();

        if (process.ExitCode != 0)
            throw new InvalidOperationException($"Elevated update process exited with code {process.ExitCode}.");
    }

    private async Task DownloadWithProgressAsync(string url, string destPath, long totalSize)
    {
        using var response = await _httpClient.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();

        var actualSize = response.Content.Headers.ContentLength ?? totalSize;

        using var stream = await response.Content.ReadAsStreamAsync();
        using var fileStream = new FileStream(destPath, FileMode.Create, FileAccess.Write, FileShare.None, 8192, true);

        var buffer = new byte[8192];
        long totalRead = 0;
        int read;

        while ((read = await stream.ReadAsync(buffer)) > 0)
        {
            await fileStream.WriteAsync(buffer.AsMemory(0, read));
            totalRead += read;
            if (actualSize > 0)
                DownloadProgress?.Invoke((double)totalRead / actualSize);
        }
    }

    private static void CopyDirectory(string source, string destination)
    {
        foreach (var file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            var relativePath = Path.GetRelativePath(source, file);
            var destFile = Path.Combine(destination, relativePath);
            var destDir = Path.GetDirectoryName(destFile)!;

            Directory.CreateDirectory(destDir);

            // Skip overwriting the running exe
            if (destFile.EndsWith("MediaDownloader.exe", StringComparison.OrdinalIgnoreCase))
                continue;

            File.Copy(file, destFile, overwrite: true);
        }
    }

    private async Task UpdatePipDependenciesAsync()
    {
        var requirementsPath = Path.Combine(_installDir, "requirements.txt");
        if (!File.Exists(requirementsPath)) return;

        var venvPip = Path.Combine(_installDir, ".venv", "Scripts", "pip.exe");
        if (!File.Exists(venvPip)) return;

        var psi = new ProcessStartInfo
        {
            FileName = venvPip,
            Arguments = $"install -r \"{requirementsPath}\" --quiet",
            WorkingDirectory = _installDir,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        try
        {
            var process = Process.Start(psi);
            if (process != null)
                await process.WaitForExitAsync();
        }
        catch (Exception)
        {
            // If direct pip fails (e.g. permissions), try elevated
            var elevatedPsi = new ProcessStartInfo
            {
                FileName = venvPip,
                Arguments = $"install -r \"{requirementsPath}\" --quiet",
                WorkingDirectory = _installDir,
                Verb = "runas",
                UseShellExecute = true,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            };

            var elevatedProcess = Process.Start(elevatedPsi);
            if (elevatedProcess != null)
                await elevatedProcess.WaitForExitAsync();
        }
    }

    private string? ReadVersionFile()
    {
        var path = Path.Combine(_installDir, ".version");
        return File.Exists(path) ? File.ReadAllText(path).Trim() : null;
    }

    private void WriteVersionFile(string version)
    {
        File.WriteAllText(Path.Combine(_installDir, ".version"), version);
    }
}
