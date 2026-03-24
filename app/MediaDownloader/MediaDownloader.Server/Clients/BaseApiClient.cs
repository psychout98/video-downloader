using System.Net;
using System.Text.Json;

namespace MediaDownloader.Server.Clients;

/// <summary>
/// Async HTTP client with built-in retry and exponential backoff.
/// Mirrors server/clients/base_client.py.
/// </summary>
public class BaseApiClient : IDisposable
{
    private static readonly HashSet<HttpStatusCode> RetryableStatuses =
    [
        (HttpStatusCode)429,
        HttpStatusCode.InternalServerError,
        HttpStatusCode.BadGateway,
        HttpStatusCode.ServiceUnavailable,
        HttpStatusCode.GatewayTimeout,
        (HttpStatusCode)520, (HttpStatusCode)521, (HttpStatusCode)522, (HttpStatusCode)524,
    ];

    protected readonly HttpClient Http;
    private readonly int _maxRetries;
    private readonly double _backoffBase;
    private readonly string _clientName;
    private readonly ILogger? _logger;

    protected BaseApiClient(
        string? baseUrl = null,
        double timeoutSeconds = 30,
        int maxRetries = 3,
        double backoffBase = 1.0,
        Dictionary<string, string>? headers = null,
        ILogger? logger = null)
    {
        _maxRetries = maxRetries;
        _backoffBase = backoffBase;
        _clientName = GetType().Name;
        _logger = logger;

        var handler = new HttpClientHandler { AllowAutoRedirect = true };
        Http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(timeoutSeconds) };

        if (baseUrl != null)
            Http.BaseAddress = new Uri(baseUrl);
        if (headers != null)
        {
            foreach (var (key, value) in headers)
                Http.DefaultRequestHeaders.TryAddWithoutValidation(key, value);
        }
    }

    public void Dispose() => Http.Dispose();

    protected async Task<HttpResponseMessage> RequestAsync(
        HttpMethod method, string url, HttpContent? content = null,
        bool retry = true, CancellationToken ct = default)
    {
        int maxAttempts = retry ? _maxRetries : 1;
        Exception? lastExc = null;

        for (int attempt = 0; attempt < maxAttempts; attempt++)
        {
            try
            {
                using var request = new HttpRequestMessage(method, url) { Content = content };
                var response = await Http.SendAsync(request, ct);

                if (RetryableStatuses.Contains(response.StatusCode) && attempt < maxAttempts - 1)
                {
                    var delay = _backoffBase * Math.Pow(2, attempt);
                    _logger?.LogInformation(
                        "{Client} {Method} {Url} returned {Status} — retrying in {Delay:F1}s ({Attempt}/{Max})",
                        _clientName, method, url, (int)response.StatusCode, delay, attempt + 1, maxAttempts);
                    await Task.Delay(TimeSpan.FromSeconds(delay), ct);
                    continue;
                }

                response.EnsureSuccessStatusCode();
                return response;
            }
            catch (HttpRequestException ex) when (ex.StatusCode != null)
            {
                throw; // Non-retryable HTTP errors (400, 401, 403, 404)
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or IOException)
            {
                lastExc = ex;
                if (attempt < maxAttempts - 1)
                {
                    var delay = _backoffBase * Math.Pow(2, attempt);
                    _logger?.LogInformation(
                        "{Client} {Method} {Url} failed ({Error}) — retrying in {Delay:F1}s ({Attempt}/{Max})",
                        _clientName, method, url, ex.GetType().Name, delay, attempt + 1, maxAttempts);
                    await Task.Delay(TimeSpan.FromSeconds(delay), ct);
                }
                else
                {
                    _logger?.LogWarning(
                        "{Client} {Method} {Url} failed after {Max} attempts: {Error}",
                        _clientName, method, url, maxAttempts, ex.Message);
                }
            }
        }

        throw lastExc!;
    }

    protected async Task<HttpResponseMessage> GetAsync(string url, CancellationToken ct = default)
        => await RequestAsync(HttpMethod.Get, url, ct: ct);

    protected async Task<HttpResponseMessage> PostAsync(string url, HttpContent? content = null, CancellationToken ct = default)
        => await RequestAsync(HttpMethod.Post, url, content, ct: ct);

    protected async Task<HttpResponseMessage> DeleteAsync(string url, CancellationToken ct = default)
        => await RequestAsync(HttpMethod.Delete, url, ct: ct);

    protected async Task<JsonElement> GetJsonAsync(string url, CancellationToken ct = default)
    {
        var response = await GetAsync(url, ct);
        var json = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<JsonElement>(json);
    }

    protected async Task<JsonElement> PostJsonAsync(string url, HttpContent? content = null, CancellationToken ct = default)
    {
        var response = await PostAsync(url, content, ct);
        var json = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<JsonElement>(json);
    }
}
