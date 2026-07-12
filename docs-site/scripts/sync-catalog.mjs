import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SUPPORTED_SCHEMA_VERSIONS = new Set(['1']);

/** Throws if `obj` is not a lock we can vendor. Dependency-free (no JSON Schema lib). */
export function validateLock(obj) {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    throw new Error('Invalid lock: expected a JSON object');
  }
  if (!SUPPORTED_SCHEMA_VERSIONS.has(String(obj.schema_version))) {
    throw new Error(
      `Invalid lock: unsupported schema_version ${obj.schema_version} ` +
        `(supported: ${[...SUPPORTED_SCHEMA_VERSIONS].join(', ')})`,
    );
  }
  if (!Array.isArray(obj.models)) {
    throw new Error('Invalid lock: "models" must be an array');
  }
}

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCS_SITE = join(HERE, '..'); // docs-site/
const ASTROMESH_ROOT = join(DOCS_SITE, '..'); // astromesh/
const DEFAULT_SOURCE = resolve(
  ASTROMESH_ROOT,
  '..',
  'astromesh-nebula',
  'nebula',
  'catalog.lock.json',
);
const DEST = join(DOCS_SITE, 'src', 'data', 'catalog.lock.json');

/** Copy + validate the nebula lock into the vendored docs location. */
export function sync({ source = DEFAULT_SOURCE, dest = DEST } = {}) {
  if (!existsSync(source)) {
    throw new Error(
      `Catalog lock not found at ${source}. Check out astromesh-nebula next to astromesh, ` +
        `or pass an explicit path: node scripts/sync-catalog.mjs <path-to-catalog.lock.json>`,
    );
  }
  const raw = readFileSync(source, 'utf8');
  let obj;
  try {
    obj = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Catalog lock at ${source} is not valid JSON: ${err.message}`);
  }
  validateLock(obj);
  writeFileSync(dest, `${JSON.stringify(obj, null, 2)}\n`);
  return { source, dest, models: obj.models.length };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const override = process.argv[2];
  const { source, dest, models } = sync(override ? { source: resolve(override) } : {});
  console.log(`sync-catalog: copied ${models} model(s) from ${source} -> ${dest}`);
}
