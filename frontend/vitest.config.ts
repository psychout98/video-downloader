import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Use the test tsconfig so test files get the right types
    // (vitest/globals, @testing-library/jest-dom, noUnusedLocals off)
  },
  test: {
    typecheck: {
      tsconfig: './tsconfig.test.json',
    },
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    reporters: ['verbose', ['json', { outputFile: 'test-results.json' }]],
    coverage: {
      provider: 'v8',
      // Files to measure — only our source, not tests or config
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',       // app entry point, no logic to test
        'src/index.css',
      ],
      thresholds: {
        lines: 95,
        functions: 95,
        branches: 95,
        statements: 95,
      },
      reporter: ['text', 'html', 'json-summary'],
    },
  },
})
