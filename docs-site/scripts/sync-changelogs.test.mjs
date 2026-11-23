import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseReleases, toPageBody } from './sync-changelogs.mjs';

const SAMPLE = `# Changelog

Intro line.

## [Unreleased]

## [0.2.0] - 2026-11-04

### Added
- Thing.

## v0.1.0 — 2026-10-01

### Fixed
- Other.
`;

test('parseReleases skips Unreleased and reads bracketed and bare versions', () => {
  assert.deepEqual(parseReleases(SAMPLE), [
    { version: '0.2.0', date: '2026-11-04' },
    { version: '0.1.0', date: '2026-10-01' },
  ]);
});

test('toPageBody drops the H1 and empty Unreleased, and keeps versions at H2', () => {
  const body = toPageBody(SAMPLE);
  assert.ok(!body.includes('# Changelog'));
  assert.ok(!/Unreleased/.test(body));
  assert.match(body, /^## \[0\.2\.0\] - 2026-11-04$/m);
  assert.match(body, /^### Added$/m);
});

test('toPageBody keeps an Unreleased section that has content', () => {
  const body = toPageBody('# Changelog\n\n## [Unreleased]\n\n### Added\n- Pending.\n\n## [0.1.0]\n');
  assert.match(body, /^## \[Unreleased\]$/m);
});

test('parseReleases reads release-please headings', () => {
  assert.deepEqual(
    parseReleases('## [0.21.0](https://github.com/x/y/compare/v0.20.0...v0.21.0) (2026-09-28)\n'),
    [{ version: '0.21.0', date: '2026-09-28' }],
  );
});
