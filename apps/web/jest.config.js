// Jest configuration for the Replica AI web app.
//
// We use next/jest to inherit Next.js's Babel/SWC + path-alias setup, then
// layer on jsdom + React Testing Library. Component tests live in
// `__tests__/`. End-to-end tests live in `e2e/` and are run by Playwright,
// not Jest — Jest's testPathIgnorePatterns excludes them below.

const nextJest = require('next/jest');

const createJestConfig = nextJest({
  // Path to Next.js root so next/jest can load next.config.js + .env files
  dir: './',
});

/** @type {import('jest').Config} */
const customJestConfig = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@replica-ai/shared$': '<rootDir>/../../packages/shared/src/index.ts',
  },
  testPathIgnorePatterns: [
    '<rootDir>/.next/',
    '<rootDir>/node_modules/',
    '<rootDir>/e2e/',
  ],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/app/**/layout.tsx',
    '!src/app/**/page.tsx',
  ],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 60,
      lines: 60,
      statements: 60,
    },
  },
};

module.exports = createJestConfig(customJestConfig);
