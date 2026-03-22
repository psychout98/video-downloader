import '@testing-library/jest-dom'

// Mock EventSource (not available in jsdom) — immediately triggers onerror
// so NowPlayingTab falls back to polling, matching existing test expectations.
class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  readyState = MockEventSource.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    // Trigger error asynchronously so the component falls back to polling
    setTimeout(() => {
      this.readyState = MockEventSource.CLOSED;
      this.onerror?.(new Event('error'));
    }, 0);
  }
  addEventListener() {}
  removeEventListener() {}
  close() {
    this.readyState = MockEventSource.CLOSED;
  }
}

(globalThis as any).EventSource = MockEventSource;
