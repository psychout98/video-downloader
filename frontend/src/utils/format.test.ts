import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { formatSize, formatMs, timeAgo, escapeHtml, hashColor } from './format';

describe('format utilities', () => {
  describe('formatSize', () => {
    it('should format 0 bytes', () => {
      expect(formatSize(0)).toBe('0 B');
    });

    it('should format bytes', () => {
      expect(formatSize(512)).toBe('512 B');
      expect(formatSize(1023)).toBe('1023 B');
    });

    it('should format kilobytes', () => {
      expect(formatSize(1024)).toBe('1 KB');
      expect(formatSize(1536)).toBe('1.5 KB');
      expect(formatSize(2048)).toBe('2 KB');
    });

    it('should format megabytes', () => {
      expect(formatSize(1048576)).toBe('1 MB');
      expect(formatSize(5242880)).toBe('5 MB');
    });

    it('should format gigabytes', () => {
      expect(formatSize(1073741824)).toBe('1 GB');
      expect(formatSize(1610612736)).toBe('1.5 GB');
    });

    it('should format terabytes', () => {
      expect(formatSize(1099511627776)).toBe('1 TB');
      expect(formatSize(1649267441664)).toBe('1.5 TB');
    });
  });

  describe('formatMs', () => {
    it('should handle negative milliseconds', () => {
      expect(formatMs(-1000)).toBe('0:00');
    });

    it('should format seconds only', () => {
      expect(formatMs(0)).toBe('0:00');
      expect(formatMs(5000)).toBe('0:05');
      expect(formatMs(45000)).toBe('0:45');
      expect(formatMs(59999)).toBe('0:59');
    });

    it('should format minutes and seconds', () => {
      expect(formatMs(60000)).toBe('1:00');
      expect(formatMs(90000)).toBe('1:30');
      expect(formatMs(125000)).toBe('2:05');
      expect(formatMs(599999)).toBe('9:59');
    });

    it('should format hours, minutes, and seconds', () => {
      expect(formatMs(3600000)).toBe('1:00:00');
      expect(formatMs(3661000)).toBe('1:01:01');
      expect(formatMs(7265000)).toBe('2:01:05');
      expect(formatMs(36000000)).toBe('10:00:00');
    });

    it('should pad minutes and seconds with leading zeros', () => {
      expect(formatMs(120000)).toBe('2:00');
      expect(formatMs(3605000)).toBe('1:00:05');
      expect(formatMs(3660000)).toBe('1:01:00');
    });
  });

  describe('timeAgo', () => {
    let originalDate: typeof Date;

    beforeEach(() => {
      // Mock the Date constructor to a fixed time for testing
      originalDate = Date;
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-03-22T10:00:00Z').getTime());
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return "just now" for timestamps within 60 seconds', () => {
      const recentTime = new Date('2024-03-22T09:59:30Z').toISOString();
      expect(timeAgo(recentTime)).toBe('just now');
    });

    it('should return minutes ago', () => {
      const tenMinutesAgo = new Date('2024-03-22T09:50:00Z').toISOString();
      expect(timeAgo(tenMinutesAgo)).toBe('10m ago');
    });

    it('should return hours ago', () => {
      const threeHoursAgo = new Date('2024-03-22T07:00:00Z').toISOString();
      expect(timeAgo(threeHoursAgo)).toBe('3h ago');
    });

    it('should return days ago', () => {
      const twoDaysAgo = new Date('2024-03-20T10:00:00Z').toISOString();
      expect(timeAgo(twoDaysAgo)).toBe('2d ago');
    });

    it('should return localized date for older timestamps', () => {
      const oneWeekAgo = new Date('2024-03-15T10:00:00Z').toISOString();
      const result = timeAgo(oneWeekAgo);
      // Check that it's a formatted date string
      expect(result).toMatch(/\d+\/\d+\/\d+/);
    });
  });

  describe('escapeHtml', () => {
    it('should escape ampersands', () => {
      expect(escapeHtml('Fish & Chips')).toBe('Fish &amp; Chips');
    });

    it('should escape less-than signs', () => {
      expect(escapeHtml('1 < 2')).toBe('1 &lt; 2');
    });

    it('should escape greater-than signs', () => {
      expect(escapeHtml('2 > 1')).toBe('2 &gt; 1');
    });

    it('should escape double quotes', () => {
      expect(escapeHtml('He said "hello"')).toBe('He said &quot;hello&quot;');
    });

    it('should escape single quotes', () => {
      expect(escapeHtml("Don't")).toBe('Don&#039;t');
    });

    it('should escape multiple special characters', () => {
      expect(escapeHtml('<script>alert("XSS")</script>')).toBe(
        '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
      );
    });

    it('should handle strings without special characters', () => {
      expect(escapeHtml('Normal text')).toBe('Normal text');
    });

    it('should handle empty strings', () => {
      expect(escapeHtml('')).toBe('');
    });
  });

  describe('hashColor', () => {
    it('should return a valid HSL color', () => {
      const color = hashColor('test');
      expect(color).toMatch(/^hsl\(\d{1,3}, 70%, 45%\)$/);
    });

    it('should return the same color for the same input', () => {
      const color1 = hashColor('consistent');
      const color2 = hashColor('consistent');
      expect(color1).toBe(color2);
    });

    it('should return different colors for different inputs', () => {
      const color1 = hashColor('color1');
      const color2 = hashColor('color2');
      expect(color1).not.toBe(color2);
    });

    it('should extract hue between 0-360', () => {
      const color = hashColor('any string');
      const hueMatch = color.match(/hsl\((\d+)/);
      expect(hueMatch).toBeTruthy();
      const hue = parseInt(hueMatch![1], 10);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    });

    it('should handle empty strings', () => {
      const color = hashColor('');
      expect(color).toMatch(/^hsl\(\d{1,3}, 70%, 45%\)$/);
    });

    it('should handle special characters', () => {
      const color = hashColor('!@#$%^&*()');
      expect(color).toMatch(/^hsl\(\d{1,3}, 70%, 45%\)$/);
    });

    it('should handle unicode strings', () => {
      const color = hashColor('こんにちは');
      expect(color).toMatch(/^hsl\(\d{1,3}, 70%, 45%\)$/);
    });
  });
});

