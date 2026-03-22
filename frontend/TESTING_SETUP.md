# Vitest + React Testing Library Setup

## Configuration Files

### vitest.config.ts
- Configured with jsdom environment for DOM testing
- Global test utilities enabled
- Test setup file specified at `./src/test/setup.ts`

### src/test/setup.ts
- Imports `@testing-library/jest-dom` for extended matchers

### package.json
Added test scripts:
- `npm test` - Run tests once
- `npm run test:watch` - Watch mode for development

Added devDependencies:
- vitest@^1.0.4
- @testing-library/react@^14.1.2
- @testing-library/jest-dom@^6.1.5
- @testing-library/user-event@^14.5.1
- jsdom@^23.0.1

## Test Files

### 1. src/utils/format.test.ts
Tests for all utility functions:
- `formatSize()` - bytes, KB, MB, GB, TB formatting
- `formatMs()` - milliseconds to time format (M:SS or H:MM:SS)
- `timeAgo()` - relative time strings (just now, Xm/h/d ago, dates)
- `escapeHtml()` - HTML entity escaping for XSS prevention
- `hashColor()` - consistent color generation from strings

### 2. src/api/client.test.ts
Tests for API client methods with fetch mocking:
- **checkStatus()** - Status endpoint, error handling
- **searchMedia()** - Search with JSON payload, typed response
- **downloadStream()** - snake_case key conversion (search_id, stream_index)
- **getJobs()** - Envelope unwrapping ({jobs: [...]})
- **getLibrary()** - Envelope unwrapping ({items: [...]})
- **getLogs()** - Envelope unwrapping ({lines: [...]})
- **getPosterUrl()** - URL encoding for paths
- **Error handling** - Status codes, error messages, JSON parse failures, network errors

### 3. src/components/Queue/QueueTab.test.tsx
Component tests with API mocking:
- **Search UI** - Input rendering, button state (disabled when empty)
- **Search functionality** - Form submission, API calls, warning/error toasts
- **Job list** - Polling, empty states, job rendering
- **Status badges** - Color coding (success=complete, error=failed, info=downloading)
- **Progress bars** - Active job progress display
- **Job actions** - Delete, retry functionality

### 4. src/components/Library/LibraryTab.test.tsx
Component tests with API mocking:
- **Grid rendering** - Library items display, file counts, sizes
- **Filter buttons** - all/movies/tv/anime filtering
- **Search input** - Title filtering (case-insensitive), no results state
- **Refresh button** - API call sequence (refreshLibrary → getLibrary), toasts
- **Empty states** - Empty library vs no search results
- **Error handling** - Failed API calls, error toasts

### 5. src/components/Settings/SettingsTab.test.tsx
Component tests with API mocking:
- **Settings rendering** - Field display from API
- **Save button state** - Disabled when no changes, enabled after edit
- **Field editing** - Change tracking, saving only changed fields
- **Discard changes** - Restore to original values
- **Password fields** - Type="password" for API key fields
- **Test RD Key** - Integration test button, success/error responses
- **Logs section** - Log display, loading states, empty states

## Running Tests

```bash
# Install dependencies
npm install

# Run all tests once
npm test

# Watch mode (rerun on file changes)
npm run test:watch

# Run specific test file
npm test -- src/utils/format.test.ts

# Run tests matching pattern
npm test -- --grep "formatSize"
```

## Test Coverage

All major user flows are covered:
- ✓ Search and download workflow
- ✓ Library browsing with filters
- ✓ Settings management
- ✓ API error handling
- ✓ UI state transitions
- ✓ Form validation

## Mocking Strategy

- **Fetch API** - Mocked globally using `vi.fn()`
- **API Client** - Mocked module using `vi.mock()` in component tests
- **Timers** - Using `vi.useFakeTimers()` for time-dependent tests
- **User Events** - Using `@testing-library/user-event` for realistic interactions
