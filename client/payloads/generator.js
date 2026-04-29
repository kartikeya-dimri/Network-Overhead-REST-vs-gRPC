// generator.js — k6-compatible payload generator
//
// Generates JSON payloads of four structure types (flat, nested, wide, array)
// at a specified target byte size. Used by the k6 sweep scripts.
//
// Usage (from k6 script):
//   import { generatePayload } from '../payloads/generator.js';
//   const body = generatePayload('flat', 1024);  // ~1 KB flat JSON

const CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

/**
 * Generate a random alphanumeric string of the given length.
 */
function randomString(len) {
  let s = '';
  for (let i = 0; i < len; i++) {
    s += CHARSET[Math.floor(Math.random() * CHARSET.length)];
  }
  return s;
}

/**
 * Measure JSON-serialized byte length of an object.
 */
function jsonSize(obj) {
  return JSON.stringify(obj).length;
}

// ---------------------------------------------------------------------------
// Structure generators
// ---------------------------------------------------------------------------

/**
 * Flat: { key_0: "...", key_1: "...", ... }
 * Few keys, each with a long random string value.
 */
function generateFlat(targetBytes) {
  let numKeys = 4;
  let overhead = 2 + numKeys * 12; // braces + key scaffolding
  
  while (overhead >= targetBytes && numKeys > 1) {
    numKeys--;
    overhead = 2 + numKeys * 12;
  }
  
  const valueLen = Math.max(1, Math.floor((targetBytes - overhead) / numKeys));

  const obj = {};
  for (let i = 0; i < numKeys; i++) {
    obj[`key_${i}`] = randomString(valueLen);
  }

  // Fine-tune: trim or pad the last key's value
  return tuneToSize(obj, targetBytes, `key_${numKeys - 1}`);
}

/**
 * Nested: { level_0: { value: "...", child: { value: "...", child: { ... } } } }
 * Deeply nested object to stress recursive traversal.
 */
function generateNested(targetBytes) {
  let depth = 8;
  let overhead = depth * 22;
  
  while (overhead >= targetBytes && depth > 1) {
    depth--;
    overhead = depth * 22;
  }
  
  const valueLen = Math.max(1, Math.floor((targetBytes - overhead) / depth));

  function buildLevel(d) {
    if (d === 0) {
      return { value: randomString(valueLen) };
    }
    return {
      value: randomString(valueLen),
      child: buildLevel(d - 1),
    };
  }

  const obj = buildLevel(depth - 1);

  // Fine-tune by adjusting the top-level 'value' string
  return tuneToSizeNested(obj, targetBytes);
}

/**
 * Wide: { f0: "a", f1: "b", ..., fN: "z" }
 * Many keys with tiny values — maximises per-field overhead.
 */
function generateWide(targetBytes) {
  // Each entry: "fN":"x",  → ~9 chars for small N, grows with digits
  const avgEntrySize = 10;
  let numKeys = Math.max(1, Math.floor(targetBytes / avgEntrySize));

  const obj = {};
  for (let i = 0; i < numKeys; i++) {
    obj[`f${i}`] = randomString(2);
  }

  // Adjust key count to get close to target
  let current = jsonSize(obj);
  while (current < targetBytes - avgEntrySize && numKeys < 100000) {
    obj[`f${numKeys}`] = randomString(2);
    numKeys++;
    current = jsonSize(obj);
  }
  // If overshot, remove last entries
  while (current > targetBytes * 1.05 && numKeys > 1) {
    numKeys--;
    delete obj[`f${numKeys}`];
    current = jsonSize(obj);
  }

  return obj;
}

/**
 * Array: [ { id: 0, val: "..." }, { id: 1, val: "..." }, ... ]
 * Homogeneous array of small objects.
 */
function generateArray(targetBytes) {
  // Each element: {"id":N,"val":"..."},  → ~20 chars + valueLen
  const elemValueLen = 16;
  const elemOverhead = 20;
  const elemSize = elemOverhead + elemValueLen;
  let numElems = Math.max(1, Math.floor(targetBytes / elemSize));

  const arr = [];
  for (let i = 0; i < numElems; i++) {
    arr.push({ id: i, val: randomString(elemValueLen) });
  }

  // Adjust element count
  let current = jsonSize(arr);
  while (current < targetBytes - elemSize && numElems < 100000) {
    arr.push({ id: numElems, val: randomString(elemValueLen) });
    numElems++;
    current = jsonSize(arr);
  }
  while (current > targetBytes * 1.05 && arr.length > 1) {
    arr.pop();
    current = jsonSize(arr);
  }

  return arr;
}

// ---------------------------------------------------------------------------
// Size-tuning helpers
// ---------------------------------------------------------------------------

function tuneToSize(obj, target, lastKey) {
  let current = jsonSize(obj);
  if (current < target) {
    // Pad the last value
    obj[lastKey] += randomString(target - current);
  } else if (current > target) {
    const excess = current - target;
    const val = obj[lastKey];
    obj[lastKey] = val.substring(0, Math.max(1, val.length - excess));
  }
  return obj;
}

function tuneToSizeNested(obj, target) {
  let current = jsonSize(obj);
  const diff = target - current;
  if (diff > 0) {
    obj.value += randomString(diff);
  } else if (diff < 0) {
    const val = obj.value;
    obj.value = val.substring(0, Math.max(1, val.length + diff));
  }
  return obj;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate a JSON-serializable payload of the given structure and approximate
 * byte size (when serialized via JSON.stringify).
 *
 * @param {string} structure  One of: flat, nested, wide, array
 * @param {number} targetBytes  Desired JSON.stringify().length
 * @returns {object|array}
 */
export function generatePayload(structure, targetBytes) {
  switch (structure) {
    case 'flat':
      return generateFlat(targetBytes);
    case 'nested':
      return generateNested(targetBytes);
    case 'wide':
      return generateWide(targetBytes);
    case 'array':
      return generateArray(targetBytes);
    default:
      throw new Error(`unknown structure: ${structure}`);
  }
}
