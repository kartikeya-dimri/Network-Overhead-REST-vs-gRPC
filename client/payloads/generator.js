// generator.js — k6-compatible structured payload generator
//
// Generates payloads of four structure types at a target LOGICAL byte size.
//
// logical_payload_bytes = sum of all leaf string value lengths (pre-serialization)
//
// ┌───────────┬─────────────────────┬────────────┬──────────────────────┐
// │ Structure │ field_count         │ value_size │ key overhead         │
// ├───────────┼─────────────────────┼────────────┼──────────────────────┤
// │ flat      │ 4 (fixed)           │ target/4   │ minimal (5-char keys)│
// │ wide      │ target/VALUE_SZ     │ 4 (fixed)  │ high (12+ char keys) │
// │ array     │ target/VALUE_SZ     │ 4 (fixed)  │ high (schema repet.) │
// │ nested    │ target/VALUE_SZ     │ 4 (fixed)  │ moderate (braces)    │
// └───────────┴─────────────────────┴────────────┴──────────────────────┘
//
// This ensures:
//   - Flat   → negligible encoding difference (few keys, large values)
//   - Wide   → JSON explodes (many 12+ char keys repeated per field)
//   - Array  → JSON repeats full schema ("idx","val") per element
//   - Nested → JSON adds braces, key names at every branch in the tree
//   - Protobuf avoids most of this overhead via varint field tags
//
// Usage (from k6 script):
//   import { generatePayload, logicalSize } from '../payloads/generator.js';
//   const body = generatePayload('flat', 1024);  // ~1 KB logical data

const CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

// ---------------------------------------------------------------------------
// Structural design parameters — explicitly controlled per structure type.
// These define the (field_count, value_size) tradeoff.
// ---------------------------------------------------------------------------

const FLAT_NUM_KEYS    = 4;     // Few keys → minimal structural overhead
const WIDE_VALUE_SIZE  = 4;     // Small values → amplify key repetition cost
// Wide keys: "field_name_N" → 12+ chars (realistic, not tiny "f0" stubs)
const ARRAY_VALUE_SIZE = 4;     // Small values → amplify schema repetition
// Array elements: { idx: N, val: "xxxx" } — JSON repeats both key names
const NESTED_BRANCHING = 3;     // Children per node (tree, not single-child chain)

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
 * Compute the logical size of a payload: the sum of all leaf string
 * value lengths. This is the raw application data, independent of any
 * serialization format.
 */
function logicalSize(obj) {
  if (typeof obj === 'string') {
    return obj.length;
  }
  if (typeof obj === 'number') {
    return String(obj).length;
  }
  if (Array.isArray(obj)) {
    let total = 0;
    for (let i = 0; i < obj.length; i++) {
      total += logicalSize(obj[i]);
    }
    return total;
  }
  if (obj !== null && typeof obj === 'object') {
    let total = 0;
    for (const key of Object.keys(obj)) {
      total += logicalSize(obj[key]);
    }
    return total;
  }
  return 0;
}

/**
 * Generate a wide-format key name of realistic length (12+ chars).
 * e.g., "field_name_0", "field_name_42", "field_name_999"
 */
function wideKeyName(index) {
  return `field_name_${index}`;
}

// ---------------------------------------------------------------------------
// Structure generators — all target logical bytes, not JSON bytes
// ---------------------------------------------------------------------------

/**
 * Flat: { key_0: "...", key_1: "...", key_2: "...", key_3: "..." }
 *
 * Few keys (4), each with a long random string value.
 * This is the baseline: minimal structural overhead, so JSON and protobuf
 * encode nearly the same amount of data.
 *
 * field_count = 4 (fixed)
 * value_size  = target / 4
 */
function generateFlat(targetLogicalBytes) {
  const numKeys = FLAT_NUM_KEYS;
  const valueLen = Math.max(1, Math.floor(targetLogicalBytes / numKeys));

  const obj = {};
  for (let i = 0; i < numKeys; i++) {
    obj[`key_${i}`] = randomString(valueLen);
  }

  // Fine-tune last key's value to hit exact logical size
  const diff = targetLogicalBytes - logicalSize(obj);
  if (diff > 0) {
    obj[`key_${numKeys - 1}`] += randomString(diff);
  } else if (diff < 0) {
    const lastKey = `key_${numKeys - 1}`;
    obj[lastKey] = obj[lastKey].substring(0, Math.max(1, obj[lastKey].length + diff));
  }
  return obj;
}

/**
 * Nested: branching tree (branching_factor=3)
 *   { value: "...", children: [
 *       { value: "...", children: [...] },
 *       { value: "...", children: [...] },
 *       { value: "...", children: [...] }
 *   ]}
 *
 * Uses branching factor > 1 to represent typical nested data (DOM trees,
 * org charts, config hierarchies). Uses fixed value size (4 chars) and 
 * scales the exact number of nodes to hit the target logical bytes.
 * This guarantees a smooth, linear scaling trend.
 * JSON overhead: braces + "value"/"children" key names at every node.
 *
 * node_count = target / NESTED_VALUE_SIZE (scales linearly)
 * value_size = 4 (fixed)
 */
function generateNested(targetLogicalBytes) {
  const B = NESTED_BRANCHING;
  const valSize = 4; // Use fixed 4-char values to keep structural overhead dominant
  const numNodes = Math.max(1, Math.floor(targetLogicalBytes / valSize));

  const root = { value: randomString(valSize) };
  let createdNodes = 1;
  const queue = [root];

  // Build tree breadth-first with exact node count
  while (createdNodes < numNodes && queue.length > 0) {
    const parent = queue.shift();
    parent.children = [];
    
    for (let i = 0; i < B && createdNodes < numNodes; i++) {
      const child = { value: randomString(valSize) };
      parent.children.push(child);
      queue.push(child);
      createdNodes++;
    }
  }

  // Fine-tune: adjust root's value to hit exact logical size
  const diff = targetLogicalBytes - logicalSize(root);
  if (diff > 0) {
    root.value += randomString(diff);
  } else if (diff < 0) {
    root.value = root.value.substring(0, Math.max(1, root.value.length + diff));
  }
  return root;
}

/**
 * Wide: { field_name_0: "abcd", field_name_1: "efgh", ..., field_name_N: "wxyz" }
 *
 * Many fields with realistic long key names (12+ chars) and small values (4 chars).
 * This maximizes number_of_fields / total_bytes, making JSON key repetition
 * cost the dominant overhead factor.
 *
 * field_count = target / WIDE_VALUE_SIZE (many)
 * value_size  = 4 (fixed)
 * key_size    = 12+ chars ("field_name_N")
 */
function generateWide(targetLogicalBytes) {
  const valSize = WIDE_VALUE_SIZE;
  let numKeys = Math.max(1, Math.floor(targetLogicalBytes / valSize));

  const obj = {};
  for (let i = 0; i < numKeys; i++) {
    obj[wideKeyName(i)] = randomString(valSize);
  }

  // Adjust key count to approach target logical size
  let currentLogical = logicalSize(obj);
  while (currentLogical < targetLogicalBytes && numKeys < 100000) {
    obj[wideKeyName(numKeys)] = randomString(valSize);
    numKeys++;
    currentLogical = logicalSize(obj);
  }
  while (currentLogical > targetLogicalBytes && numKeys > 1) {
    numKeys--;
    delete obj[wideKeyName(numKeys)];
    currentLogical = logicalSize(obj);
  }

  // Final pad/trim on last value
  const lastKey = wideKeyName(numKeys - 1);
  const remaining = targetLogicalBytes - logicalSize(obj);
  if (remaining > 0) {
    obj[lastKey] += randomString(remaining);
  } else if (remaining < 0) {
    const val = obj[lastKey];
    obj[lastKey] = val.substring(0, Math.max(1, val.length + remaining));
  }

  return obj;
}

/**
 * Array: [ { idx: 0, val: "abcd" }, { idx: 1, val: "efgh" }, ... ]
 *
 * Homogeneous array of small objects with fixed element schema.
 * Element size is fixed (small val), element count varies to hit target.
 * JSON repeats both key names ("idx", "val") per element — this schema
 * repetition is the primary overhead.
 *
 * element_count = varies to hit target
 * value_size    = 4 (fixed, keeps schema repetition dominant)
 * per-element logical = String(idx).length + ARRAY_VALUE_SIZE
 */
function generateArray(targetLogicalBytes) {
  const valSize = ARRAY_VALUE_SIZE;
  // Estimate: per-element logical ≈ valSize + avg_idx_digits
  // Start with a conservative estimate
  const estElemLogical = valSize + 2;
  let numElems = Math.max(1, Math.floor(targetLogicalBytes / estElemLogical));

  const arr = [];
  for (let i = 0; i < numElems; i++) {
    arr.push({ idx: i, val: randomString(valSize) });
  }

  // Adjust element count to approach target
  let currentLogical = logicalSize(arr);
  while (currentLogical < targetLogicalBytes - estElemLogical && numElems < 100000) {
    arr.push({ idx: numElems, val: randomString(valSize) });
    numElems++;
    currentLogical = logicalSize(arr);
  }
  while (currentLogical > targetLogicalBytes + estElemLogical && arr.length > 1) {
    arr.pop();
    currentLogical = logicalSize(arr);
  }

  // Fine-tune: pad/trim the last element's 'val' to hit exact logical size
  if (arr.length > 0) {
    const last = arr[arr.length - 1];
    const remaining = targetLogicalBytes - logicalSize(arr);
    if (remaining > 0) {
      last.val += randomString(remaining);
    } else if (remaining < 0) {
      last.val = last.val.substring(0, Math.max(1, last.val.length + remaining));
    }
  }

  return arr;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate a structured payload with the given structure type and target
 * logical byte size.
 *
 * Logical size = sum of all leaf value string lengths (pre-serialization).
 * This is held constant across structures so encoding overhead from JSON
 * (keys, braces, quotes) vs protobuf (field tags, length prefixes) is
 * isolated and observable.
 *
 * Structural parameters (field_count, value_size) are explicitly controlled
 * per structure type — see the parameter table at the top of this file.
 *
 * @param {string} structure  One of: flat, nested, wide, array
 * @param {number} targetLogicalBytes  Desired sum of value string lengths
 * @returns {object|array}
 */
export function generatePayload(structure, targetLogicalBytes) {
  switch (structure) {
    case 'flat':
      return generateFlat(targetLogicalBytes);
    case 'nested':
      return generateNested(targetLogicalBytes);
    case 'wide':
      return generateWide(targetLogicalBytes);
    case 'array':
      return generateArray(targetLogicalBytes);
    default:
      throw new Error(`unknown structure: ${structure}`);
  }
}

/**
 * Compute the logical size of a payload (exported for use by sweep scripts).
 * @param {*} obj  The payload object/array
 * @returns {number}  Sum of all leaf value string lengths
 */
export { logicalSize };
