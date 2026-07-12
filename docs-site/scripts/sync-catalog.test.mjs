import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateLock } from './sync-catalog.mjs';

test('validateLock accepts a well-formed lock', () => {
  assert.doesNotThrow(() => validateLock({ schema_version: '1', models: [] }));
});

test('validateLock rejects a non-object', () => {
  assert.throws(() => validateLock(null), /expected a JSON object/);
  assert.throws(() => validateLock([]), /expected a JSON object/);
});

test('validateLock rejects an unsupported schema_version', () => {
  assert.throws(
    () => validateLock({ schema_version: '2', models: [] }),
    /unsupported schema_version/,
  );
});

test('validateLock rejects a missing models array', () => {
  assert.throws(() => validateLock({ schema_version: '1' }), /"models" must be an array/);
});
