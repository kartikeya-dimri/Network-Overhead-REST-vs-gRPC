import { generatePayload, logicalSize } from './client/payloads/generator.js';

for (const size of [512, 1024]) {
  const arr = generatePayload('array', size);
  console.log(`Size: ${size}, logical: ${logicalSize(arr)}, json: ${JSON.stringify(arr).length}, elems: ${arr.length}`);
}
