var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __esm = (fn, res, err) => function __init() {
  if (err) throw err[0];
  try {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  } catch (e) {
    throw err = [e], e;
  }
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// src/store/atomic.ts
import { promises as fs2 } from "node:fs";
import { randomUUID } from "node:crypto";
async function withLock(key, fn) {
  const prev = locks.get(key) ?? Promise.resolve();
  let release;
  const next = new Promise((r) => release = r);
  locks.set(key, prev.then(() => next));
  await prev;
  try {
    return await fn();
  } finally {
    release();
    if (locks.get(key) === next) locks.delete(key);
  }
}
async function atomicWriteFile(path, content) {
  const tmp = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await fs2.writeFile(tmp, content, "utf8");
  await fs2.rename(tmp, path);
}
async function atomicWriteJSON(path, data) {
  await atomicWriteFile(path, JSON.stringify(data, null, 2));
}
async function readJSONTolerant(path) {
  try {
    const raw = await fs2.readFile(path, "utf8");
    return { ok: true, data: JSON.parse(raw) };
  } catch (e) {
    if (e.code === "ENOENT") return { ok: false, error: "not-found" };
    return { ok: false, error: `corrupt: ${e.message}` };
  }
}
async function fileExists(path) {
  try {
    await fs2.access(path);
    return true;
  } catch {
    return false;
  }
}
var locks;
var init_atomic = __esm({
  "src/store/atomic.ts"() {
    "use strict";
    locks = /* @__PURE__ */ new Map();
  }
});

// src/store/test.ts
var test_exports = {};
__export(test_exports, {
  buildDefaultRegressionScripts: () => buildDefaultRegressionScripts,
  readRegressionIndex: () => readRegressionIndex,
  regressionDirFor: () => regressionDirFor,
  upsertRegressionIndex: () => upsertRegressionIndex,
  writeRegressionScripts: () => writeRegressionScripts,
  writeTestReport: () => writeTestReport
});
import { join as join4 } from "node:path";
import { promises as fs4 } from "node:fs";
function regressionDirFor(layout, taskId) {
  return join4(layout.projectRoot, "tests", "regression", taskId);
}
async function writeRegressionScripts(layout, taskId, scripts) {
  const written = [];
  for (const sc of scripts ?? []) {
    const target = join4(layout.projectRoot, sc.path);
    await fs4.mkdir(join4(target, ".."), { recursive: true });
    await atomicWriteFile(target, sc.content);
    written.push(sc.path);
  }
  return written;
}
async function writeTestReport(layout, taskId, report) {
  await fs4.mkdir(layout.reports, { recursive: true });
  const id = taskId.startsWith("T-") ? taskId : `T-${taskId}`;
  const p = join4(layout.reports, `${id}_report.json`);
  await atomicWriteJSON(p, report);
  return p;
}
async function upsertRegressionIndex(layout, entry) {
  await withLock(join4(layout.regression, INDEX_NAME), async () => {
    await fs4.mkdir(layout.regression, { recursive: true });
    const prev = (await readJSONTolerant(join4(layout.regression, INDEX_NAME))).data;
    const st = (await readJSONTolerant(layout.state)).data ?? {};
    const tasks = [...(prev?.tasks ?? []).filter((t) => t.task_id !== entry.task_id), entry];
    const next = {
      module: st.module ?? "module",
      updated_at: (/* @__PURE__ */ new Date()).toISOString(),
      tasks
    };
    await atomicWriteJSON(join4(layout.regression, INDEX_NAME), next);
  });
}
async function readRegressionIndex(layout) {
  const r = await readJSONTolerant(join4(layout.regression, INDEX_NAME));
  return r.ok ? r.data : null;
}
function buildDefaultRegressionScripts(taskId, report) {
  const cases = Array.isArray(report?.cases) ? report.cases : [];
  return cases.filter((c) => c?.case_id).map((c) => ({
    path: `tests/regression/${taskId}/${c.case_id}.sh`,
    content: `#!/usr/bin/env bash
# ${c.case_id} ${c.fr_ref ?? ""} ${c.description ?? ""}
# expected: ${c.expected_behavior ?? ""}
# verify_command: ${c.verify_command ?? ""}
# \u672C\u811A\u672C\u7531 ar-flow P3 \u673A\u68B0\u751F\u6210\uFF0C\u4F9B\u5168\u91CF\u56DE\u5F52\u590D\u7528\uFF1B\u5982\u542B\u81EA\u5B9A\u4E49\u65AD\u8A00\u8BF7\u4EE5\u5B9E\u9645\u547D\u4EE4\u4E3A\u51C6\u3002
`
  }));
}
var INDEX_NAME;
var init_test = __esm({
  "src/store/test.ts"() {
    "use strict";
    init_atomic();
    INDEX_NAME = "index.json";
  }
});

// node_modules/zod/v4/classic/external.js
var external_exports = {};
__export(external_exports, {
  $brand: () => $brand,
  $input: () => $input,
  $output: () => $output,
  NEVER: () => NEVER,
  TimePrecision: () => TimePrecision,
  ZodAny: () => ZodAny,
  ZodArray: () => ZodArray,
  ZodBase64: () => ZodBase64,
  ZodBase64URL: () => ZodBase64URL,
  ZodBigInt: () => ZodBigInt,
  ZodBigIntFormat: () => ZodBigIntFormat,
  ZodBoolean: () => ZodBoolean,
  ZodCIDRv4: () => ZodCIDRv4,
  ZodCIDRv6: () => ZodCIDRv6,
  ZodCUID: () => ZodCUID,
  ZodCUID2: () => ZodCUID2,
  ZodCatch: () => ZodCatch,
  ZodCodec: () => ZodCodec,
  ZodCustom: () => ZodCustom,
  ZodCustomStringFormat: () => ZodCustomStringFormat,
  ZodDate: () => ZodDate,
  ZodDefault: () => ZodDefault,
  ZodDiscriminatedUnion: () => ZodDiscriminatedUnion,
  ZodE164: () => ZodE164,
  ZodEmail: () => ZodEmail,
  ZodEmoji: () => ZodEmoji,
  ZodEnum: () => ZodEnum,
  ZodError: () => ZodError,
  ZodExactOptional: () => ZodExactOptional,
  ZodFile: () => ZodFile,
  ZodFirstPartyTypeKind: () => ZodFirstPartyTypeKind,
  ZodFunction: () => ZodFunction,
  ZodGUID: () => ZodGUID,
  ZodIPv4: () => ZodIPv4,
  ZodIPv6: () => ZodIPv6,
  ZodISODate: () => ZodISODate,
  ZodISODateTime: () => ZodISODateTime,
  ZodISODuration: () => ZodISODuration,
  ZodISOTime: () => ZodISOTime,
  ZodIntersection: () => ZodIntersection,
  ZodIssueCode: () => ZodIssueCode,
  ZodJWT: () => ZodJWT,
  ZodKSUID: () => ZodKSUID,
  ZodLazy: () => ZodLazy,
  ZodLiteral: () => ZodLiteral,
  ZodMAC: () => ZodMAC,
  ZodMap: () => ZodMap,
  ZodNaN: () => ZodNaN,
  ZodNanoID: () => ZodNanoID,
  ZodNever: () => ZodNever,
  ZodNonOptional: () => ZodNonOptional,
  ZodNull: () => ZodNull,
  ZodNullable: () => ZodNullable,
  ZodNumber: () => ZodNumber,
  ZodNumberFormat: () => ZodNumberFormat,
  ZodObject: () => ZodObject,
  ZodOptional: () => ZodOptional,
  ZodPipe: () => ZodPipe,
  ZodPrefault: () => ZodPrefault,
  ZodPreprocess: () => ZodPreprocess,
  ZodPromise: () => ZodPromise,
  ZodReadonly: () => ZodReadonly,
  ZodRealError: () => ZodRealError,
  ZodRecord: () => ZodRecord,
  ZodSet: () => ZodSet,
  ZodString: () => ZodString,
  ZodStringFormat: () => ZodStringFormat,
  ZodSuccess: () => ZodSuccess,
  ZodSymbol: () => ZodSymbol,
  ZodTemplateLiteral: () => ZodTemplateLiteral,
  ZodTransform: () => ZodTransform,
  ZodTuple: () => ZodTuple,
  ZodType: () => ZodType,
  ZodULID: () => ZodULID,
  ZodURL: () => ZodURL,
  ZodUUID: () => ZodUUID,
  ZodUndefined: () => ZodUndefined,
  ZodUnion: () => ZodUnion,
  ZodUnknown: () => ZodUnknown,
  ZodVoid: () => ZodVoid,
  ZodXID: () => ZodXID,
  ZodXor: () => ZodXor,
  _ZodString: () => _ZodString,
  _default: () => _default2,
  _function: () => _function,
  any: () => any,
  array: () => array,
  base64: () => base642,
  base64url: () => base64url2,
  bigint: () => bigint2,
  boolean: () => boolean2,
  catch: () => _catch2,
  check: () => check,
  cidrv4: () => cidrv42,
  cidrv6: () => cidrv62,
  clone: () => clone,
  codec: () => codec,
  coerce: () => coerce_exports,
  config: () => config,
  core: () => core_exports2,
  cuid: () => cuid3,
  cuid2: () => cuid22,
  custom: () => custom,
  date: () => date3,
  decode: () => decode2,
  decodeAsync: () => decodeAsync2,
  describe: () => describe2,
  discriminatedUnion: () => discriminatedUnion,
  e164: () => e1642,
  email: () => email2,
  emoji: () => emoji2,
  encode: () => encode2,
  encodeAsync: () => encodeAsync2,
  endsWith: () => _endsWith,
  enum: () => _enum2,
  exactOptional: () => exactOptional,
  file: () => file,
  flattenError: () => flattenError,
  float32: () => float32,
  float64: () => float64,
  formatError: () => formatError,
  fromJSONSchema: () => fromJSONSchema,
  function: () => _function,
  getErrorMap: () => getErrorMap,
  globalRegistry: () => globalRegistry,
  gt: () => _gt,
  gte: () => _gte,
  guid: () => guid2,
  hash: () => hash,
  hex: () => hex2,
  hostname: () => hostname2,
  httpUrl: () => httpUrl,
  includes: () => _includes,
  instanceof: () => _instanceof,
  int: () => int,
  int32: () => int32,
  int64: () => int64,
  intersection: () => intersection,
  invertCodec: () => invertCodec,
  ipv4: () => ipv42,
  ipv6: () => ipv62,
  iso: () => iso_exports,
  json: () => json,
  jwt: () => jwt,
  keyof: () => keyof,
  ksuid: () => ksuid2,
  lazy: () => lazy,
  length: () => _length,
  literal: () => literal,
  locales: () => locales_exports,
  looseObject: () => looseObject,
  looseRecord: () => looseRecord,
  lowercase: () => _lowercase,
  lt: () => _lt,
  lte: () => _lte,
  mac: () => mac2,
  map: () => map,
  maxLength: () => _maxLength,
  maxSize: () => _maxSize,
  meta: () => meta2,
  mime: () => _mime,
  minLength: () => _minLength,
  minSize: () => _minSize,
  multipleOf: () => _multipleOf,
  nan: () => nan,
  nanoid: () => nanoid2,
  nativeEnum: () => nativeEnum,
  negative: () => _negative,
  never: () => never,
  nonnegative: () => _nonnegative,
  nonoptional: () => nonoptional,
  nonpositive: () => _nonpositive,
  normalize: () => _normalize,
  null: () => _null3,
  nullable: () => nullable,
  nullish: () => nullish2,
  number: () => number2,
  object: () => object,
  optional: () => optional,
  overwrite: () => _overwrite,
  parse: () => parse2,
  parseAsync: () => parseAsync2,
  partialRecord: () => partialRecord,
  pipe: () => pipe,
  positive: () => _positive,
  prefault: () => prefault,
  preprocess: () => preprocess,
  prettifyError: () => prettifyError,
  promise: () => promise,
  property: () => _property,
  readonly: () => readonly,
  record: () => record,
  refine: () => refine,
  regex: () => _regex,
  regexes: () => regexes_exports,
  registry: () => registry,
  safeDecode: () => safeDecode2,
  safeDecodeAsync: () => safeDecodeAsync2,
  safeEncode: () => safeEncode2,
  safeEncodeAsync: () => safeEncodeAsync2,
  safeParse: () => safeParse2,
  safeParseAsync: () => safeParseAsync2,
  set: () => set,
  setErrorMap: () => setErrorMap,
  size: () => _size,
  slugify: () => _slugify,
  startsWith: () => _startsWith,
  strictObject: () => strictObject,
  string: () => string2,
  stringFormat: () => stringFormat,
  stringbool: () => stringbool,
  success: () => success,
  superRefine: () => superRefine,
  symbol: () => symbol,
  templateLiteral: () => templateLiteral,
  toJSONSchema: () => toJSONSchema,
  toLowerCase: () => _toLowerCase,
  toUpperCase: () => _toUpperCase,
  transform: () => transform,
  treeifyError: () => treeifyError,
  trim: () => _trim,
  tuple: () => tuple,
  uint32: () => uint32,
  uint64: () => uint64,
  ulid: () => ulid2,
  undefined: () => _undefined3,
  union: () => union,
  unknown: () => unknown,
  uppercase: () => _uppercase,
  url: () => url,
  util: () => util_exports,
  uuid: () => uuid2,
  uuidv4: () => uuidv4,
  uuidv6: () => uuidv6,
  uuidv7: () => uuidv7,
  void: () => _void2,
  xid: () => xid2,
  xor: () => xor
});

// node_modules/zod/v4/core/index.js
var core_exports2 = {};
__export(core_exports2, {
  $ZodAny: () => $ZodAny,
  $ZodArray: () => $ZodArray,
  $ZodAsyncError: () => $ZodAsyncError,
  $ZodBase64: () => $ZodBase64,
  $ZodBase64URL: () => $ZodBase64URL,
  $ZodBigInt: () => $ZodBigInt,
  $ZodBigIntFormat: () => $ZodBigIntFormat,
  $ZodBoolean: () => $ZodBoolean,
  $ZodCIDRv4: () => $ZodCIDRv4,
  $ZodCIDRv6: () => $ZodCIDRv6,
  $ZodCUID: () => $ZodCUID,
  $ZodCUID2: () => $ZodCUID2,
  $ZodCatch: () => $ZodCatch,
  $ZodCheck: () => $ZodCheck,
  $ZodCheckBigIntFormat: () => $ZodCheckBigIntFormat,
  $ZodCheckEndsWith: () => $ZodCheckEndsWith,
  $ZodCheckGreaterThan: () => $ZodCheckGreaterThan,
  $ZodCheckIncludes: () => $ZodCheckIncludes,
  $ZodCheckLengthEquals: () => $ZodCheckLengthEquals,
  $ZodCheckLessThan: () => $ZodCheckLessThan,
  $ZodCheckLowerCase: () => $ZodCheckLowerCase,
  $ZodCheckMaxLength: () => $ZodCheckMaxLength,
  $ZodCheckMaxSize: () => $ZodCheckMaxSize,
  $ZodCheckMimeType: () => $ZodCheckMimeType,
  $ZodCheckMinLength: () => $ZodCheckMinLength,
  $ZodCheckMinSize: () => $ZodCheckMinSize,
  $ZodCheckMultipleOf: () => $ZodCheckMultipleOf,
  $ZodCheckNumberFormat: () => $ZodCheckNumberFormat,
  $ZodCheckOverwrite: () => $ZodCheckOverwrite,
  $ZodCheckProperty: () => $ZodCheckProperty,
  $ZodCheckRegex: () => $ZodCheckRegex,
  $ZodCheckSizeEquals: () => $ZodCheckSizeEquals,
  $ZodCheckStartsWith: () => $ZodCheckStartsWith,
  $ZodCheckStringFormat: () => $ZodCheckStringFormat,
  $ZodCheckUpperCase: () => $ZodCheckUpperCase,
  $ZodCodec: () => $ZodCodec,
  $ZodCustom: () => $ZodCustom,
  $ZodCustomStringFormat: () => $ZodCustomStringFormat,
  $ZodDate: () => $ZodDate,
  $ZodDefault: () => $ZodDefault,
  $ZodDiscriminatedUnion: () => $ZodDiscriminatedUnion,
  $ZodE164: () => $ZodE164,
  $ZodEmail: () => $ZodEmail,
  $ZodEmoji: () => $ZodEmoji,
  $ZodEncodeError: () => $ZodEncodeError,
  $ZodEnum: () => $ZodEnum,
  $ZodError: () => $ZodError,
  $ZodExactOptional: () => $ZodExactOptional,
  $ZodFile: () => $ZodFile,
  $ZodFunction: () => $ZodFunction,
  $ZodGUID: () => $ZodGUID,
  $ZodIPv4: () => $ZodIPv4,
  $ZodIPv6: () => $ZodIPv6,
  $ZodISODate: () => $ZodISODate,
  $ZodISODateTime: () => $ZodISODateTime,
  $ZodISODuration: () => $ZodISODuration,
  $ZodISOTime: () => $ZodISOTime,
  $ZodIntersection: () => $ZodIntersection,
  $ZodJWT: () => $ZodJWT,
  $ZodKSUID: () => $ZodKSUID,
  $ZodLazy: () => $ZodLazy,
  $ZodLiteral: () => $ZodLiteral,
  $ZodMAC: () => $ZodMAC,
  $ZodMap: () => $ZodMap,
  $ZodNaN: () => $ZodNaN,
  $ZodNanoID: () => $ZodNanoID,
  $ZodNever: () => $ZodNever,
  $ZodNonOptional: () => $ZodNonOptional,
  $ZodNull: () => $ZodNull,
  $ZodNullable: () => $ZodNullable,
  $ZodNumber: () => $ZodNumber,
  $ZodNumberFormat: () => $ZodNumberFormat,
  $ZodObject: () => $ZodObject,
  $ZodObjectJIT: () => $ZodObjectJIT,
  $ZodOptional: () => $ZodOptional,
  $ZodPipe: () => $ZodPipe,
  $ZodPrefault: () => $ZodPrefault,
  $ZodPreprocess: () => $ZodPreprocess,
  $ZodPromise: () => $ZodPromise,
  $ZodReadonly: () => $ZodReadonly,
  $ZodRealError: () => $ZodRealError,
  $ZodRecord: () => $ZodRecord,
  $ZodRegistry: () => $ZodRegistry,
  $ZodSet: () => $ZodSet,
  $ZodString: () => $ZodString,
  $ZodStringFormat: () => $ZodStringFormat,
  $ZodSuccess: () => $ZodSuccess,
  $ZodSymbol: () => $ZodSymbol,
  $ZodTemplateLiteral: () => $ZodTemplateLiteral,
  $ZodTransform: () => $ZodTransform,
  $ZodTuple: () => $ZodTuple,
  $ZodType: () => $ZodType,
  $ZodULID: () => $ZodULID,
  $ZodURL: () => $ZodURL,
  $ZodUUID: () => $ZodUUID,
  $ZodUndefined: () => $ZodUndefined,
  $ZodUnion: () => $ZodUnion,
  $ZodUnknown: () => $ZodUnknown,
  $ZodVoid: () => $ZodVoid,
  $ZodXID: () => $ZodXID,
  $ZodXor: () => $ZodXor,
  $brand: () => $brand,
  $constructor: () => $constructor,
  $input: () => $input,
  $output: () => $output,
  Doc: () => Doc,
  JSONSchema: () => json_schema_exports,
  JSONSchemaGenerator: () => JSONSchemaGenerator,
  NEVER: () => NEVER,
  TimePrecision: () => TimePrecision,
  _any: () => _any,
  _array: () => _array,
  _base64: () => _base64,
  _base64url: () => _base64url,
  _bigint: () => _bigint,
  _boolean: () => _boolean,
  _catch: () => _catch,
  _check: () => _check,
  _cidrv4: () => _cidrv4,
  _cidrv6: () => _cidrv6,
  _coercedBigint: () => _coercedBigint,
  _coercedBoolean: () => _coercedBoolean,
  _coercedDate: () => _coercedDate,
  _coercedNumber: () => _coercedNumber,
  _coercedString: () => _coercedString,
  _cuid: () => _cuid,
  _cuid2: () => _cuid2,
  _custom: () => _custom,
  _date: () => _date,
  _decode: () => _decode,
  _decodeAsync: () => _decodeAsync,
  _default: () => _default,
  _discriminatedUnion: () => _discriminatedUnion,
  _e164: () => _e164,
  _email: () => _email,
  _emoji: () => _emoji2,
  _encode: () => _encode,
  _encodeAsync: () => _encodeAsync,
  _endsWith: () => _endsWith,
  _enum: () => _enum,
  _file: () => _file,
  _float32: () => _float32,
  _float64: () => _float64,
  _gt: () => _gt,
  _gte: () => _gte,
  _guid: () => _guid,
  _includes: () => _includes,
  _int: () => _int,
  _int32: () => _int32,
  _int64: () => _int64,
  _intersection: () => _intersection,
  _ipv4: () => _ipv4,
  _ipv6: () => _ipv6,
  _isoDate: () => _isoDate,
  _isoDateTime: () => _isoDateTime,
  _isoDuration: () => _isoDuration,
  _isoTime: () => _isoTime,
  _jwt: () => _jwt,
  _ksuid: () => _ksuid,
  _lazy: () => _lazy,
  _length: () => _length,
  _literal: () => _literal,
  _lowercase: () => _lowercase,
  _lt: () => _lt,
  _lte: () => _lte,
  _mac: () => _mac,
  _map: () => _map,
  _max: () => _lte,
  _maxLength: () => _maxLength,
  _maxSize: () => _maxSize,
  _mime: () => _mime,
  _min: () => _gte,
  _minLength: () => _minLength,
  _minSize: () => _minSize,
  _multipleOf: () => _multipleOf,
  _nan: () => _nan,
  _nanoid: () => _nanoid,
  _nativeEnum: () => _nativeEnum,
  _negative: () => _negative,
  _never: () => _never,
  _nonnegative: () => _nonnegative,
  _nonoptional: () => _nonoptional,
  _nonpositive: () => _nonpositive,
  _normalize: () => _normalize,
  _null: () => _null2,
  _nullable: () => _nullable,
  _number: () => _number,
  _optional: () => _optional,
  _overwrite: () => _overwrite,
  _parse: () => _parse,
  _parseAsync: () => _parseAsync,
  _pipe: () => _pipe,
  _positive: () => _positive,
  _promise: () => _promise,
  _property: () => _property,
  _readonly: () => _readonly,
  _record: () => _record,
  _refine: () => _refine,
  _regex: () => _regex,
  _safeDecode: () => _safeDecode,
  _safeDecodeAsync: () => _safeDecodeAsync,
  _safeEncode: () => _safeEncode,
  _safeEncodeAsync: () => _safeEncodeAsync,
  _safeParse: () => _safeParse,
  _safeParseAsync: () => _safeParseAsync,
  _set: () => _set,
  _size: () => _size,
  _slugify: () => _slugify,
  _startsWith: () => _startsWith,
  _string: () => _string,
  _stringFormat: () => _stringFormat,
  _stringbool: () => _stringbool,
  _success: () => _success,
  _superRefine: () => _superRefine,
  _symbol: () => _symbol,
  _templateLiteral: () => _templateLiteral,
  _toLowerCase: () => _toLowerCase,
  _toUpperCase: () => _toUpperCase,
  _transform: () => _transform,
  _trim: () => _trim,
  _tuple: () => _tuple,
  _uint32: () => _uint32,
  _uint64: () => _uint64,
  _ulid: () => _ulid,
  _undefined: () => _undefined2,
  _union: () => _union,
  _unknown: () => _unknown,
  _uppercase: () => _uppercase,
  _url: () => _url,
  _uuid: () => _uuid,
  _uuidv4: () => _uuidv4,
  _uuidv6: () => _uuidv6,
  _uuidv7: () => _uuidv7,
  _void: () => _void,
  _xid: () => _xid,
  _xor: () => _xor,
  clone: () => clone,
  config: () => config,
  createStandardJSONSchemaMethod: () => createStandardJSONSchemaMethod,
  createToJSONSchemaMethod: () => createToJSONSchemaMethod,
  decode: () => decode,
  decodeAsync: () => decodeAsync,
  describe: () => describe,
  encode: () => encode,
  encodeAsync: () => encodeAsync,
  extractDefs: () => extractDefs,
  finalize: () => finalize,
  flattenError: () => flattenError,
  formatError: () => formatError,
  globalConfig: () => globalConfig,
  globalRegistry: () => globalRegistry,
  initializeContext: () => initializeContext,
  isValidBase64: () => isValidBase64,
  isValidBase64URL: () => isValidBase64URL,
  isValidJWT: () => isValidJWT,
  locales: () => locales_exports,
  meta: () => meta,
  parse: () => parse,
  parseAsync: () => parseAsync,
  prettifyError: () => prettifyError,
  process: () => process2,
  regexes: () => regexes_exports,
  registry: () => registry,
  safeDecode: () => safeDecode,
  safeDecodeAsync: () => safeDecodeAsync,
  safeEncode: () => safeEncode,
  safeEncodeAsync: () => safeEncodeAsync,
  safeParse: () => safeParse,
  safeParseAsync: () => safeParseAsync,
  toDotPath: () => toDotPath,
  toJSONSchema: () => toJSONSchema,
  treeifyError: () => treeifyError,
  util: () => util_exports,
  version: () => version
});

// node_modules/zod/v4/core/core.js
var _a;
var NEVER = /* @__PURE__ */ Object.freeze({
  status: "aborted"
});
// @__NO_SIDE_EFFECTS__
function $constructor(name, initializer3, params) {
  function init(inst, def) {
    if (!inst._zod) {
      Object.defineProperty(inst, "_zod", {
        value: {
          def,
          constr: _,
          traits: /* @__PURE__ */ new Set()
        },
        enumerable: false
      });
    }
    if (inst._zod.traits.has(name)) {
      return;
    }
    inst._zod.traits.add(name);
    initializer3(inst, def);
    const proto = _.prototype;
    const keys = Object.keys(proto);
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (!(k in inst)) {
        inst[k] = proto[k].bind(inst);
      }
    }
  }
  const Parent = params?.Parent ?? Object;
  class Definition extends Parent {
  }
  Object.defineProperty(Definition, "name", { value: name });
  function _(def) {
    var _a3;
    const inst = params?.Parent ? new Definition() : this;
    init(inst, def);
    (_a3 = inst._zod).deferred ?? (_a3.deferred = []);
    for (const fn of inst._zod.deferred) {
      fn();
    }
    return inst;
  }
  Object.defineProperty(_, "init", { value: init });
  Object.defineProperty(_, Symbol.hasInstance, {
    value: (inst) => {
      if (params?.Parent && inst instanceof params.Parent)
        return true;
      return inst?._zod?.traits?.has(name);
    }
  });
  Object.defineProperty(_, "name", { value: name });
  return _;
}
var $brand = /* @__PURE__ */ Symbol("zod_brand");
var $ZodAsyncError = class extends Error {
  constructor() {
    super(`Encountered Promise during synchronous parse. Use .parseAsync() instead.`);
  }
};
var $ZodEncodeError = class extends Error {
  constructor(name) {
    super(`Encountered unidirectional transform during encode: ${name}`);
    this.name = "ZodEncodeError";
  }
};
(_a = globalThis).__zod_globalConfig ?? (_a.__zod_globalConfig = {});
var globalConfig = globalThis.__zod_globalConfig;
function config(newConfig) {
  if (newConfig)
    Object.assign(globalConfig, newConfig);
  return globalConfig;
}

// node_modules/zod/v4/core/util.js
var util_exports = {};
__export(util_exports, {
  BIGINT_FORMAT_RANGES: () => BIGINT_FORMAT_RANGES,
  Class: () => Class,
  NUMBER_FORMAT_RANGES: () => NUMBER_FORMAT_RANGES,
  aborted: () => aborted,
  allowsEval: () => allowsEval,
  assert: () => assert,
  assertEqual: () => assertEqual,
  assertIs: () => assertIs,
  assertNever: () => assertNever,
  assertNotEqual: () => assertNotEqual,
  assignProp: () => assignProp,
  base64ToUint8Array: () => base64ToUint8Array,
  base64urlToUint8Array: () => base64urlToUint8Array,
  cached: () => cached,
  captureStackTrace: () => captureStackTrace,
  cleanEnum: () => cleanEnum,
  cleanRegex: () => cleanRegex,
  clone: () => clone,
  cloneDef: () => cloneDef,
  createTransparentProxy: () => createTransparentProxy,
  defineLazy: () => defineLazy,
  esc: () => esc,
  escapeRegex: () => escapeRegex,
  explicitlyAborted: () => explicitlyAborted,
  extend: () => extend,
  finalizeIssue: () => finalizeIssue,
  floatSafeRemainder: () => floatSafeRemainder,
  getElementAtPath: () => getElementAtPath,
  getEnumValues: () => getEnumValues,
  getLengthableOrigin: () => getLengthableOrigin,
  getParsedType: () => getParsedType,
  getSizableOrigin: () => getSizableOrigin,
  hexToUint8Array: () => hexToUint8Array,
  isObject: () => isObject,
  isPlainObject: () => isPlainObject,
  issue: () => issue,
  joinValues: () => joinValues,
  jsonStringifyReplacer: () => jsonStringifyReplacer,
  merge: () => merge,
  mergeDefs: () => mergeDefs,
  normalizeParams: () => normalizeParams,
  nullish: () => nullish,
  numKeys: () => numKeys,
  objectClone: () => objectClone,
  omit: () => omit,
  optionalKeys: () => optionalKeys,
  parsedType: () => parsedType,
  partial: () => partial,
  pick: () => pick,
  prefixIssues: () => prefixIssues,
  primitiveTypes: () => primitiveTypes,
  promiseAllObject: () => promiseAllObject,
  propertyKeyTypes: () => propertyKeyTypes,
  randomString: () => randomString,
  required: () => required,
  safeExtend: () => safeExtend,
  shallowClone: () => shallowClone,
  slugify: () => slugify,
  stringifyPrimitive: () => stringifyPrimitive,
  uint8ArrayToBase64: () => uint8ArrayToBase64,
  uint8ArrayToBase64url: () => uint8ArrayToBase64url,
  uint8ArrayToHex: () => uint8ArrayToHex,
  unwrapMessage: () => unwrapMessage
});
function assertEqual(val) {
  return val;
}
function assertNotEqual(val) {
  return val;
}
function assertIs(_arg) {
}
function assertNever(_x) {
  throw new Error("Unexpected value in exhaustive check");
}
function assert(_) {
}
function getEnumValues(entries) {
  const numericValues = Object.values(entries).filter((v) => typeof v === "number");
  const values = Object.entries(entries).filter(([k, _]) => numericValues.indexOf(+k) === -1).map(([_, v]) => v);
  return values;
}
function joinValues(array2, separator = "|") {
  return array2.map((val) => stringifyPrimitive(val)).join(separator);
}
function jsonStringifyReplacer(_, value) {
  if (typeof value === "bigint")
    return value.toString();
  return value;
}
function cached(getter) {
  const set2 = false;
  return {
    get value() {
      if (!set2) {
        const value = getter();
        Object.defineProperty(this, "value", { value });
        return value;
      }
      throw new Error("cached value already set");
    }
  };
}
function nullish(input) {
  return input === null || input === void 0;
}
function cleanRegex(source) {
  const start = source.startsWith("^") ? 1 : 0;
  const end = source.endsWith("$") ? source.length - 1 : source.length;
  return source.slice(start, end);
}
function floatSafeRemainder(val, step) {
  const ratio = val / step;
  const roundedRatio = Math.round(ratio);
  const tolerance = Number.EPSILON * Math.max(Math.abs(ratio), 1);
  if (Math.abs(ratio - roundedRatio) < tolerance)
    return 0;
  return ratio - roundedRatio;
}
var EVALUATING = /* @__PURE__ */ Symbol("evaluating");
function defineLazy(object2, key, getter) {
  let value = void 0;
  Object.defineProperty(object2, key, {
    get() {
      if (value === EVALUATING) {
        return void 0;
      }
      if (value === void 0) {
        value = EVALUATING;
        value = getter();
      }
      return value;
    },
    set(v) {
      Object.defineProperty(object2, key, {
        value: v
        // configurable: true,
      });
    },
    configurable: true
  });
}
function objectClone(obj) {
  return Object.create(Object.getPrototypeOf(obj), Object.getOwnPropertyDescriptors(obj));
}
function assignProp(target, prop, value) {
  Object.defineProperty(target, prop, {
    value,
    writable: true,
    enumerable: true,
    configurable: true
  });
}
function mergeDefs(...defs) {
  const mergedDescriptors = {};
  for (const def of defs) {
    const descriptors = Object.getOwnPropertyDescriptors(def);
    Object.assign(mergedDescriptors, descriptors);
  }
  return Object.defineProperties({}, mergedDescriptors);
}
function cloneDef(schema) {
  return mergeDefs(schema._zod.def);
}
function getElementAtPath(obj, path) {
  if (!path)
    return obj;
  return path.reduce((acc, key) => acc?.[key], obj);
}
function promiseAllObject(promisesObj) {
  const keys = Object.keys(promisesObj);
  const promises = keys.map((key) => promisesObj[key]);
  return Promise.all(promises).then((results) => {
    const resolvedObj = {};
    for (let i = 0; i < keys.length; i++) {
      resolvedObj[keys[i]] = results[i];
    }
    return resolvedObj;
  });
}
function randomString(length = 10) {
  const chars = "abcdefghijklmnopqrstuvwxyz";
  let str = "";
  for (let i = 0; i < length; i++) {
    str += chars[Math.floor(Math.random() * chars.length)];
  }
  return str;
}
function esc(str) {
  return JSON.stringify(str);
}
function slugify(input) {
  return input.toLowerCase().trim().replace(/[^\w\s-]/g, "").replace(/[\s_-]+/g, "-").replace(/^-+|-+$/g, "");
}
var captureStackTrace = "captureStackTrace" in Error ? Error.captureStackTrace : (..._args) => {
};
function isObject(data) {
  return typeof data === "object" && data !== null && !Array.isArray(data);
}
var allowsEval = /* @__PURE__ */ cached(() => {
  if (globalConfig.jitless) {
    return false;
  }
  if (typeof navigator !== "undefined" && navigator?.userAgent?.includes("Cloudflare")) {
    return false;
  }
  try {
    const F = Function;
    new F("");
    return true;
  } catch (_) {
    return false;
  }
});
function isPlainObject(o) {
  if (isObject(o) === false)
    return false;
  const ctor = o.constructor;
  if (ctor === void 0)
    return true;
  if (typeof ctor !== "function")
    return true;
  const prot = ctor.prototype;
  if (isObject(prot) === false)
    return false;
  if (Object.prototype.hasOwnProperty.call(prot, "isPrototypeOf") === false) {
    return false;
  }
  return true;
}
function shallowClone(o) {
  if (isPlainObject(o))
    return { ...o };
  if (Array.isArray(o))
    return [...o];
  if (o instanceof Map)
    return new Map(o);
  if (o instanceof Set)
    return new Set(o);
  return o;
}
function numKeys(data) {
  let keyCount = 0;
  for (const key in data) {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      keyCount++;
    }
  }
  return keyCount;
}
var getParsedType = (data) => {
  const t = typeof data;
  switch (t) {
    case "undefined":
      return "undefined";
    case "string":
      return "string";
    case "number":
      return Number.isNaN(data) ? "nan" : "number";
    case "boolean":
      return "boolean";
    case "function":
      return "function";
    case "bigint":
      return "bigint";
    case "symbol":
      return "symbol";
    case "object":
      if (Array.isArray(data)) {
        return "array";
      }
      if (data === null) {
        return "null";
      }
      if (data.then && typeof data.then === "function" && data.catch && typeof data.catch === "function") {
        return "promise";
      }
      if (typeof Map !== "undefined" && data instanceof Map) {
        return "map";
      }
      if (typeof Set !== "undefined" && data instanceof Set) {
        return "set";
      }
      if (typeof Date !== "undefined" && data instanceof Date) {
        return "date";
      }
      if (typeof File !== "undefined" && data instanceof File) {
        return "file";
      }
      return "object";
    default:
      throw new Error(`Unknown data type: ${t}`);
  }
};
var propertyKeyTypes = /* @__PURE__ */ new Set(["string", "number", "symbol"]);
var primitiveTypes = /* @__PURE__ */ new Set([
  "string",
  "number",
  "bigint",
  "boolean",
  "symbol",
  "undefined"
]);
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function clone(inst, def, params) {
  const cl = new inst._zod.constr(def ?? inst._zod.def);
  if (!def || params?.parent)
    cl._zod.parent = inst;
  return cl;
}
function normalizeParams(_params) {
  const params = _params;
  if (!params)
    return {};
  if (typeof params === "string")
    return { error: () => params };
  if (params?.message !== void 0) {
    if (params?.error !== void 0)
      throw new Error("Cannot specify both `message` and `error` params");
    params.error = params.message;
  }
  delete params.message;
  if (typeof params.error === "string")
    return { ...params, error: () => params.error };
  return params;
}
function createTransparentProxy(getter) {
  let target;
  return new Proxy({}, {
    get(_, prop, receiver) {
      target ?? (target = getter());
      return Reflect.get(target, prop, receiver);
    },
    set(_, prop, value, receiver) {
      target ?? (target = getter());
      return Reflect.set(target, prop, value, receiver);
    },
    has(_, prop) {
      target ?? (target = getter());
      return Reflect.has(target, prop);
    },
    deleteProperty(_, prop) {
      target ?? (target = getter());
      return Reflect.deleteProperty(target, prop);
    },
    ownKeys(_) {
      target ?? (target = getter());
      return Reflect.ownKeys(target);
    },
    getOwnPropertyDescriptor(_, prop) {
      target ?? (target = getter());
      return Reflect.getOwnPropertyDescriptor(target, prop);
    },
    defineProperty(_, prop, descriptor) {
      target ?? (target = getter());
      return Reflect.defineProperty(target, prop, descriptor);
    }
  });
}
function stringifyPrimitive(value) {
  if (typeof value === "bigint")
    return value.toString() + "n";
  if (typeof value === "string")
    return `"${value}"`;
  return `${value}`;
}
function optionalKeys(shape) {
  return Object.keys(shape).filter((k) => {
    return shape[k]._zod.optin === "optional" && shape[k]._zod.optout === "optional";
  });
}
var NUMBER_FORMAT_RANGES = {
  safeint: [Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER],
  int32: [-2147483648, 2147483647],
  uint32: [0, 4294967295],
  float32: [-34028234663852886e22, 34028234663852886e22],
  float64: [-Number.MAX_VALUE, Number.MAX_VALUE]
};
var BIGINT_FORMAT_RANGES = {
  int64: [/* @__PURE__ */ BigInt("-9223372036854775808"), /* @__PURE__ */ BigInt("9223372036854775807")],
  uint64: [/* @__PURE__ */ BigInt(0), /* @__PURE__ */ BigInt("18446744073709551615")]
};
function pick(schema, mask) {
  const currDef = schema._zod.def;
  const checks = currDef.checks;
  const hasChecks = checks && checks.length > 0;
  if (hasChecks) {
    throw new Error(".pick() cannot be used on object schemas containing refinements");
  }
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const newShape = {};
      for (const key in mask) {
        if (!(key in currDef.shape)) {
          throw new Error(`Unrecognized key: "${key}"`);
        }
        if (!mask[key])
          continue;
        newShape[key] = currDef.shape[key];
      }
      assignProp(this, "shape", newShape);
      return newShape;
    },
    checks: []
  });
  return clone(schema, def);
}
function omit(schema, mask) {
  const currDef = schema._zod.def;
  const checks = currDef.checks;
  const hasChecks = checks && checks.length > 0;
  if (hasChecks) {
    throw new Error(".omit() cannot be used on object schemas containing refinements");
  }
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const newShape = { ...schema._zod.def.shape };
      for (const key in mask) {
        if (!(key in currDef.shape)) {
          throw new Error(`Unrecognized key: "${key}"`);
        }
        if (!mask[key])
          continue;
        delete newShape[key];
      }
      assignProp(this, "shape", newShape);
      return newShape;
    },
    checks: []
  });
  return clone(schema, def);
}
function extend(schema, shape) {
  if (!isPlainObject(shape)) {
    throw new Error("Invalid input to extend: expected a plain object");
  }
  const checks = schema._zod.def.checks;
  const hasChecks = checks && checks.length > 0;
  if (hasChecks) {
    const existingShape = schema._zod.def.shape;
    for (const key in shape) {
      if (Object.getOwnPropertyDescriptor(existingShape, key) !== void 0) {
        throw new Error("Cannot overwrite keys on object schemas containing refinements. Use `.safeExtend()` instead.");
      }
    }
  }
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const _shape = { ...schema._zod.def.shape, ...shape };
      assignProp(this, "shape", _shape);
      return _shape;
    }
  });
  return clone(schema, def);
}
function safeExtend(schema, shape) {
  if (!isPlainObject(shape)) {
    throw new Error("Invalid input to safeExtend: expected a plain object");
  }
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const _shape = { ...schema._zod.def.shape, ...shape };
      assignProp(this, "shape", _shape);
      return _shape;
    }
  });
  return clone(schema, def);
}
function merge(a, b) {
  if (a._zod.def.checks?.length) {
    throw new Error(".merge() cannot be used on object schemas containing refinements. Use .safeExtend() instead.");
  }
  const def = mergeDefs(a._zod.def, {
    get shape() {
      const _shape = { ...a._zod.def.shape, ...b._zod.def.shape };
      assignProp(this, "shape", _shape);
      return _shape;
    },
    get catchall() {
      return b._zod.def.catchall;
    },
    checks: b._zod.def.checks ?? []
  });
  return clone(a, def);
}
function partial(Class2, schema, mask) {
  const currDef = schema._zod.def;
  const checks = currDef.checks;
  const hasChecks = checks && checks.length > 0;
  if (hasChecks) {
    throw new Error(".partial() cannot be used on object schemas containing refinements");
  }
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const oldShape = schema._zod.def.shape;
      const shape = { ...oldShape };
      if (mask) {
        for (const key in mask) {
          if (!(key in oldShape)) {
            throw new Error(`Unrecognized key: "${key}"`);
          }
          if (!mask[key])
            continue;
          shape[key] = Class2 ? new Class2({
            type: "optional",
            innerType: oldShape[key]
          }) : oldShape[key];
        }
      } else {
        for (const key in oldShape) {
          shape[key] = Class2 ? new Class2({
            type: "optional",
            innerType: oldShape[key]
          }) : oldShape[key];
        }
      }
      assignProp(this, "shape", shape);
      return shape;
    },
    checks: []
  });
  return clone(schema, def);
}
function required(Class2, schema, mask) {
  const def = mergeDefs(schema._zod.def, {
    get shape() {
      const oldShape = schema._zod.def.shape;
      const shape = { ...oldShape };
      if (mask) {
        for (const key in mask) {
          if (!(key in shape)) {
            throw new Error(`Unrecognized key: "${key}"`);
          }
          if (!mask[key])
            continue;
          shape[key] = new Class2({
            type: "nonoptional",
            innerType: oldShape[key]
          });
        }
      } else {
        for (const key in oldShape) {
          shape[key] = new Class2({
            type: "nonoptional",
            innerType: oldShape[key]
          });
        }
      }
      assignProp(this, "shape", shape);
      return shape;
    }
  });
  return clone(schema, def);
}
function aborted(x, startIndex = 0) {
  if (x.aborted === true)
    return true;
  for (let i = startIndex; i < x.issues.length; i++) {
    if (x.issues[i]?.continue !== true) {
      return true;
    }
  }
  return false;
}
function explicitlyAborted(x, startIndex = 0) {
  if (x.aborted === true)
    return true;
  for (let i = startIndex; i < x.issues.length; i++) {
    if (x.issues[i]?.continue === false) {
      return true;
    }
  }
  return false;
}
function prefixIssues(path, issues) {
  return issues.map((iss) => {
    var _a3;
    (_a3 = iss).path ?? (_a3.path = []);
    iss.path.unshift(path);
    return iss;
  });
}
function unwrapMessage(message) {
  return typeof message === "string" ? message : message?.message;
}
function finalizeIssue(iss, ctx, config2) {
  const message = iss.message ? iss.message : unwrapMessage(iss.inst?._zod.def?.error?.(iss)) ?? unwrapMessage(ctx?.error?.(iss)) ?? unwrapMessage(config2.customError?.(iss)) ?? unwrapMessage(config2.localeError?.(iss)) ?? "Invalid input";
  const { inst: _inst, continue: _continue, input: _input, ...rest } = iss;
  rest.path ?? (rest.path = []);
  rest.message = message;
  if (ctx?.reportInput) {
    rest.input = _input;
  }
  return rest;
}
function getSizableOrigin(input) {
  if (input instanceof Set)
    return "set";
  if (input instanceof Map)
    return "map";
  if (input instanceof File)
    return "file";
  return "unknown";
}
function getLengthableOrigin(input) {
  if (Array.isArray(input))
    return "array";
  if (typeof input === "string")
    return "string";
  return "unknown";
}
function parsedType(data) {
  const t = typeof data;
  switch (t) {
    case "number": {
      return Number.isNaN(data) ? "nan" : "number";
    }
    case "object": {
      if (data === null) {
        return "null";
      }
      if (Array.isArray(data)) {
        return "array";
      }
      const obj = data;
      if (obj && Object.getPrototypeOf(obj) !== Object.prototype && "constructor" in obj && obj.constructor) {
        return obj.constructor.name;
      }
    }
  }
  return t;
}
function issue(...args) {
  const [iss, input, inst] = args;
  if (typeof iss === "string") {
    return {
      message: iss,
      code: "custom",
      input,
      inst
    };
  }
  return { ...iss };
}
function cleanEnum(obj) {
  return Object.entries(obj).filter(([k, _]) => {
    return Number.isNaN(Number.parseInt(k, 10));
  }).map((el) => el[1]);
}
function base64ToUint8Array(base643) {
  const binaryString = atob(base643);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}
function uint8ArrayToBase64(bytes) {
  let binaryString = "";
  for (let i = 0; i < bytes.length; i++) {
    binaryString += String.fromCharCode(bytes[i]);
  }
  return btoa(binaryString);
}
function base64urlToUint8Array(base64url3) {
  const base643 = base64url3.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - base643.length % 4) % 4);
  return base64ToUint8Array(base643 + padding);
}
function uint8ArrayToBase64url(bytes) {
  return uint8ArrayToBase64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}
function hexToUint8Array(hex3) {
  const cleanHex = hex3.replace(/^0x/, "");
  if (cleanHex.length % 2 !== 0) {
    throw new Error("Invalid hex string length");
  }
  const bytes = new Uint8Array(cleanHex.length / 2);
  for (let i = 0; i < cleanHex.length; i += 2) {
    bytes[i / 2] = Number.parseInt(cleanHex.slice(i, i + 2), 16);
  }
  return bytes;
}
function uint8ArrayToHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}
var Class = class {
  constructor(..._args) {
  }
};

// node_modules/zod/v4/core/errors.js
var initializer = (inst, def) => {
  inst.name = "$ZodError";
  Object.defineProperty(inst, "_zod", {
    value: inst._zod,
    enumerable: false
  });
  Object.defineProperty(inst, "issues", {
    value: def,
    enumerable: false
  });
  inst.message = JSON.stringify(def, jsonStringifyReplacer, 2);
  Object.defineProperty(inst, "toString", {
    value: () => inst.message,
    enumerable: false
  });
};
var $ZodError = $constructor("$ZodError", initializer);
var $ZodRealError = $constructor("$ZodError", initializer, { Parent: Error });
function flattenError(error51, mapper = (issue3) => issue3.message) {
  const fieldErrors = {};
  const formErrors = [];
  for (const sub of error51.issues) {
    if (sub.path.length > 0) {
      fieldErrors[sub.path[0]] = fieldErrors[sub.path[0]] || [];
      fieldErrors[sub.path[0]].push(mapper(sub));
    } else {
      formErrors.push(mapper(sub));
    }
  }
  return { formErrors, fieldErrors };
}
function formatError(error51, mapper = (issue3) => issue3.message) {
  const fieldErrors = { _errors: [] };
  const processError = (error52, path = []) => {
    for (const issue3 of error52.issues) {
      if (issue3.code === "invalid_union" && issue3.errors.length) {
        issue3.errors.map((issues) => processError({ issues }, [...path, ...issue3.path]));
      } else if (issue3.code === "invalid_key") {
        processError({ issues: issue3.issues }, [...path, ...issue3.path]);
      } else if (issue3.code === "invalid_element") {
        processError({ issues: issue3.issues }, [...path, ...issue3.path]);
      } else {
        const fullpath = [...path, ...issue3.path];
        if (fullpath.length === 0) {
          fieldErrors._errors.push(mapper(issue3));
        } else {
          let curr = fieldErrors;
          let i = 0;
          while (i < fullpath.length) {
            const el = fullpath[i];
            const terminal = i === fullpath.length - 1;
            if (!terminal) {
              curr[el] = curr[el] || { _errors: [] };
            } else {
              curr[el] = curr[el] || { _errors: [] };
              curr[el]._errors.push(mapper(issue3));
            }
            curr = curr[el];
            i++;
          }
        }
      }
    }
  };
  processError(error51);
  return fieldErrors;
}
function treeifyError(error51, mapper = (issue3) => issue3.message) {
  const result = { errors: [] };
  const processError = (error52, path = []) => {
    var _a3, _b;
    for (const issue3 of error52.issues) {
      if (issue3.code === "invalid_union" && issue3.errors.length) {
        issue3.errors.map((issues) => processError({ issues }, [...path, ...issue3.path]));
      } else if (issue3.code === "invalid_key") {
        processError({ issues: issue3.issues }, [...path, ...issue3.path]);
      } else if (issue3.code === "invalid_element") {
        processError({ issues: issue3.issues }, [...path, ...issue3.path]);
      } else {
        const fullpath = [...path, ...issue3.path];
        if (fullpath.length === 0) {
          result.errors.push(mapper(issue3));
          continue;
        }
        let curr = result;
        let i = 0;
        while (i < fullpath.length) {
          const el = fullpath[i];
          const terminal = i === fullpath.length - 1;
          if (typeof el === "string") {
            curr.properties ?? (curr.properties = {});
            (_a3 = curr.properties)[el] ?? (_a3[el] = { errors: [] });
            curr = curr.properties[el];
          } else {
            curr.items ?? (curr.items = []);
            (_b = curr.items)[el] ?? (_b[el] = { errors: [] });
            curr = curr.items[el];
          }
          if (terminal) {
            curr.errors.push(mapper(issue3));
          }
          i++;
        }
      }
    }
  };
  processError(error51);
  return result;
}
function toDotPath(_path) {
  const segs = [];
  const path = _path.map((seg) => typeof seg === "object" ? seg.key : seg);
  for (const seg of path) {
    if (typeof seg === "number")
      segs.push(`[${seg}]`);
    else if (typeof seg === "symbol")
      segs.push(`[${JSON.stringify(String(seg))}]`);
    else if (/[^\w$]/.test(seg))
      segs.push(`[${JSON.stringify(seg)}]`);
    else {
      if (segs.length)
        segs.push(".");
      segs.push(seg);
    }
  }
  return segs.join("");
}
function prettifyError(error51) {
  const lines = [];
  const issues = [...error51.issues].sort((a, b) => (a.path ?? []).length - (b.path ?? []).length);
  for (const issue3 of issues) {
    lines.push(`\u2716 ${issue3.message}`);
    if (issue3.path?.length)
      lines.push(`  \u2192 at ${toDotPath(issue3.path)}`);
  }
  return lines.join("\n");
}

// node_modules/zod/v4/core/parse.js
var _parse = (_Err) => (schema, value, _ctx, _params) => {
  const ctx = _ctx ? { ..._ctx, async: false } : { async: false };
  const result = schema._zod.run({ value, issues: [] }, ctx);
  if (result instanceof Promise) {
    throw new $ZodAsyncError();
  }
  if (result.issues.length) {
    const e = new (_params?.Err ?? _Err)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())));
    captureStackTrace(e, _params?.callee);
    throw e;
  }
  return result.value;
};
var parse = /* @__PURE__ */ _parse($ZodRealError);
var _parseAsync = (_Err) => async (schema, value, _ctx, params) => {
  const ctx = _ctx ? { ..._ctx, async: true } : { async: true };
  let result = schema._zod.run({ value, issues: [] }, ctx);
  if (result instanceof Promise)
    result = await result;
  if (result.issues.length) {
    const e = new (params?.Err ?? _Err)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())));
    captureStackTrace(e, params?.callee);
    throw e;
  }
  return result.value;
};
var parseAsync = /* @__PURE__ */ _parseAsync($ZodRealError);
var _safeParse = (_Err) => (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, async: false } : { async: false };
  const result = schema._zod.run({ value, issues: [] }, ctx);
  if (result instanceof Promise) {
    throw new $ZodAsyncError();
  }
  return result.issues.length ? {
    success: false,
    error: new (_Err ?? $ZodError)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
  } : { success: true, data: result.value };
};
var safeParse = /* @__PURE__ */ _safeParse($ZodRealError);
var _safeParseAsync = (_Err) => async (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, async: true } : { async: true };
  let result = schema._zod.run({ value, issues: [] }, ctx);
  if (result instanceof Promise)
    result = await result;
  return result.issues.length ? {
    success: false,
    error: new _Err(result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
  } : { success: true, data: result.value };
};
var safeParseAsync = /* @__PURE__ */ _safeParseAsync($ZodRealError);
var _encode = (_Err) => (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, direction: "backward" } : { direction: "backward" };
  return _parse(_Err)(schema, value, ctx);
};
var encode = /* @__PURE__ */ _encode($ZodRealError);
var _decode = (_Err) => (schema, value, _ctx) => {
  return _parse(_Err)(schema, value, _ctx);
};
var decode = /* @__PURE__ */ _decode($ZodRealError);
var _encodeAsync = (_Err) => async (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, direction: "backward" } : { direction: "backward" };
  return _parseAsync(_Err)(schema, value, ctx);
};
var encodeAsync = /* @__PURE__ */ _encodeAsync($ZodRealError);
var _decodeAsync = (_Err) => async (schema, value, _ctx) => {
  return _parseAsync(_Err)(schema, value, _ctx);
};
var decodeAsync = /* @__PURE__ */ _decodeAsync($ZodRealError);
var _safeEncode = (_Err) => (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, direction: "backward" } : { direction: "backward" };
  return _safeParse(_Err)(schema, value, ctx);
};
var safeEncode = /* @__PURE__ */ _safeEncode($ZodRealError);
var _safeDecode = (_Err) => (schema, value, _ctx) => {
  return _safeParse(_Err)(schema, value, _ctx);
};
var safeDecode = /* @__PURE__ */ _safeDecode($ZodRealError);
var _safeEncodeAsync = (_Err) => async (schema, value, _ctx) => {
  const ctx = _ctx ? { ..._ctx, direction: "backward" } : { direction: "backward" };
  return _safeParseAsync(_Err)(schema, value, ctx);
};
var safeEncodeAsync = /* @__PURE__ */ _safeEncodeAsync($ZodRealError);
var _safeDecodeAsync = (_Err) => async (schema, value, _ctx) => {
  return _safeParseAsync(_Err)(schema, value, _ctx);
};
var safeDecodeAsync = /* @__PURE__ */ _safeDecodeAsync($ZodRealError);

// node_modules/zod/v4/core/regexes.js
var regexes_exports = {};
__export(regexes_exports, {
  base64: () => base64,
  base64url: () => base64url,
  bigint: () => bigint,
  boolean: () => boolean,
  browserEmail: () => browserEmail,
  cidrv4: () => cidrv4,
  cidrv6: () => cidrv6,
  cuid: () => cuid,
  cuid2: () => cuid2,
  date: () => date,
  datetime: () => datetime,
  domain: () => domain,
  duration: () => duration,
  e164: () => e164,
  email: () => email,
  emoji: () => emoji,
  extendedDuration: () => extendedDuration,
  guid: () => guid,
  hex: () => hex,
  hostname: () => hostname,
  html5Email: () => html5Email,
  httpProtocol: () => httpProtocol,
  idnEmail: () => idnEmail,
  integer: () => integer,
  ipv4: () => ipv4,
  ipv6: () => ipv6,
  ksuid: () => ksuid,
  lowercase: () => lowercase,
  mac: () => mac,
  md5_base64: () => md5_base64,
  md5_base64url: () => md5_base64url,
  md5_hex: () => md5_hex,
  nanoid: () => nanoid,
  null: () => _null,
  number: () => number,
  rfc5322Email: () => rfc5322Email,
  sha1_base64: () => sha1_base64,
  sha1_base64url: () => sha1_base64url,
  sha1_hex: () => sha1_hex,
  sha256_base64: () => sha256_base64,
  sha256_base64url: () => sha256_base64url,
  sha256_hex: () => sha256_hex,
  sha384_base64: () => sha384_base64,
  sha384_base64url: () => sha384_base64url,
  sha384_hex: () => sha384_hex,
  sha512_base64: () => sha512_base64,
  sha512_base64url: () => sha512_base64url,
  sha512_hex: () => sha512_hex,
  string: () => string,
  time: () => time,
  ulid: () => ulid,
  undefined: () => _undefined,
  unicodeEmail: () => unicodeEmail,
  uppercase: () => uppercase,
  uuid: () => uuid,
  uuid4: () => uuid4,
  uuid6: () => uuid6,
  uuid7: () => uuid7,
  xid: () => xid
});
var cuid = /^[cC][0-9a-z]{6,}$/;
var cuid2 = /^[0-9a-z]+$/;
var ulid = /^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$/;
var xid = /^[0-9a-vA-V]{20}$/;
var ksuid = /^[A-Za-z0-9]{27}$/;
var nanoid = /^[a-zA-Z0-9_-]{21}$/;
var duration = /^P(?:(\d+W)|(?!.*W)(?=\d|T\d)(\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+([.,]\d+)?S)?)?)$/;
var extendedDuration = /^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/;
var guid = /^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;
var uuid = (version2) => {
  if (!version2)
    return /^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$/;
  return new RegExp(`^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-${version2}[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$`);
};
var uuid4 = /* @__PURE__ */ uuid(4);
var uuid6 = /* @__PURE__ */ uuid(6);
var uuid7 = /* @__PURE__ */ uuid(7);
var email = /^(?!\.)(?!.*\.\.)([A-Za-z0-9_'+\-\.]*)[A-Za-z0-9_+-]@([A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}$/;
var html5Email = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
var rfc5322Email = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
var unicodeEmail = /^[^\s@"]{1,64}@[^\s@]{1,255}$/u;
var idnEmail = unicodeEmail;
var browserEmail = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
var _emoji = `^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$`;
function emoji() {
  return new RegExp(_emoji, "u");
}
var ipv4 = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/;
var ipv6 = /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:))$/;
var mac = (delimiter) => {
  const escapedDelim = escapeRegex(delimiter ?? ":");
  return new RegExp(`^(?:[0-9A-F]{2}${escapedDelim}){5}[0-9A-F]{2}$|^(?:[0-9a-f]{2}${escapedDelim}){5}[0-9a-f]{2}$`);
};
var cidrv4 = /^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/([0-9]|[1-2][0-9]|3[0-2])$/;
var cidrv6 = /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|::|([0-9a-fA-F]{1,4})?::([0-9a-fA-F]{1,4}:?){0,6})\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/;
var base64 = /^$|^(?:[0-9a-zA-Z+/]{4})*(?:(?:[0-9a-zA-Z+/]{2}==)|(?:[0-9a-zA-Z+/]{3}=))?$/;
var base64url = /^[A-Za-z0-9_-]*$/;
var hostname = /^(?=.{1,253}\.?$)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[-0-9a-zA-Z]{0,61}[0-9a-zA-Z])?)*\.?$/;
var domain = /^([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/;
var httpProtocol = /^https?$/;
var e164 = /^\+[1-9]\d{6,14}$/;
var dateSource = `(?:(?:\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12]\\d|3[01])|(?:0[469]|11)-(?:0[1-9]|[12]\\d|30)|(?:02)-(?:0[1-9]|1\\d|2[0-8])))`;
var date = /* @__PURE__ */ new RegExp(`^${dateSource}$`);
function timeSource(args) {
  const hhmm = `(?:[01]\\d|2[0-3]):[0-5]\\d`;
  const regex = typeof args.precision === "number" ? args.precision === -1 ? `${hhmm}` : args.precision === 0 ? `${hhmm}:[0-5]\\d` : `${hhmm}:[0-5]\\d\\.\\d{${args.precision}}` : `${hhmm}(?::[0-5]\\d(?:\\.\\d+)?)?`;
  return regex;
}
function time(args) {
  return new RegExp(`^${timeSource(args)}$`);
}
function datetime(args) {
  const time3 = timeSource({ precision: args.precision });
  const opts = ["Z"];
  if (args.local)
    opts.push("");
  if (args.offset)
    opts.push(`([+-](?:[01]\\d|2[0-3]):[0-5]\\d)`);
  const timeRegex = `${time3}(?:${opts.join("|")})`;
  return new RegExp(`^${dateSource}T(?:${timeRegex})$`);
}
var string = (params) => {
  const regex = params ? `[\\s\\S]{${params?.minimum ?? 0},${params?.maximum ?? ""}}` : `[\\s\\S]*`;
  return new RegExp(`^${regex}$`);
};
var bigint = /^-?\d+n?$/;
var integer = /^-?\d+$/;
var number = /^-?\d+(?:\.\d+)?$/;
var boolean = /^(?:true|false)$/i;
var _null = /^null$/i;
var _undefined = /^undefined$/i;
var lowercase = /^[^A-Z]*$/;
var uppercase = /^[^a-z]*$/;
var hex = /^[0-9a-fA-F]*$/;
function fixedBase64(bodyLength, padding) {
  return new RegExp(`^[A-Za-z0-9+/]{${bodyLength}}${padding}$`);
}
function fixedBase64url(length) {
  return new RegExp(`^[A-Za-z0-9_-]{${length}}$`);
}
var md5_hex = /^[0-9a-fA-F]{32}$/;
var md5_base64 = /* @__PURE__ */ fixedBase64(22, "==");
var md5_base64url = /* @__PURE__ */ fixedBase64url(22);
var sha1_hex = /^[0-9a-fA-F]{40}$/;
var sha1_base64 = /* @__PURE__ */ fixedBase64(27, "=");
var sha1_base64url = /* @__PURE__ */ fixedBase64url(27);
var sha256_hex = /^[0-9a-fA-F]{64}$/;
var sha256_base64 = /* @__PURE__ */ fixedBase64(43, "=");
var sha256_base64url = /* @__PURE__ */ fixedBase64url(43);
var sha384_hex = /^[0-9a-fA-F]{96}$/;
var sha384_base64 = /* @__PURE__ */ fixedBase64(64, "");
var sha384_base64url = /* @__PURE__ */ fixedBase64url(64);
var sha512_hex = /^[0-9a-fA-F]{128}$/;
var sha512_base64 = /* @__PURE__ */ fixedBase64(86, "==");
var sha512_base64url = /* @__PURE__ */ fixedBase64url(86);

// node_modules/zod/v4/core/checks.js
var $ZodCheck = /* @__PURE__ */ $constructor("$ZodCheck", (inst, def) => {
  var _a3;
  inst._zod ?? (inst._zod = {});
  inst._zod.def = def;
  (_a3 = inst._zod).onattach ?? (_a3.onattach = []);
});
var numericOriginMap = {
  number: "number",
  bigint: "bigint",
  object: "date"
};
var $ZodCheckLessThan = /* @__PURE__ */ $constructor("$ZodCheckLessThan", (inst, def) => {
  $ZodCheck.init(inst, def);
  const origin = numericOriginMap[typeof def.value];
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    const curr = (def.inclusive ? bag.maximum : bag.exclusiveMaximum) ?? Number.POSITIVE_INFINITY;
    if (def.value < curr) {
      if (def.inclusive)
        bag.maximum = def.value;
      else
        bag.exclusiveMaximum = def.value;
    }
  });
  inst._zod.check = (payload) => {
    if (def.inclusive ? payload.value <= def.value : payload.value < def.value) {
      return;
    }
    payload.issues.push({
      origin,
      code: "too_big",
      maximum: typeof def.value === "object" ? def.value.getTime() : def.value,
      input: payload.value,
      inclusive: def.inclusive,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckGreaterThan = /* @__PURE__ */ $constructor("$ZodCheckGreaterThan", (inst, def) => {
  $ZodCheck.init(inst, def);
  const origin = numericOriginMap[typeof def.value];
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    const curr = (def.inclusive ? bag.minimum : bag.exclusiveMinimum) ?? Number.NEGATIVE_INFINITY;
    if (def.value > curr) {
      if (def.inclusive)
        bag.minimum = def.value;
      else
        bag.exclusiveMinimum = def.value;
    }
  });
  inst._zod.check = (payload) => {
    if (def.inclusive ? payload.value >= def.value : payload.value > def.value) {
      return;
    }
    payload.issues.push({
      origin,
      code: "too_small",
      minimum: typeof def.value === "object" ? def.value.getTime() : def.value,
      input: payload.value,
      inclusive: def.inclusive,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckMultipleOf = /* @__PURE__ */ $constructor("$ZodCheckMultipleOf", (inst, def) => {
  $ZodCheck.init(inst, def);
  inst._zod.onattach.push((inst2) => {
    var _a3;
    (_a3 = inst2._zod.bag).multipleOf ?? (_a3.multipleOf = def.value);
  });
  inst._zod.check = (payload) => {
    if (typeof payload.value !== typeof def.value)
      throw new Error("Cannot mix number and bigint in multiple_of check.");
    const isMultiple = typeof payload.value === "bigint" ? payload.value % def.value === BigInt(0) : floatSafeRemainder(payload.value, def.value) === 0;
    if (isMultiple)
      return;
    payload.issues.push({
      origin: typeof payload.value,
      code: "not_multiple_of",
      divisor: def.value,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckNumberFormat = /* @__PURE__ */ $constructor("$ZodCheckNumberFormat", (inst, def) => {
  $ZodCheck.init(inst, def);
  def.format = def.format || "float64";
  const isInt = def.format?.includes("int");
  const origin = isInt ? "int" : "number";
  const [minimum, maximum] = NUMBER_FORMAT_RANGES[def.format];
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.format = def.format;
    bag.minimum = minimum;
    bag.maximum = maximum;
    if (isInt)
      bag.pattern = integer;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    if (isInt) {
      if (!Number.isInteger(input)) {
        payload.issues.push({
          expected: origin,
          format: def.format,
          code: "invalid_type",
          continue: false,
          input,
          inst
        });
        return;
      }
      if (!Number.isSafeInteger(input)) {
        if (input > 0) {
          payload.issues.push({
            input,
            code: "too_big",
            maximum: Number.MAX_SAFE_INTEGER,
            note: "Integers must be within the safe integer range.",
            inst,
            origin,
            inclusive: true,
            continue: !def.abort
          });
        } else {
          payload.issues.push({
            input,
            code: "too_small",
            minimum: Number.MIN_SAFE_INTEGER,
            note: "Integers must be within the safe integer range.",
            inst,
            origin,
            inclusive: true,
            continue: !def.abort
          });
        }
        return;
      }
    }
    if (input < minimum) {
      payload.issues.push({
        origin: "number",
        input,
        code: "too_small",
        minimum,
        inclusive: true,
        inst,
        continue: !def.abort
      });
    }
    if (input > maximum) {
      payload.issues.push({
        origin: "number",
        input,
        code: "too_big",
        maximum,
        inclusive: true,
        inst,
        continue: !def.abort
      });
    }
  };
});
var $ZodCheckBigIntFormat = /* @__PURE__ */ $constructor("$ZodCheckBigIntFormat", (inst, def) => {
  $ZodCheck.init(inst, def);
  const [minimum, maximum] = BIGINT_FORMAT_RANGES[def.format];
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.format = def.format;
    bag.minimum = minimum;
    bag.maximum = maximum;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    if (input < minimum) {
      payload.issues.push({
        origin: "bigint",
        input,
        code: "too_small",
        minimum,
        inclusive: true,
        inst,
        continue: !def.abort
      });
    }
    if (input > maximum) {
      payload.issues.push({
        origin: "bigint",
        input,
        code: "too_big",
        maximum,
        inclusive: true,
        inst,
        continue: !def.abort
      });
    }
  };
});
var $ZodCheckMaxSize = /* @__PURE__ */ $constructor("$ZodCheckMaxSize", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.size !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const curr = inst2._zod.bag.maximum ?? Number.POSITIVE_INFINITY;
    if (def.maximum < curr)
      inst2._zod.bag.maximum = def.maximum;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const size = input.size;
    if (size <= def.maximum)
      return;
    payload.issues.push({
      origin: getSizableOrigin(input),
      code: "too_big",
      maximum: def.maximum,
      inclusive: true,
      input,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckMinSize = /* @__PURE__ */ $constructor("$ZodCheckMinSize", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.size !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const curr = inst2._zod.bag.minimum ?? Number.NEGATIVE_INFINITY;
    if (def.minimum > curr)
      inst2._zod.bag.minimum = def.minimum;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const size = input.size;
    if (size >= def.minimum)
      return;
    payload.issues.push({
      origin: getSizableOrigin(input),
      code: "too_small",
      minimum: def.minimum,
      inclusive: true,
      input,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckSizeEquals = /* @__PURE__ */ $constructor("$ZodCheckSizeEquals", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.size !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.minimum = def.size;
    bag.maximum = def.size;
    bag.size = def.size;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const size = input.size;
    if (size === def.size)
      return;
    const tooBig = size > def.size;
    payload.issues.push({
      origin: getSizableOrigin(input),
      ...tooBig ? { code: "too_big", maximum: def.size } : { code: "too_small", minimum: def.size },
      inclusive: true,
      exact: true,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckMaxLength = /* @__PURE__ */ $constructor("$ZodCheckMaxLength", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.length !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const curr = inst2._zod.bag.maximum ?? Number.POSITIVE_INFINITY;
    if (def.maximum < curr)
      inst2._zod.bag.maximum = def.maximum;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const length = input.length;
    if (length <= def.maximum)
      return;
    const origin = getLengthableOrigin(input);
    payload.issues.push({
      origin,
      code: "too_big",
      maximum: def.maximum,
      inclusive: true,
      input,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckMinLength = /* @__PURE__ */ $constructor("$ZodCheckMinLength", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.length !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const curr = inst2._zod.bag.minimum ?? Number.NEGATIVE_INFINITY;
    if (def.minimum > curr)
      inst2._zod.bag.minimum = def.minimum;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const length = input.length;
    if (length >= def.minimum)
      return;
    const origin = getLengthableOrigin(input);
    payload.issues.push({
      origin,
      code: "too_small",
      minimum: def.minimum,
      inclusive: true,
      input,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckLengthEquals = /* @__PURE__ */ $constructor("$ZodCheckLengthEquals", (inst, def) => {
  var _a3;
  $ZodCheck.init(inst, def);
  (_a3 = inst._zod.def).when ?? (_a3.when = (payload) => {
    const val = payload.value;
    return !nullish(val) && val.length !== void 0;
  });
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.minimum = def.length;
    bag.maximum = def.length;
    bag.length = def.length;
  });
  inst._zod.check = (payload) => {
    const input = payload.value;
    const length = input.length;
    if (length === def.length)
      return;
    const origin = getLengthableOrigin(input);
    const tooBig = length > def.length;
    payload.issues.push({
      origin,
      ...tooBig ? { code: "too_big", maximum: def.length } : { code: "too_small", minimum: def.length },
      inclusive: true,
      exact: true,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckStringFormat = /* @__PURE__ */ $constructor("$ZodCheckStringFormat", (inst, def) => {
  var _a3, _b;
  $ZodCheck.init(inst, def);
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.format = def.format;
    if (def.pattern) {
      bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
      bag.patterns.add(def.pattern);
    }
  });
  if (def.pattern)
    (_a3 = inst._zod).check ?? (_a3.check = (payload) => {
      def.pattern.lastIndex = 0;
      if (def.pattern.test(payload.value))
        return;
      payload.issues.push({
        origin: "string",
        code: "invalid_format",
        format: def.format,
        input: payload.value,
        ...def.pattern ? { pattern: def.pattern.toString() } : {},
        inst,
        continue: !def.abort
      });
    });
  else
    (_b = inst._zod).check ?? (_b.check = () => {
    });
});
var $ZodCheckRegex = /* @__PURE__ */ $constructor("$ZodCheckRegex", (inst, def) => {
  $ZodCheckStringFormat.init(inst, def);
  inst._zod.check = (payload) => {
    def.pattern.lastIndex = 0;
    if (def.pattern.test(payload.value))
      return;
    payload.issues.push({
      origin: "string",
      code: "invalid_format",
      format: "regex",
      input: payload.value,
      pattern: def.pattern.toString(),
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckLowerCase = /* @__PURE__ */ $constructor("$ZodCheckLowerCase", (inst, def) => {
  def.pattern ?? (def.pattern = lowercase);
  $ZodCheckStringFormat.init(inst, def);
});
var $ZodCheckUpperCase = /* @__PURE__ */ $constructor("$ZodCheckUpperCase", (inst, def) => {
  def.pattern ?? (def.pattern = uppercase);
  $ZodCheckStringFormat.init(inst, def);
});
var $ZodCheckIncludes = /* @__PURE__ */ $constructor("$ZodCheckIncludes", (inst, def) => {
  $ZodCheck.init(inst, def);
  const escapedRegex = escapeRegex(def.includes);
  const pattern = new RegExp(typeof def.position === "number" ? `^.{${def.position}}${escapedRegex}` : escapedRegex);
  def.pattern = pattern;
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
    bag.patterns.add(pattern);
  });
  inst._zod.check = (payload) => {
    if (payload.value.includes(def.includes, def.position))
      return;
    payload.issues.push({
      origin: "string",
      code: "invalid_format",
      format: "includes",
      includes: def.includes,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckStartsWith = /* @__PURE__ */ $constructor("$ZodCheckStartsWith", (inst, def) => {
  $ZodCheck.init(inst, def);
  const pattern = new RegExp(`^${escapeRegex(def.prefix)}.*`);
  def.pattern ?? (def.pattern = pattern);
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
    bag.patterns.add(pattern);
  });
  inst._zod.check = (payload) => {
    if (payload.value.startsWith(def.prefix))
      return;
    payload.issues.push({
      origin: "string",
      code: "invalid_format",
      format: "starts_with",
      prefix: def.prefix,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckEndsWith = /* @__PURE__ */ $constructor("$ZodCheckEndsWith", (inst, def) => {
  $ZodCheck.init(inst, def);
  const pattern = new RegExp(`.*${escapeRegex(def.suffix)}$`);
  def.pattern ?? (def.pattern = pattern);
  inst._zod.onattach.push((inst2) => {
    const bag = inst2._zod.bag;
    bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
    bag.patterns.add(pattern);
  });
  inst._zod.check = (payload) => {
    if (payload.value.endsWith(def.suffix))
      return;
    payload.issues.push({
      origin: "string",
      code: "invalid_format",
      format: "ends_with",
      suffix: def.suffix,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
function handleCheckPropertyResult(result, payload, property) {
  if (result.issues.length) {
    payload.issues.push(...prefixIssues(property, result.issues));
  }
}
var $ZodCheckProperty = /* @__PURE__ */ $constructor("$ZodCheckProperty", (inst, def) => {
  $ZodCheck.init(inst, def);
  inst._zod.check = (payload) => {
    const result = def.schema._zod.run({
      value: payload.value[def.property],
      issues: []
    }, {});
    if (result instanceof Promise) {
      return result.then((result2) => handleCheckPropertyResult(result2, payload, def.property));
    }
    handleCheckPropertyResult(result, payload, def.property);
    return;
  };
});
var $ZodCheckMimeType = /* @__PURE__ */ $constructor("$ZodCheckMimeType", (inst, def) => {
  $ZodCheck.init(inst, def);
  const mimeSet = new Set(def.mime);
  inst._zod.onattach.push((inst2) => {
    inst2._zod.bag.mime = def.mime;
  });
  inst._zod.check = (payload) => {
    if (mimeSet.has(payload.value.type))
      return;
    payload.issues.push({
      code: "invalid_value",
      values: def.mime,
      input: payload.value.type,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCheckOverwrite = /* @__PURE__ */ $constructor("$ZodCheckOverwrite", (inst, def) => {
  $ZodCheck.init(inst, def);
  inst._zod.check = (payload) => {
    payload.value = def.tx(payload.value);
  };
});

// node_modules/zod/v4/core/doc.js
var Doc = class {
  constructor(args = []) {
    this.content = [];
    this.indent = 0;
    if (this)
      this.args = args;
  }
  indented(fn) {
    this.indent += 1;
    fn(this);
    this.indent -= 1;
  }
  write(arg) {
    if (typeof arg === "function") {
      arg(this, { execution: "sync" });
      arg(this, { execution: "async" });
      return;
    }
    const content = arg;
    const lines = content.split("\n").filter((x) => x);
    const minIndent = Math.min(...lines.map((x) => x.length - x.trimStart().length));
    const dedented = lines.map((x) => x.slice(minIndent)).map((x) => " ".repeat(this.indent * 2) + x);
    for (const line of dedented) {
      this.content.push(line);
    }
  }
  compile() {
    const F = Function;
    const args = this?.args;
    const content = this?.content ?? [``];
    const lines = [...content.map((x) => `  ${x}`)];
    return new F(...args, lines.join("\n"));
  }
};

// node_modules/zod/v4/core/versions.js
var version = {
  major: 4,
  minor: 4,
  patch: 3
};

// node_modules/zod/v4/core/schemas.js
var $ZodType = /* @__PURE__ */ $constructor("$ZodType", (inst, def) => {
  var _a3;
  inst ?? (inst = {});
  inst._zod.def = def;
  inst._zod.bag = inst._zod.bag || {};
  inst._zod.version = version;
  const checks = [...inst._zod.def.checks ?? []];
  if (inst._zod.traits.has("$ZodCheck")) {
    checks.unshift(inst);
  }
  for (const ch of checks) {
    for (const fn of ch._zod.onattach) {
      fn(inst);
    }
  }
  if (checks.length === 0) {
    (_a3 = inst._zod).deferred ?? (_a3.deferred = []);
    inst._zod.deferred?.push(() => {
      inst._zod.run = inst._zod.parse;
    });
  } else {
    const runChecks = (payload, checks2, ctx) => {
      let isAborted = aborted(payload);
      let asyncResult;
      for (const ch of checks2) {
        if (ch._zod.def.when) {
          if (explicitlyAborted(payload))
            continue;
          const shouldRun = ch._zod.def.when(payload);
          if (!shouldRun)
            continue;
        } else if (isAborted) {
          continue;
        }
        const currLen = payload.issues.length;
        const _ = ch._zod.check(payload);
        if (_ instanceof Promise && ctx?.async === false) {
          throw new $ZodAsyncError();
        }
        if (asyncResult || _ instanceof Promise) {
          asyncResult = (asyncResult ?? Promise.resolve()).then(async () => {
            await _;
            const nextLen = payload.issues.length;
            if (nextLen === currLen)
              return;
            if (!isAborted)
              isAborted = aborted(payload, currLen);
          });
        } else {
          const nextLen = payload.issues.length;
          if (nextLen === currLen)
            continue;
          if (!isAborted)
            isAborted = aborted(payload, currLen);
        }
      }
      if (asyncResult) {
        return asyncResult.then(() => {
          return payload;
        });
      }
      return payload;
    };
    const handleCanaryResult = (canary, payload, ctx) => {
      if (aborted(canary)) {
        canary.aborted = true;
        return canary;
      }
      const checkResult = runChecks(payload, checks, ctx);
      if (checkResult instanceof Promise) {
        if (ctx.async === false)
          throw new $ZodAsyncError();
        return checkResult.then((checkResult2) => inst._zod.parse(checkResult2, ctx));
      }
      return inst._zod.parse(checkResult, ctx);
    };
    inst._zod.run = (payload, ctx) => {
      if (ctx.skipChecks) {
        return inst._zod.parse(payload, ctx);
      }
      if (ctx.direction === "backward") {
        const canary = inst._zod.parse({ value: payload.value, issues: [] }, { ...ctx, skipChecks: true });
        if (canary instanceof Promise) {
          return canary.then((canary2) => {
            return handleCanaryResult(canary2, payload, ctx);
          });
        }
        return handleCanaryResult(canary, payload, ctx);
      }
      const result = inst._zod.parse(payload, ctx);
      if (result instanceof Promise) {
        if (ctx.async === false)
          throw new $ZodAsyncError();
        return result.then((result2) => runChecks(result2, checks, ctx));
      }
      return runChecks(result, checks, ctx);
    };
  }
  defineLazy(inst, "~standard", () => ({
    validate: (value) => {
      try {
        const r = safeParse(inst, value);
        return r.success ? { value: r.data } : { issues: r.error?.issues };
      } catch (_) {
        return safeParseAsync(inst, value).then((r) => r.success ? { value: r.data } : { issues: r.error?.issues });
      }
    },
    vendor: "zod",
    version: 1
  }));
});
var $ZodString = /* @__PURE__ */ $constructor("$ZodString", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = [...inst?._zod.bag?.patterns ?? []].pop() ?? string(inst._zod.bag);
  inst._zod.parse = (payload, _) => {
    if (def.coerce)
      try {
        payload.value = String(payload.value);
      } catch (_2) {
      }
    if (typeof payload.value === "string")
      return payload;
    payload.issues.push({
      expected: "string",
      code: "invalid_type",
      input: payload.value,
      inst
    });
    return payload;
  };
});
var $ZodStringFormat = /* @__PURE__ */ $constructor("$ZodStringFormat", (inst, def) => {
  $ZodCheckStringFormat.init(inst, def);
  $ZodString.init(inst, def);
});
var $ZodGUID = /* @__PURE__ */ $constructor("$ZodGUID", (inst, def) => {
  def.pattern ?? (def.pattern = guid);
  $ZodStringFormat.init(inst, def);
});
var $ZodUUID = /* @__PURE__ */ $constructor("$ZodUUID", (inst, def) => {
  if (def.version) {
    const versionMap = {
      v1: 1,
      v2: 2,
      v3: 3,
      v4: 4,
      v5: 5,
      v6: 6,
      v7: 7,
      v8: 8
    };
    const v = versionMap[def.version];
    if (v === void 0)
      throw new Error(`Invalid UUID version: "${def.version}"`);
    def.pattern ?? (def.pattern = uuid(v));
  } else
    def.pattern ?? (def.pattern = uuid());
  $ZodStringFormat.init(inst, def);
});
var $ZodEmail = /* @__PURE__ */ $constructor("$ZodEmail", (inst, def) => {
  def.pattern ?? (def.pattern = email);
  $ZodStringFormat.init(inst, def);
});
var $ZodURL = /* @__PURE__ */ $constructor("$ZodURL", (inst, def) => {
  $ZodStringFormat.init(inst, def);
  inst._zod.check = (payload) => {
    try {
      const trimmed = payload.value.trim();
      if (!def.normalize && def.protocol?.source === httpProtocol.source) {
        if (!/^https?:\/\//i.test(trimmed)) {
          payload.issues.push({
            code: "invalid_format",
            format: "url",
            note: "Invalid URL format",
            input: payload.value,
            inst,
            continue: !def.abort
          });
          return;
        }
      }
      const url2 = new URL(trimmed);
      if (def.hostname) {
        def.hostname.lastIndex = 0;
        if (!def.hostname.test(url2.hostname)) {
          payload.issues.push({
            code: "invalid_format",
            format: "url",
            note: "Invalid hostname",
            pattern: def.hostname.source,
            input: payload.value,
            inst,
            continue: !def.abort
          });
        }
      }
      if (def.protocol) {
        def.protocol.lastIndex = 0;
        if (!def.protocol.test(url2.protocol.endsWith(":") ? url2.protocol.slice(0, -1) : url2.protocol)) {
          payload.issues.push({
            code: "invalid_format",
            format: "url",
            note: "Invalid protocol",
            pattern: def.protocol.source,
            input: payload.value,
            inst,
            continue: !def.abort
          });
        }
      }
      if (def.normalize) {
        payload.value = url2.href;
      } else {
        payload.value = trimmed;
      }
      return;
    } catch (_) {
      payload.issues.push({
        code: "invalid_format",
        format: "url",
        input: payload.value,
        inst,
        continue: !def.abort
      });
    }
  };
});
var $ZodEmoji = /* @__PURE__ */ $constructor("$ZodEmoji", (inst, def) => {
  def.pattern ?? (def.pattern = emoji());
  $ZodStringFormat.init(inst, def);
});
var $ZodNanoID = /* @__PURE__ */ $constructor("$ZodNanoID", (inst, def) => {
  def.pattern ?? (def.pattern = nanoid);
  $ZodStringFormat.init(inst, def);
});
var $ZodCUID = /* @__PURE__ */ $constructor("$ZodCUID", (inst, def) => {
  def.pattern ?? (def.pattern = cuid);
  $ZodStringFormat.init(inst, def);
});
var $ZodCUID2 = /* @__PURE__ */ $constructor("$ZodCUID2", (inst, def) => {
  def.pattern ?? (def.pattern = cuid2);
  $ZodStringFormat.init(inst, def);
});
var $ZodULID = /* @__PURE__ */ $constructor("$ZodULID", (inst, def) => {
  def.pattern ?? (def.pattern = ulid);
  $ZodStringFormat.init(inst, def);
});
var $ZodXID = /* @__PURE__ */ $constructor("$ZodXID", (inst, def) => {
  def.pattern ?? (def.pattern = xid);
  $ZodStringFormat.init(inst, def);
});
var $ZodKSUID = /* @__PURE__ */ $constructor("$ZodKSUID", (inst, def) => {
  def.pattern ?? (def.pattern = ksuid);
  $ZodStringFormat.init(inst, def);
});
var $ZodISODateTime = /* @__PURE__ */ $constructor("$ZodISODateTime", (inst, def) => {
  def.pattern ?? (def.pattern = datetime(def));
  $ZodStringFormat.init(inst, def);
});
var $ZodISODate = /* @__PURE__ */ $constructor("$ZodISODate", (inst, def) => {
  def.pattern ?? (def.pattern = date);
  $ZodStringFormat.init(inst, def);
});
var $ZodISOTime = /* @__PURE__ */ $constructor("$ZodISOTime", (inst, def) => {
  def.pattern ?? (def.pattern = time(def));
  $ZodStringFormat.init(inst, def);
});
var $ZodISODuration = /* @__PURE__ */ $constructor("$ZodISODuration", (inst, def) => {
  def.pattern ?? (def.pattern = duration);
  $ZodStringFormat.init(inst, def);
});
var $ZodIPv4 = /* @__PURE__ */ $constructor("$ZodIPv4", (inst, def) => {
  def.pattern ?? (def.pattern = ipv4);
  $ZodStringFormat.init(inst, def);
  inst._zod.bag.format = `ipv4`;
});
var $ZodIPv6 = /* @__PURE__ */ $constructor("$ZodIPv6", (inst, def) => {
  def.pattern ?? (def.pattern = ipv6);
  $ZodStringFormat.init(inst, def);
  inst._zod.bag.format = `ipv6`;
  inst._zod.check = (payload) => {
    try {
      new URL(`http://[${payload.value}]`);
    } catch {
      payload.issues.push({
        code: "invalid_format",
        format: "ipv6",
        input: payload.value,
        inst,
        continue: !def.abort
      });
    }
  };
});
var $ZodMAC = /* @__PURE__ */ $constructor("$ZodMAC", (inst, def) => {
  def.pattern ?? (def.pattern = mac(def.delimiter));
  $ZodStringFormat.init(inst, def);
  inst._zod.bag.format = `mac`;
});
var $ZodCIDRv4 = /* @__PURE__ */ $constructor("$ZodCIDRv4", (inst, def) => {
  def.pattern ?? (def.pattern = cidrv4);
  $ZodStringFormat.init(inst, def);
});
var $ZodCIDRv6 = /* @__PURE__ */ $constructor("$ZodCIDRv6", (inst, def) => {
  def.pattern ?? (def.pattern = cidrv6);
  $ZodStringFormat.init(inst, def);
  inst._zod.check = (payload) => {
    const parts = payload.value.split("/");
    try {
      if (parts.length !== 2)
        throw new Error();
      const [address, prefix] = parts;
      if (!prefix)
        throw new Error();
      const prefixNum = Number(prefix);
      if (`${prefixNum}` !== prefix)
        throw new Error();
      if (prefixNum < 0 || prefixNum > 128)
        throw new Error();
      new URL(`http://[${address}]`);
    } catch {
      payload.issues.push({
        code: "invalid_format",
        format: "cidrv6",
        input: payload.value,
        inst,
        continue: !def.abort
      });
    }
  };
});
function isValidBase64(data) {
  if (data === "")
    return true;
  if (/\s/.test(data))
    return false;
  if (data.length % 4 !== 0)
    return false;
  try {
    atob(data);
    return true;
  } catch {
    return false;
  }
}
var $ZodBase64 = /* @__PURE__ */ $constructor("$ZodBase64", (inst, def) => {
  def.pattern ?? (def.pattern = base64);
  $ZodStringFormat.init(inst, def);
  inst._zod.bag.contentEncoding = "base64";
  inst._zod.check = (payload) => {
    if (isValidBase64(payload.value))
      return;
    payload.issues.push({
      code: "invalid_format",
      format: "base64",
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
function isValidBase64URL(data) {
  if (!base64url.test(data))
    return false;
  const base643 = data.replace(/[-_]/g, (c) => c === "-" ? "+" : "/");
  const padded = base643.padEnd(Math.ceil(base643.length / 4) * 4, "=");
  return isValidBase64(padded);
}
var $ZodBase64URL = /* @__PURE__ */ $constructor("$ZodBase64URL", (inst, def) => {
  def.pattern ?? (def.pattern = base64url);
  $ZodStringFormat.init(inst, def);
  inst._zod.bag.contentEncoding = "base64url";
  inst._zod.check = (payload) => {
    if (isValidBase64URL(payload.value))
      return;
    payload.issues.push({
      code: "invalid_format",
      format: "base64url",
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodE164 = /* @__PURE__ */ $constructor("$ZodE164", (inst, def) => {
  def.pattern ?? (def.pattern = e164);
  $ZodStringFormat.init(inst, def);
});
function isValidJWT(token, algorithm = null) {
  try {
    const tokensParts = token.split(".");
    if (tokensParts.length !== 3)
      return false;
    const [header] = tokensParts;
    if (!header)
      return false;
    const parsedHeader = JSON.parse(atob(header));
    if ("typ" in parsedHeader && parsedHeader?.typ !== "JWT")
      return false;
    if (!parsedHeader.alg)
      return false;
    if (algorithm && (!("alg" in parsedHeader) || parsedHeader.alg !== algorithm))
      return false;
    return true;
  } catch {
    return false;
  }
}
var $ZodJWT = /* @__PURE__ */ $constructor("$ZodJWT", (inst, def) => {
  $ZodStringFormat.init(inst, def);
  inst._zod.check = (payload) => {
    if (isValidJWT(payload.value, def.alg))
      return;
    payload.issues.push({
      code: "invalid_format",
      format: "jwt",
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodCustomStringFormat = /* @__PURE__ */ $constructor("$ZodCustomStringFormat", (inst, def) => {
  $ZodStringFormat.init(inst, def);
  inst._zod.check = (payload) => {
    if (def.fn(payload.value))
      return;
    payload.issues.push({
      code: "invalid_format",
      format: def.format,
      input: payload.value,
      inst,
      continue: !def.abort
    });
  };
});
var $ZodNumber = /* @__PURE__ */ $constructor("$ZodNumber", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = inst._zod.bag.pattern ?? number;
  inst._zod.parse = (payload, _ctx) => {
    if (def.coerce)
      try {
        payload.value = Number(payload.value);
      } catch (_) {
      }
    const input = payload.value;
    if (typeof input === "number" && !Number.isNaN(input) && Number.isFinite(input)) {
      return payload;
    }
    const received = typeof input === "number" ? Number.isNaN(input) ? "NaN" : !Number.isFinite(input) ? "Infinity" : void 0 : void 0;
    payload.issues.push({
      expected: "number",
      code: "invalid_type",
      input,
      inst,
      ...received ? { received } : {}
    });
    return payload;
  };
});
var $ZodNumberFormat = /* @__PURE__ */ $constructor("$ZodNumberFormat", (inst, def) => {
  $ZodCheckNumberFormat.init(inst, def);
  $ZodNumber.init(inst, def);
});
var $ZodBoolean = /* @__PURE__ */ $constructor("$ZodBoolean", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = boolean;
  inst._zod.parse = (payload, _ctx) => {
    if (def.coerce)
      try {
        payload.value = Boolean(payload.value);
      } catch (_) {
      }
    const input = payload.value;
    if (typeof input === "boolean")
      return payload;
    payload.issues.push({
      expected: "boolean",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodBigInt = /* @__PURE__ */ $constructor("$ZodBigInt", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = bigint;
  inst._zod.parse = (payload, _ctx) => {
    if (def.coerce)
      try {
        payload.value = BigInt(payload.value);
      } catch (_) {
      }
    if (typeof payload.value === "bigint")
      return payload;
    payload.issues.push({
      expected: "bigint",
      code: "invalid_type",
      input: payload.value,
      inst
    });
    return payload;
  };
});
var $ZodBigIntFormat = /* @__PURE__ */ $constructor("$ZodBigIntFormat", (inst, def) => {
  $ZodCheckBigIntFormat.init(inst, def);
  $ZodBigInt.init(inst, def);
});
var $ZodSymbol = /* @__PURE__ */ $constructor("$ZodSymbol", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (typeof input === "symbol")
      return payload;
    payload.issues.push({
      expected: "symbol",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodUndefined = /* @__PURE__ */ $constructor("$ZodUndefined", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = _undefined;
  inst._zod.values = /* @__PURE__ */ new Set([void 0]);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (typeof input === "undefined")
      return payload;
    payload.issues.push({
      expected: "undefined",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodNull = /* @__PURE__ */ $constructor("$ZodNull", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.pattern = _null;
  inst._zod.values = /* @__PURE__ */ new Set([null]);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (input === null)
      return payload;
    payload.issues.push({
      expected: "null",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodAny = /* @__PURE__ */ $constructor("$ZodAny", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload) => payload;
});
var $ZodUnknown = /* @__PURE__ */ $constructor("$ZodUnknown", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload) => payload;
});
var $ZodNever = /* @__PURE__ */ $constructor("$ZodNever", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    payload.issues.push({
      expected: "never",
      code: "invalid_type",
      input: payload.value,
      inst
    });
    return payload;
  };
});
var $ZodVoid = /* @__PURE__ */ $constructor("$ZodVoid", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (typeof input === "undefined")
      return payload;
    payload.issues.push({
      expected: "void",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodDate = /* @__PURE__ */ $constructor("$ZodDate", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    if (def.coerce) {
      try {
        payload.value = new Date(payload.value);
      } catch (_err) {
      }
    }
    const input = payload.value;
    const isDate = input instanceof Date;
    const isValidDate = isDate && !Number.isNaN(input.getTime());
    if (isValidDate)
      return payload;
    payload.issues.push({
      expected: "date",
      code: "invalid_type",
      input,
      ...isDate ? { received: "Invalid Date" } : {},
      inst
    });
    return payload;
  };
});
function handleArrayResult(result, final, index) {
  if (result.issues.length) {
    final.issues.push(...prefixIssues(index, result.issues));
  }
  final.value[index] = result.value;
}
var $ZodArray = /* @__PURE__ */ $constructor("$ZodArray", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!Array.isArray(input)) {
      payload.issues.push({
        expected: "array",
        code: "invalid_type",
        input,
        inst
      });
      return payload;
    }
    payload.value = Array(input.length);
    const proms = [];
    for (let i = 0; i < input.length; i++) {
      const item = input[i];
      const result = def.element._zod.run({
        value: item,
        issues: []
      }, ctx);
      if (result instanceof Promise) {
        proms.push(result.then((result2) => handleArrayResult(result2, payload, i)));
      } else {
        handleArrayResult(result, payload, i);
      }
    }
    if (proms.length) {
      return Promise.all(proms).then(() => payload);
    }
    return payload;
  };
});
function handlePropertyResult(result, final, key, input, isOptionalIn, isOptionalOut) {
  const isPresent = key in input;
  if (result.issues.length) {
    if (isOptionalIn && isOptionalOut && !isPresent) {
      return;
    }
    final.issues.push(...prefixIssues(key, result.issues));
  }
  if (!isPresent && !isOptionalIn) {
    if (!result.issues.length) {
      final.issues.push({
        code: "invalid_type",
        expected: "nonoptional",
        input: void 0,
        path: [key]
      });
    }
    return;
  }
  if (result.value === void 0) {
    if (isPresent) {
      final.value[key] = void 0;
    }
  } else {
    final.value[key] = result.value;
  }
}
function normalizeDef(def) {
  const keys = Object.keys(def.shape);
  for (const k of keys) {
    if (!def.shape?.[k]?._zod?.traits?.has("$ZodType")) {
      throw new Error(`Invalid element at key "${k}": expected a Zod schema`);
    }
  }
  const okeys = optionalKeys(def.shape);
  return {
    ...def,
    keys,
    keySet: new Set(keys),
    numKeys: keys.length,
    optionalKeys: new Set(okeys)
  };
}
function handleCatchall(proms, input, payload, ctx, def, inst) {
  const unrecognized = [];
  const keySet = def.keySet;
  const _catchall = def.catchall._zod;
  const t = _catchall.def.type;
  const isOptionalIn = _catchall.optin === "optional";
  const isOptionalOut = _catchall.optout === "optional";
  for (const key in input) {
    if (key === "__proto__")
      continue;
    if (keySet.has(key))
      continue;
    if (t === "never") {
      unrecognized.push(key);
      continue;
    }
    const r = _catchall.run({ value: input[key], issues: [] }, ctx);
    if (r instanceof Promise) {
      proms.push(r.then((r2) => handlePropertyResult(r2, payload, key, input, isOptionalIn, isOptionalOut)));
    } else {
      handlePropertyResult(r, payload, key, input, isOptionalIn, isOptionalOut);
    }
  }
  if (unrecognized.length) {
    payload.issues.push({
      code: "unrecognized_keys",
      keys: unrecognized,
      input,
      inst
    });
  }
  if (!proms.length)
    return payload;
  return Promise.all(proms).then(() => {
    return payload;
  });
}
var $ZodObject = /* @__PURE__ */ $constructor("$ZodObject", (inst, def) => {
  $ZodType.init(inst, def);
  const desc = Object.getOwnPropertyDescriptor(def, "shape");
  if (!desc?.get) {
    const sh = def.shape;
    Object.defineProperty(def, "shape", {
      get: () => {
        const newSh = { ...sh };
        Object.defineProperty(def, "shape", {
          value: newSh
        });
        return newSh;
      }
    });
  }
  const _normalized = cached(() => normalizeDef(def));
  defineLazy(inst._zod, "propValues", () => {
    const shape = def.shape;
    const propValues = {};
    for (const key in shape) {
      const field = shape[key]._zod;
      if (field.values) {
        propValues[key] ?? (propValues[key] = /* @__PURE__ */ new Set());
        for (const v of field.values)
          propValues[key].add(v);
      }
    }
    return propValues;
  });
  const isObject2 = isObject;
  const catchall = def.catchall;
  let value;
  inst._zod.parse = (payload, ctx) => {
    value ?? (value = _normalized.value);
    const input = payload.value;
    if (!isObject2(input)) {
      payload.issues.push({
        expected: "object",
        code: "invalid_type",
        input,
        inst
      });
      return payload;
    }
    payload.value = {};
    const proms = [];
    const shape = value.shape;
    for (const key of value.keys) {
      const el = shape[key];
      const isOptionalIn = el._zod.optin === "optional";
      const isOptionalOut = el._zod.optout === "optional";
      const r = el._zod.run({ value: input[key], issues: [] }, ctx);
      if (r instanceof Promise) {
        proms.push(r.then((r2) => handlePropertyResult(r2, payload, key, input, isOptionalIn, isOptionalOut)));
      } else {
        handlePropertyResult(r, payload, key, input, isOptionalIn, isOptionalOut);
      }
    }
    if (!catchall) {
      return proms.length ? Promise.all(proms).then(() => payload) : payload;
    }
    return handleCatchall(proms, input, payload, ctx, _normalized.value, inst);
  };
});
var $ZodObjectJIT = /* @__PURE__ */ $constructor("$ZodObjectJIT", (inst, def) => {
  $ZodObject.init(inst, def);
  const superParse = inst._zod.parse;
  const _normalized = cached(() => normalizeDef(def));
  const generateFastpass = (shape) => {
    const doc = new Doc(["shape", "payload", "ctx"]);
    const normalized = _normalized.value;
    const parseStr = (key) => {
      const k = esc(key);
      return `shape[${k}]._zod.run({ value: input[${k}], issues: [] }, ctx)`;
    };
    doc.write(`const input = payload.value;`);
    const ids = /* @__PURE__ */ Object.create(null);
    let counter = 0;
    for (const key of normalized.keys) {
      ids[key] = `key_${counter++}`;
    }
    doc.write(`const newResult = {};`);
    for (const key of normalized.keys) {
      const id = ids[key];
      const k = esc(key);
      const schema = shape[key];
      const isOptionalIn = schema?._zod?.optin === "optional";
      const isOptionalOut = schema?._zod?.optout === "optional";
      doc.write(`const ${id} = ${parseStr(key)};`);
      if (isOptionalIn && isOptionalOut) {
        doc.write(`
        if (${id}.issues.length) {
          if (${k} in input) {
            payload.issues = payload.issues.concat(${id}.issues.map(iss => ({
              ...iss,
              path: iss.path ? [${k}, ...iss.path] : [${k}]
            })));
          }
        }
        
        if (${id}.value === undefined) {
          if (${k} in input) {
            newResult[${k}] = undefined;
          }
        } else {
          newResult[${k}] = ${id}.value;
        }
        
      `);
      } else if (!isOptionalIn) {
        doc.write(`
        const ${id}_present = ${k} in input;
        if (${id}.issues.length) {
          payload.issues = payload.issues.concat(${id}.issues.map(iss => ({
            ...iss,
            path: iss.path ? [${k}, ...iss.path] : [${k}]
          })));
        }
        if (!${id}_present && !${id}.issues.length) {
          payload.issues.push({
            code: "invalid_type",
            expected: "nonoptional",
            input: undefined,
            path: [${k}]
          });
        }

        if (${id}_present) {
          if (${id}.value === undefined) {
            newResult[${k}] = undefined;
          } else {
            newResult[${k}] = ${id}.value;
          }
        }

      `);
      } else {
        doc.write(`
        if (${id}.issues.length) {
          payload.issues = payload.issues.concat(${id}.issues.map(iss => ({
            ...iss,
            path: iss.path ? [${k}, ...iss.path] : [${k}]
          })));
        }
        
        if (${id}.value === undefined) {
          if (${k} in input) {
            newResult[${k}] = undefined;
          }
        } else {
          newResult[${k}] = ${id}.value;
        }
        
      `);
      }
    }
    doc.write(`payload.value = newResult;`);
    doc.write(`return payload;`);
    const fn = doc.compile();
    return (payload, ctx) => fn(shape, payload, ctx);
  };
  let fastpass;
  const isObject2 = isObject;
  const jit = !globalConfig.jitless;
  const allowsEval2 = allowsEval;
  const fastEnabled = jit && allowsEval2.value;
  const catchall = def.catchall;
  let value;
  inst._zod.parse = (payload, ctx) => {
    value ?? (value = _normalized.value);
    const input = payload.value;
    if (!isObject2(input)) {
      payload.issues.push({
        expected: "object",
        code: "invalid_type",
        input,
        inst
      });
      return payload;
    }
    if (jit && fastEnabled && ctx?.async === false && ctx.jitless !== true) {
      if (!fastpass)
        fastpass = generateFastpass(def.shape);
      payload = fastpass(payload, ctx);
      if (!catchall)
        return payload;
      return handleCatchall([], input, payload, ctx, value, inst);
    }
    return superParse(payload, ctx);
  };
});
function handleUnionResults(results, final, inst, ctx) {
  for (const result of results) {
    if (result.issues.length === 0) {
      final.value = result.value;
      return final;
    }
  }
  const nonaborted = results.filter((r) => !aborted(r));
  if (nonaborted.length === 1) {
    final.value = nonaborted[0].value;
    return nonaborted[0];
  }
  final.issues.push({
    code: "invalid_union",
    input: final.value,
    inst,
    errors: results.map((result) => result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
  });
  return final;
}
var $ZodUnion = /* @__PURE__ */ $constructor("$ZodUnion", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "optin", () => def.options.some((o) => o._zod.optin === "optional") ? "optional" : void 0);
  defineLazy(inst._zod, "optout", () => def.options.some((o) => o._zod.optout === "optional") ? "optional" : void 0);
  defineLazy(inst._zod, "values", () => {
    if (def.options.every((o) => o._zod.values)) {
      return new Set(def.options.flatMap((option) => Array.from(option._zod.values)));
    }
    return void 0;
  });
  defineLazy(inst._zod, "pattern", () => {
    if (def.options.every((o) => o._zod.pattern)) {
      const patterns = def.options.map((o) => o._zod.pattern);
      return new RegExp(`^(${patterns.map((p) => cleanRegex(p.source)).join("|")})$`);
    }
    return void 0;
  });
  const first = def.options.length === 1 ? def.options[0]._zod.run : null;
  inst._zod.parse = (payload, ctx) => {
    if (first) {
      return first(payload, ctx);
    }
    let async = false;
    const results = [];
    for (const option of def.options) {
      const result = option._zod.run({
        value: payload.value,
        issues: []
      }, ctx);
      if (result instanceof Promise) {
        results.push(result);
        async = true;
      } else {
        if (result.issues.length === 0)
          return result;
        results.push(result);
      }
    }
    if (!async)
      return handleUnionResults(results, payload, inst, ctx);
    return Promise.all(results).then((results2) => {
      return handleUnionResults(results2, payload, inst, ctx);
    });
  };
});
function handleExclusiveUnionResults(results, final, inst, ctx) {
  const successes = results.filter((r) => r.issues.length === 0);
  if (successes.length === 1) {
    final.value = successes[0].value;
    return final;
  }
  if (successes.length === 0) {
    final.issues.push({
      code: "invalid_union",
      input: final.value,
      inst,
      errors: results.map((result) => result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
    });
  } else {
    final.issues.push({
      code: "invalid_union",
      input: final.value,
      inst,
      errors: [],
      inclusive: false
    });
  }
  return final;
}
var $ZodXor = /* @__PURE__ */ $constructor("$ZodXor", (inst, def) => {
  $ZodUnion.init(inst, def);
  def.inclusive = false;
  const first = def.options.length === 1 ? def.options[0]._zod.run : null;
  inst._zod.parse = (payload, ctx) => {
    if (first) {
      return first(payload, ctx);
    }
    let async = false;
    const results = [];
    for (const option of def.options) {
      const result = option._zod.run({
        value: payload.value,
        issues: []
      }, ctx);
      if (result instanceof Promise) {
        results.push(result);
        async = true;
      } else {
        results.push(result);
      }
    }
    if (!async)
      return handleExclusiveUnionResults(results, payload, inst, ctx);
    return Promise.all(results).then((results2) => {
      return handleExclusiveUnionResults(results2, payload, inst, ctx);
    });
  };
});
var $ZodDiscriminatedUnion = /* @__PURE__ */ $constructor("$ZodDiscriminatedUnion", (inst, def) => {
  def.inclusive = false;
  $ZodUnion.init(inst, def);
  const _super = inst._zod.parse;
  defineLazy(inst._zod, "propValues", () => {
    const propValues = {};
    for (const option of def.options) {
      const pv = option._zod.propValues;
      if (!pv || Object.keys(pv).length === 0)
        throw new Error(`Invalid discriminated union option at index "${def.options.indexOf(option)}"`);
      for (const [k, v] of Object.entries(pv)) {
        if (!propValues[k])
          propValues[k] = /* @__PURE__ */ new Set();
        for (const val of v) {
          propValues[k].add(val);
        }
      }
    }
    return propValues;
  });
  const disc = cached(() => {
    const opts = def.options;
    const map2 = /* @__PURE__ */ new Map();
    for (const o of opts) {
      const values = o._zod.propValues?.[def.discriminator];
      if (!values || values.size === 0)
        throw new Error(`Invalid discriminated union option at index "${def.options.indexOf(o)}"`);
      for (const v of values) {
        if (map2.has(v)) {
          throw new Error(`Duplicate discriminator value "${String(v)}"`);
        }
        map2.set(v, o);
      }
    }
    return map2;
  });
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!isObject(input)) {
      payload.issues.push({
        code: "invalid_type",
        expected: "object",
        input,
        inst
      });
      return payload;
    }
    const opt = disc.value.get(input?.[def.discriminator]);
    if (opt) {
      return opt._zod.run(payload, ctx);
    }
    if (def.unionFallback || ctx.direction === "backward") {
      return _super(payload, ctx);
    }
    payload.issues.push({
      code: "invalid_union",
      errors: [],
      note: "No matching discriminator",
      discriminator: def.discriminator,
      options: Array.from(disc.value.keys()),
      input,
      path: [def.discriminator],
      inst
    });
    return payload;
  };
});
var $ZodIntersection = /* @__PURE__ */ $constructor("$ZodIntersection", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    const left = def.left._zod.run({ value: input, issues: [] }, ctx);
    const right = def.right._zod.run({ value: input, issues: [] }, ctx);
    const async = left instanceof Promise || right instanceof Promise;
    if (async) {
      return Promise.all([left, right]).then(([left2, right2]) => {
        return handleIntersectionResults(payload, left2, right2);
      });
    }
    return handleIntersectionResults(payload, left, right);
  };
});
function mergeValues(a, b) {
  if (a === b) {
    return { valid: true, data: a };
  }
  if (a instanceof Date && b instanceof Date && +a === +b) {
    return { valid: true, data: a };
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const bKeys = Object.keys(b);
    const sharedKeys = Object.keys(a).filter((key) => bKeys.indexOf(key) !== -1);
    const newObj = { ...a, ...b };
    for (const key of sharedKeys) {
      const sharedValue = mergeValues(a[key], b[key]);
      if (!sharedValue.valid) {
        return {
          valid: false,
          mergeErrorPath: [key, ...sharedValue.mergeErrorPath]
        };
      }
      newObj[key] = sharedValue.data;
    }
    return { valid: true, data: newObj };
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) {
      return { valid: false, mergeErrorPath: [] };
    }
    const newArray = [];
    for (let index = 0; index < a.length; index++) {
      const itemA = a[index];
      const itemB = b[index];
      const sharedValue = mergeValues(itemA, itemB);
      if (!sharedValue.valid) {
        return {
          valid: false,
          mergeErrorPath: [index, ...sharedValue.mergeErrorPath]
        };
      }
      newArray.push(sharedValue.data);
    }
    return { valid: true, data: newArray };
  }
  return { valid: false, mergeErrorPath: [] };
}
function handleIntersectionResults(result, left, right) {
  const unrecKeys = /* @__PURE__ */ new Map();
  let unrecIssue;
  for (const iss of left.issues) {
    if (iss.code === "unrecognized_keys") {
      unrecIssue ?? (unrecIssue = iss);
      for (const k of iss.keys) {
        if (!unrecKeys.has(k))
          unrecKeys.set(k, {});
        unrecKeys.get(k).l = true;
      }
    } else {
      result.issues.push(iss);
    }
  }
  for (const iss of right.issues) {
    if (iss.code === "unrecognized_keys") {
      for (const k of iss.keys) {
        if (!unrecKeys.has(k))
          unrecKeys.set(k, {});
        unrecKeys.get(k).r = true;
      }
    } else {
      result.issues.push(iss);
    }
  }
  const bothKeys = [...unrecKeys].filter(([, f]) => f.l && f.r).map(([k]) => k);
  if (bothKeys.length && unrecIssue) {
    result.issues.push({ ...unrecIssue, keys: bothKeys });
  }
  if (aborted(result))
    return result;
  const merged = mergeValues(left.value, right.value);
  if (!merged.valid) {
    throw new Error(`Unmergable intersection. Error path: ${JSON.stringify(merged.mergeErrorPath)}`);
  }
  result.value = merged.data;
  return result;
}
var $ZodTuple = /* @__PURE__ */ $constructor("$ZodTuple", (inst, def) => {
  $ZodType.init(inst, def);
  const items = def.items;
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!Array.isArray(input)) {
      payload.issues.push({
        input,
        inst,
        expected: "tuple",
        code: "invalid_type"
      });
      return payload;
    }
    payload.value = [];
    const proms = [];
    const optinStart = getTupleOptStart(items, "optin");
    const optoutStart = getTupleOptStart(items, "optout");
    if (!def.rest) {
      if (input.length < optinStart) {
        payload.issues.push({
          code: "too_small",
          minimum: optinStart,
          inclusive: true,
          input,
          inst,
          origin: "array"
        });
        return payload;
      }
      if (input.length > items.length) {
        payload.issues.push({
          code: "too_big",
          maximum: items.length,
          inclusive: true,
          input,
          inst,
          origin: "array"
        });
      }
    }
    const itemResults = new Array(items.length);
    for (let i = 0; i < items.length; i++) {
      const r = items[i]._zod.run({ value: input[i], issues: [] }, ctx);
      if (r instanceof Promise) {
        proms.push(r.then((rr) => {
          itemResults[i] = rr;
        }));
      } else {
        itemResults[i] = r;
      }
    }
    if (def.rest) {
      let i = items.length - 1;
      const rest = input.slice(items.length);
      for (const el of rest) {
        i++;
        const result = def.rest._zod.run({ value: el, issues: [] }, ctx);
        if (result instanceof Promise) {
          proms.push(result.then((r) => handleTupleResult(r, payload, i)));
        } else {
          handleTupleResult(result, payload, i);
        }
      }
    }
    if (proms.length) {
      return Promise.all(proms).then(() => handleTupleResults(itemResults, payload, items, input, optoutStart));
    }
    return handleTupleResults(itemResults, payload, items, input, optoutStart);
  };
});
function getTupleOptStart(items, key) {
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i]._zod[key] !== "optional")
      return i + 1;
  }
  return 0;
}
function handleTupleResult(result, final, index) {
  if (result.issues.length) {
    final.issues.push(...prefixIssues(index, result.issues));
  }
  final.value[index] = result.value;
}
function handleTupleResults(itemResults, final, items, input, optoutStart) {
  for (let i = 0; i < items.length; i++) {
    const r = itemResults[i];
    const isPresent = i < input.length;
    if (r.issues.length) {
      if (!isPresent && i >= optoutStart) {
        final.value.length = i;
        break;
      }
      final.issues.push(...prefixIssues(i, r.issues));
    }
    final.value[i] = r.value;
  }
  for (let i = final.value.length - 1; i >= input.length; i--) {
    if (items[i]._zod.optout === "optional" && final.value[i] === void 0) {
      final.value.length = i;
    } else {
      break;
    }
  }
  return final;
}
var $ZodRecord = /* @__PURE__ */ $constructor("$ZodRecord", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!isPlainObject(input)) {
      payload.issues.push({
        expected: "record",
        code: "invalid_type",
        input,
        inst
      });
      return payload;
    }
    const proms = [];
    const values = def.keyType._zod.values;
    if (values) {
      payload.value = {};
      const recordKeys = /* @__PURE__ */ new Set();
      for (const key of values) {
        if (typeof key === "string" || typeof key === "number" || typeof key === "symbol") {
          recordKeys.add(typeof key === "number" ? key.toString() : key);
          const keyResult = def.keyType._zod.run({ value: key, issues: [] }, ctx);
          if (keyResult instanceof Promise) {
            throw new Error("Async schemas not supported in object keys currently");
          }
          if (keyResult.issues.length) {
            payload.issues.push({
              code: "invalid_key",
              origin: "record",
              issues: keyResult.issues.map((iss) => finalizeIssue(iss, ctx, config())),
              input: key,
              path: [key],
              inst
            });
            continue;
          }
          const outKey = keyResult.value;
          const result = def.valueType._zod.run({ value: input[key], issues: [] }, ctx);
          if (result instanceof Promise) {
            proms.push(result.then((result2) => {
              if (result2.issues.length) {
                payload.issues.push(...prefixIssues(key, result2.issues));
              }
              payload.value[outKey] = result2.value;
            }));
          } else {
            if (result.issues.length) {
              payload.issues.push(...prefixIssues(key, result.issues));
            }
            payload.value[outKey] = result.value;
          }
        }
      }
      let unrecognized;
      for (const key in input) {
        if (!recordKeys.has(key)) {
          unrecognized = unrecognized ?? [];
          unrecognized.push(key);
        }
      }
      if (unrecognized && unrecognized.length > 0) {
        payload.issues.push({
          code: "unrecognized_keys",
          input,
          inst,
          keys: unrecognized
        });
      }
    } else {
      payload.value = {};
      for (const key of Reflect.ownKeys(input)) {
        if (key === "__proto__")
          continue;
        if (!Object.prototype.propertyIsEnumerable.call(input, key))
          continue;
        let keyResult = def.keyType._zod.run({ value: key, issues: [] }, ctx);
        if (keyResult instanceof Promise) {
          throw new Error("Async schemas not supported in object keys currently");
        }
        const checkNumericKey = typeof key === "string" && number.test(key) && keyResult.issues.length;
        if (checkNumericKey) {
          const retryResult = def.keyType._zod.run({ value: Number(key), issues: [] }, ctx);
          if (retryResult instanceof Promise) {
            throw new Error("Async schemas not supported in object keys currently");
          }
          if (retryResult.issues.length === 0) {
            keyResult = retryResult;
          }
        }
        if (keyResult.issues.length) {
          if (def.mode === "loose") {
            payload.value[key] = input[key];
          } else {
            payload.issues.push({
              code: "invalid_key",
              origin: "record",
              issues: keyResult.issues.map((iss) => finalizeIssue(iss, ctx, config())),
              input: key,
              path: [key],
              inst
            });
          }
          continue;
        }
        const result = def.valueType._zod.run({ value: input[key], issues: [] }, ctx);
        if (result instanceof Promise) {
          proms.push(result.then((result2) => {
            if (result2.issues.length) {
              payload.issues.push(...prefixIssues(key, result2.issues));
            }
            payload.value[keyResult.value] = result2.value;
          }));
        } else {
          if (result.issues.length) {
            payload.issues.push(...prefixIssues(key, result.issues));
          }
          payload.value[keyResult.value] = result.value;
        }
      }
    }
    if (proms.length) {
      return Promise.all(proms).then(() => payload);
    }
    return payload;
  };
});
var $ZodMap = /* @__PURE__ */ $constructor("$ZodMap", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!(input instanceof Map)) {
      payload.issues.push({
        expected: "map",
        code: "invalid_type",
        input,
        inst
      });
      return payload;
    }
    const proms = [];
    payload.value = /* @__PURE__ */ new Map();
    for (const [key, value] of input) {
      const keyResult = def.keyType._zod.run({ value: key, issues: [] }, ctx);
      const valueResult = def.valueType._zod.run({ value, issues: [] }, ctx);
      if (keyResult instanceof Promise || valueResult instanceof Promise) {
        proms.push(Promise.all([keyResult, valueResult]).then(([keyResult2, valueResult2]) => {
          handleMapResult(keyResult2, valueResult2, payload, key, input, inst, ctx);
        }));
      } else {
        handleMapResult(keyResult, valueResult, payload, key, input, inst, ctx);
      }
    }
    if (proms.length)
      return Promise.all(proms).then(() => payload);
    return payload;
  };
});
function handleMapResult(keyResult, valueResult, final, key, input, inst, ctx) {
  if (keyResult.issues.length) {
    if (propertyKeyTypes.has(typeof key)) {
      final.issues.push(...prefixIssues(key, keyResult.issues));
    } else {
      final.issues.push({
        code: "invalid_key",
        origin: "map",
        input,
        inst,
        issues: keyResult.issues.map((iss) => finalizeIssue(iss, ctx, config()))
      });
    }
  }
  if (valueResult.issues.length) {
    if (propertyKeyTypes.has(typeof key)) {
      final.issues.push(...prefixIssues(key, valueResult.issues));
    } else {
      final.issues.push({
        origin: "map",
        code: "invalid_element",
        input,
        inst,
        key,
        issues: valueResult.issues.map((iss) => finalizeIssue(iss, ctx, config()))
      });
    }
  }
  final.value.set(keyResult.value, valueResult.value);
}
var $ZodSet = /* @__PURE__ */ $constructor("$ZodSet", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    const input = payload.value;
    if (!(input instanceof Set)) {
      payload.issues.push({
        input,
        inst,
        expected: "set",
        code: "invalid_type"
      });
      return payload;
    }
    const proms = [];
    payload.value = /* @__PURE__ */ new Set();
    for (const item of input) {
      const result = def.valueType._zod.run({ value: item, issues: [] }, ctx);
      if (result instanceof Promise) {
        proms.push(result.then((result2) => handleSetResult(result2, payload)));
      } else
        handleSetResult(result, payload);
    }
    if (proms.length)
      return Promise.all(proms).then(() => payload);
    return payload;
  };
});
function handleSetResult(result, final) {
  if (result.issues.length) {
    final.issues.push(...result.issues);
  }
  final.value.add(result.value);
}
var $ZodEnum = /* @__PURE__ */ $constructor("$ZodEnum", (inst, def) => {
  $ZodType.init(inst, def);
  const values = getEnumValues(def.entries);
  const valuesSet = new Set(values);
  inst._zod.values = valuesSet;
  inst._zod.pattern = new RegExp(`^(${values.filter((k) => propertyKeyTypes.has(typeof k)).map((o) => typeof o === "string" ? escapeRegex(o) : o.toString()).join("|")})$`);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (valuesSet.has(input)) {
      return payload;
    }
    payload.issues.push({
      code: "invalid_value",
      values,
      input,
      inst
    });
    return payload;
  };
});
var $ZodLiteral = /* @__PURE__ */ $constructor("$ZodLiteral", (inst, def) => {
  $ZodType.init(inst, def);
  if (def.values.length === 0) {
    throw new Error("Cannot create literal schema with no valid values");
  }
  const values = new Set(def.values);
  inst._zod.values = values;
  inst._zod.pattern = new RegExp(`^(${def.values.map((o) => typeof o === "string" ? escapeRegex(o) : o ? escapeRegex(o.toString()) : String(o)).join("|")})$`);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (values.has(input)) {
      return payload;
    }
    payload.issues.push({
      code: "invalid_value",
      values: def.values,
      input,
      inst
    });
    return payload;
  };
});
var $ZodFile = /* @__PURE__ */ $constructor("$ZodFile", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    const input = payload.value;
    if (input instanceof File)
      return payload;
    payload.issues.push({
      expected: "file",
      code: "invalid_type",
      input,
      inst
    });
    return payload;
  };
});
var $ZodTransform = /* @__PURE__ */ $constructor("$ZodTransform", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.optin = "optional";
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      throw new $ZodEncodeError(inst.constructor.name);
    }
    const _out = def.transform(payload.value, payload);
    if (ctx.async) {
      const output = _out instanceof Promise ? _out : Promise.resolve(_out);
      return output.then((output2) => {
        payload.value = output2;
        payload.fallback = true;
        return payload;
      });
    }
    if (_out instanceof Promise) {
      throw new $ZodAsyncError();
    }
    payload.value = _out;
    payload.fallback = true;
    return payload;
  };
});
function handleOptionalResult(result, input) {
  if (input === void 0 && (result.issues.length || result.fallback)) {
    return { issues: [], value: void 0 };
  }
  return result;
}
var $ZodOptional = /* @__PURE__ */ $constructor("$ZodOptional", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.optin = "optional";
  inst._zod.optout = "optional";
  defineLazy(inst._zod, "values", () => {
    return def.innerType._zod.values ? /* @__PURE__ */ new Set([...def.innerType._zod.values, void 0]) : void 0;
  });
  defineLazy(inst._zod, "pattern", () => {
    const pattern = def.innerType._zod.pattern;
    return pattern ? new RegExp(`^(${cleanRegex(pattern.source)})?$`) : void 0;
  });
  inst._zod.parse = (payload, ctx) => {
    if (def.innerType._zod.optin === "optional") {
      const input = payload.value;
      const result = def.innerType._zod.run(payload, ctx);
      if (result instanceof Promise)
        return result.then((r) => handleOptionalResult(r, input));
      return handleOptionalResult(result, input);
    }
    if (payload.value === void 0) {
      return payload;
    }
    return def.innerType._zod.run(payload, ctx);
  };
});
var $ZodExactOptional = /* @__PURE__ */ $constructor("$ZodExactOptional", (inst, def) => {
  $ZodOptional.init(inst, def);
  defineLazy(inst._zod, "values", () => def.innerType._zod.values);
  defineLazy(inst._zod, "pattern", () => def.innerType._zod.pattern);
  inst._zod.parse = (payload, ctx) => {
    return def.innerType._zod.run(payload, ctx);
  };
});
var $ZodNullable = /* @__PURE__ */ $constructor("$ZodNullable", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "optin", () => def.innerType._zod.optin);
  defineLazy(inst._zod, "optout", () => def.innerType._zod.optout);
  defineLazy(inst._zod, "pattern", () => {
    const pattern = def.innerType._zod.pattern;
    return pattern ? new RegExp(`^(${cleanRegex(pattern.source)}|null)$`) : void 0;
  });
  defineLazy(inst._zod, "values", () => {
    return def.innerType._zod.values ? /* @__PURE__ */ new Set([...def.innerType._zod.values, null]) : void 0;
  });
  inst._zod.parse = (payload, ctx) => {
    if (payload.value === null)
      return payload;
    return def.innerType._zod.run(payload, ctx);
  };
});
var $ZodDefault = /* @__PURE__ */ $constructor("$ZodDefault", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.optin = "optional";
  defineLazy(inst._zod, "values", () => def.innerType._zod.values);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      return def.innerType._zod.run(payload, ctx);
    }
    if (payload.value === void 0) {
      payload.value = def.defaultValue;
      return payload;
    }
    const result = def.innerType._zod.run(payload, ctx);
    if (result instanceof Promise) {
      return result.then((result2) => handleDefaultResult(result2, def));
    }
    return handleDefaultResult(result, def);
  };
});
function handleDefaultResult(payload, def) {
  if (payload.value === void 0) {
    payload.value = def.defaultValue;
  }
  return payload;
}
var $ZodPrefault = /* @__PURE__ */ $constructor("$ZodPrefault", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.optin = "optional";
  defineLazy(inst._zod, "values", () => def.innerType._zod.values);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      return def.innerType._zod.run(payload, ctx);
    }
    if (payload.value === void 0) {
      payload.value = def.defaultValue;
    }
    return def.innerType._zod.run(payload, ctx);
  };
});
var $ZodNonOptional = /* @__PURE__ */ $constructor("$ZodNonOptional", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "values", () => {
    const v = def.innerType._zod.values;
    return v ? new Set([...v].filter((x) => x !== void 0)) : void 0;
  });
  inst._zod.parse = (payload, ctx) => {
    const result = def.innerType._zod.run(payload, ctx);
    if (result instanceof Promise) {
      return result.then((result2) => handleNonOptionalResult(result2, inst));
    }
    return handleNonOptionalResult(result, inst);
  };
});
function handleNonOptionalResult(payload, inst) {
  if (!payload.issues.length && payload.value === void 0) {
    payload.issues.push({
      code: "invalid_type",
      expected: "nonoptional",
      input: payload.value,
      inst
    });
  }
  return payload;
}
var $ZodSuccess = /* @__PURE__ */ $constructor("$ZodSuccess", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      throw new $ZodEncodeError("ZodSuccess");
    }
    const result = def.innerType._zod.run(payload, ctx);
    if (result instanceof Promise) {
      return result.then((result2) => {
        payload.value = result2.issues.length === 0;
        return payload;
      });
    }
    payload.value = result.issues.length === 0;
    return payload;
  };
});
var $ZodCatch = /* @__PURE__ */ $constructor("$ZodCatch", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.optin = "optional";
  defineLazy(inst._zod, "optout", () => def.innerType._zod.optout);
  defineLazy(inst._zod, "values", () => def.innerType._zod.values);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      return def.innerType._zod.run(payload, ctx);
    }
    const result = def.innerType._zod.run(payload, ctx);
    if (result instanceof Promise) {
      return result.then((result2) => {
        payload.value = result2.value;
        if (result2.issues.length) {
          payload.value = def.catchValue({
            ...payload,
            error: {
              issues: result2.issues.map((iss) => finalizeIssue(iss, ctx, config()))
            },
            input: payload.value
          });
          payload.issues = [];
          payload.fallback = true;
        }
        return payload;
      });
    }
    payload.value = result.value;
    if (result.issues.length) {
      payload.value = def.catchValue({
        ...payload,
        error: {
          issues: result.issues.map((iss) => finalizeIssue(iss, ctx, config()))
        },
        input: payload.value
      });
      payload.issues = [];
      payload.fallback = true;
    }
    return payload;
  };
});
var $ZodNaN = /* @__PURE__ */ $constructor("$ZodNaN", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _ctx) => {
    if (typeof payload.value !== "number" || !Number.isNaN(payload.value)) {
      payload.issues.push({
        input: payload.value,
        inst,
        expected: "nan",
        code: "invalid_type"
      });
      return payload;
    }
    return payload;
  };
});
var $ZodPipe = /* @__PURE__ */ $constructor("$ZodPipe", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "values", () => def.in._zod.values);
  defineLazy(inst._zod, "optin", () => def.in._zod.optin);
  defineLazy(inst._zod, "optout", () => def.out._zod.optout);
  defineLazy(inst._zod, "propValues", () => def.in._zod.propValues);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      const right = def.out._zod.run(payload, ctx);
      if (right instanceof Promise) {
        return right.then((right2) => handlePipeResult(right2, def.in, ctx));
      }
      return handlePipeResult(right, def.in, ctx);
    }
    const left = def.in._zod.run(payload, ctx);
    if (left instanceof Promise) {
      return left.then((left2) => handlePipeResult(left2, def.out, ctx));
    }
    return handlePipeResult(left, def.out, ctx);
  };
});
function handlePipeResult(left, next, ctx) {
  if (left.issues.length) {
    left.aborted = true;
    return left;
  }
  return next._zod.run({ value: left.value, issues: left.issues, fallback: left.fallback }, ctx);
}
var $ZodCodec = /* @__PURE__ */ $constructor("$ZodCodec", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "values", () => def.in._zod.values);
  defineLazy(inst._zod, "optin", () => def.in._zod.optin);
  defineLazy(inst._zod, "optout", () => def.out._zod.optout);
  defineLazy(inst._zod, "propValues", () => def.in._zod.propValues);
  inst._zod.parse = (payload, ctx) => {
    const direction = ctx.direction || "forward";
    if (direction === "forward") {
      const left = def.in._zod.run(payload, ctx);
      if (left instanceof Promise) {
        return left.then((left2) => handleCodecAResult(left2, def, ctx));
      }
      return handleCodecAResult(left, def, ctx);
    } else {
      const right = def.out._zod.run(payload, ctx);
      if (right instanceof Promise) {
        return right.then((right2) => handleCodecAResult(right2, def, ctx));
      }
      return handleCodecAResult(right, def, ctx);
    }
  };
});
function handleCodecAResult(result, def, ctx) {
  if (result.issues.length) {
    result.aborted = true;
    return result;
  }
  const direction = ctx.direction || "forward";
  if (direction === "forward") {
    const transformed = def.transform(result.value, result);
    if (transformed instanceof Promise) {
      return transformed.then((value) => handleCodecTxResult(result, value, def.out, ctx));
    }
    return handleCodecTxResult(result, transformed, def.out, ctx);
  } else {
    const transformed = def.reverseTransform(result.value, result);
    if (transformed instanceof Promise) {
      return transformed.then((value) => handleCodecTxResult(result, value, def.in, ctx));
    }
    return handleCodecTxResult(result, transformed, def.in, ctx);
  }
}
function handleCodecTxResult(left, value, nextSchema, ctx) {
  if (left.issues.length) {
    left.aborted = true;
    return left;
  }
  return nextSchema._zod.run({ value, issues: left.issues }, ctx);
}
var $ZodPreprocess = /* @__PURE__ */ $constructor("$ZodPreprocess", (inst, def) => {
  $ZodPipe.init(inst, def);
});
var $ZodReadonly = /* @__PURE__ */ $constructor("$ZodReadonly", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "propValues", () => def.innerType._zod.propValues);
  defineLazy(inst._zod, "values", () => def.innerType._zod.values);
  defineLazy(inst._zod, "optin", () => def.innerType?._zod?.optin);
  defineLazy(inst._zod, "optout", () => def.innerType?._zod?.optout);
  inst._zod.parse = (payload, ctx) => {
    if (ctx.direction === "backward") {
      return def.innerType._zod.run(payload, ctx);
    }
    const result = def.innerType._zod.run(payload, ctx);
    if (result instanceof Promise) {
      return result.then(handleReadonlyResult);
    }
    return handleReadonlyResult(result);
  };
});
function handleReadonlyResult(payload) {
  payload.value = Object.freeze(payload.value);
  return payload;
}
var $ZodTemplateLiteral = /* @__PURE__ */ $constructor("$ZodTemplateLiteral", (inst, def) => {
  $ZodType.init(inst, def);
  const regexParts = [];
  for (const part of def.parts) {
    if (typeof part === "object" && part !== null) {
      if (!part._zod.pattern) {
        throw new Error(`Invalid template literal part, no pattern found: ${[...part._zod.traits].shift()}`);
      }
      const source = part._zod.pattern instanceof RegExp ? part._zod.pattern.source : part._zod.pattern;
      if (!source)
        throw new Error(`Invalid template literal part: ${part._zod.traits}`);
      const start = source.startsWith("^") ? 1 : 0;
      const end = source.endsWith("$") ? source.length - 1 : source.length;
      regexParts.push(source.slice(start, end));
    } else if (part === null || primitiveTypes.has(typeof part)) {
      regexParts.push(escapeRegex(`${part}`));
    } else {
      throw new Error(`Invalid template literal part: ${part}`);
    }
  }
  inst._zod.pattern = new RegExp(`^${regexParts.join("")}$`);
  inst._zod.parse = (payload, _ctx) => {
    if (typeof payload.value !== "string") {
      payload.issues.push({
        input: payload.value,
        inst,
        expected: "string",
        code: "invalid_type"
      });
      return payload;
    }
    inst._zod.pattern.lastIndex = 0;
    if (!inst._zod.pattern.test(payload.value)) {
      payload.issues.push({
        input: payload.value,
        inst,
        code: "invalid_format",
        format: def.format ?? "template_literal",
        pattern: inst._zod.pattern.source
      });
      return payload;
    }
    return payload;
  };
});
var $ZodFunction = /* @__PURE__ */ $constructor("$ZodFunction", (inst, def) => {
  $ZodType.init(inst, def);
  inst._def = def;
  inst._zod.def = def;
  inst.implement = (func) => {
    if (typeof func !== "function") {
      throw new Error("implement() must be called with a function");
    }
    return function(...args) {
      const parsedArgs = inst._def.input ? parse(inst._def.input, args) : args;
      const result = Reflect.apply(func, this, parsedArgs);
      if (inst._def.output) {
        return parse(inst._def.output, result);
      }
      return result;
    };
  };
  inst.implementAsync = (func) => {
    if (typeof func !== "function") {
      throw new Error("implementAsync() must be called with a function");
    }
    return async function(...args) {
      const parsedArgs = inst._def.input ? await parseAsync(inst._def.input, args) : args;
      const result = await Reflect.apply(func, this, parsedArgs);
      if (inst._def.output) {
        return await parseAsync(inst._def.output, result);
      }
      return result;
    };
  };
  inst._zod.parse = (payload, _ctx) => {
    if (typeof payload.value !== "function") {
      payload.issues.push({
        code: "invalid_type",
        expected: "function",
        input: payload.value,
        inst
      });
      return payload;
    }
    const hasPromiseOutput = inst._def.output && inst._def.output._zod.def.type === "promise";
    if (hasPromiseOutput) {
      payload.value = inst.implementAsync(payload.value);
    } else {
      payload.value = inst.implement(payload.value);
    }
    return payload;
  };
  inst.input = (...args) => {
    const F = inst.constructor;
    if (Array.isArray(args[0])) {
      return new F({
        type: "function",
        input: new $ZodTuple({
          type: "tuple",
          items: args[0],
          rest: args[1]
        }),
        output: inst._def.output
      });
    }
    return new F({
      type: "function",
      input: args[0],
      output: inst._def.output
    });
  };
  inst.output = (output) => {
    const F = inst.constructor;
    return new F({
      type: "function",
      input: inst._def.input,
      output
    });
  };
  return inst;
});
var $ZodPromise = /* @__PURE__ */ $constructor("$ZodPromise", (inst, def) => {
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, ctx) => {
    return Promise.resolve(payload.value).then((inner) => def.innerType._zod.run({ value: inner, issues: [] }, ctx));
  };
});
var $ZodLazy = /* @__PURE__ */ $constructor("$ZodLazy", (inst, def) => {
  $ZodType.init(inst, def);
  defineLazy(inst._zod, "innerType", () => {
    const d = def;
    if (!d._cachedInner)
      d._cachedInner = def.getter();
    return d._cachedInner;
  });
  defineLazy(inst._zod, "pattern", () => inst._zod.innerType?._zod?.pattern);
  defineLazy(inst._zod, "propValues", () => inst._zod.innerType?._zod?.propValues);
  defineLazy(inst._zod, "optin", () => inst._zod.innerType?._zod?.optin ?? void 0);
  defineLazy(inst._zod, "optout", () => inst._zod.innerType?._zod?.optout ?? void 0);
  inst._zod.parse = (payload, ctx) => {
    const inner = inst._zod.innerType;
    return inner._zod.run(payload, ctx);
  };
});
var $ZodCustom = /* @__PURE__ */ $constructor("$ZodCustom", (inst, def) => {
  $ZodCheck.init(inst, def);
  $ZodType.init(inst, def);
  inst._zod.parse = (payload, _) => {
    return payload;
  };
  inst._zod.check = (payload) => {
    const input = payload.value;
    const r = def.fn(input);
    if (r instanceof Promise) {
      return r.then((r2) => handleRefineResult(r2, payload, input, inst));
    }
    handleRefineResult(r, payload, input, inst);
    return;
  };
});
function handleRefineResult(result, payload, input, inst) {
  if (!result) {
    const _iss = {
      code: "custom",
      input,
      inst,
      // incorporates params.error into issue reporting
      path: [...inst._zod.def.path ?? []],
      // incorporates params.error into issue reporting
      continue: !inst._zod.def.abort
      // params: inst._zod.def.params,
    };
    if (inst._zod.def.params)
      _iss.params = inst._zod.def.params;
    payload.issues.push(issue(_iss));
  }
}

// node_modules/zod/v4/locales/index.js
var locales_exports = {};
__export(locales_exports, {
  ar: () => ar_default,
  az: () => az_default,
  be: () => be_default,
  bg: () => bg_default,
  ca: () => ca_default,
  cs: () => cs_default,
  da: () => da_default,
  de: () => de_default,
  el: () => el_default,
  en: () => en_default,
  eo: () => eo_default,
  es: () => es_default,
  fa: () => fa_default,
  fi: () => fi_default,
  fr: () => fr_default,
  frCA: () => fr_CA_default,
  he: () => he_default,
  hr: () => hr_default,
  hu: () => hu_default,
  hy: () => hy_default,
  id: () => id_default,
  is: () => is_default,
  it: () => it_default,
  ja: () => ja_default,
  ka: () => ka_default,
  kh: () => kh_default,
  km: () => km_default,
  ko: () => ko_default,
  lt: () => lt_default,
  mk: () => mk_default,
  ms: () => ms_default,
  nl: () => nl_default,
  no: () => no_default,
  ota: () => ota_default,
  pl: () => pl_default,
  ps: () => ps_default,
  pt: () => pt_default,
  ro: () => ro_default,
  ru: () => ru_default,
  sl: () => sl_default,
  sv: () => sv_default,
  ta: () => ta_default,
  th: () => th_default,
  tr: () => tr_default,
  ua: () => ua_default,
  uk: () => uk_default,
  ur: () => ur_default,
  uz: () => uz_default,
  vi: () => vi_default,
  yo: () => yo_default,
  zhCN: () => zh_CN_default,
  zhTW: () => zh_TW_default
});

// node_modules/zod/v4/locales/ar.js
var error = () => {
  const Sizable = {
    string: { unit: "\u062D\u0631\u0641", verb: "\u0623\u0646 \u064A\u062D\u0648\u064A" },
    file: { unit: "\u0628\u0627\u064A\u062A", verb: "\u0623\u0646 \u064A\u062D\u0648\u064A" },
    array: { unit: "\u0639\u0646\u0635\u0631", verb: "\u0623\u0646 \u064A\u062D\u0648\u064A" },
    set: { unit: "\u0639\u0646\u0635\u0631", verb: "\u0623\u0646 \u064A\u062D\u0648\u064A" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0645\u062F\u062E\u0644",
    email: "\u0628\u0631\u064A\u062F \u0625\u0644\u0643\u062A\u0631\u0648\u0646\u064A",
    url: "\u0631\u0627\u0628\u0637",
    emoji: "\u0625\u064A\u0645\u0648\u062C\u064A",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u062A\u0627\u0631\u064A\u062E \u0648\u0648\u0642\u062A \u0628\u0645\u0639\u064A\u0627\u0631 ISO",
    date: "\u062A\u0627\u0631\u064A\u062E \u0628\u0645\u0639\u064A\u0627\u0631 ISO",
    time: "\u0648\u0642\u062A \u0628\u0645\u0639\u064A\u0627\u0631 ISO",
    duration: "\u0645\u062F\u0629 \u0628\u0645\u0639\u064A\u0627\u0631 ISO",
    ipv4: "\u0639\u0646\u0648\u0627\u0646 IPv4",
    ipv6: "\u0639\u0646\u0648\u0627\u0646 IPv6",
    cidrv4: "\u0645\u062F\u0649 \u0639\u0646\u0627\u0648\u064A\u0646 \u0628\u0635\u064A\u063A\u0629 IPv4",
    cidrv6: "\u0645\u062F\u0649 \u0639\u0646\u0627\u0648\u064A\u0646 \u0628\u0635\u064A\u063A\u0629 IPv6",
    base64: "\u0646\u064E\u0635 \u0628\u062A\u0631\u0645\u064A\u0632 base64-encoded",
    base64url: "\u0646\u064E\u0635 \u0628\u062A\u0631\u0645\u064A\u0632 base64url-encoded",
    json_string: "\u0646\u064E\u0635 \u0639\u0644\u0649 \u0647\u064A\u0626\u0629 JSON",
    e164: "\u0631\u0642\u0645 \u0647\u0627\u062A\u0641 \u0628\u0645\u0639\u064A\u0627\u0631 E.164",
    jwt: "JWT",
    template_literal: "\u0645\u062F\u062E\u0644"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0645\u062F\u062E\u0644\u0627\u062A \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644\u0629: \u064A\u0641\u062A\u0631\u0636 \u0625\u062F\u062E\u0627\u0644 instanceof ${issue3.expected}\u060C \u0648\u0644\u0643\u0646 \u062A\u0645 \u0625\u062F\u062E\u0627\u0644 ${received}`;
        }
        return `\u0645\u062F\u062E\u0644\u0627\u062A \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644\u0629: \u064A\u0641\u062A\u0631\u0636 \u0625\u062F\u062E\u0627\u0644 ${expected}\u060C \u0648\u0644\u0643\u0646 \u062A\u0645 \u0625\u062F\u062E\u0627\u0644 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u0645\u062F\u062E\u0644\u0627\u062A \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644\u0629: \u064A\u0641\u062A\u0631\u0636 \u0625\u062F\u062E\u0627\u0644 ${stringifyPrimitive(issue3.values[0])}`;
        return `\u0627\u062E\u062A\u064A\u0627\u0631 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062A\u0648\u0642\u0639 \u0627\u0646\u062A\u0642\u0627\u0621 \u0623\u062D\u062F \u0647\u0630\u0647 \u0627\u0644\u062E\u064A\u0627\u0631\u0627\u062A: ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return ` \u0623\u0643\u0628\u0631 \u0645\u0646 \u0627\u0644\u0644\u0627\u0632\u0645: \u064A\u0641\u062A\u0631\u0636 \u0623\u0646 \u062A\u0643\u0648\u0646 ${issue3.origin ?? "\u0627\u0644\u0642\u064A\u0645\u0629"} ${adj} ${issue3.maximum.toString()} ${sizing.unit ?? "\u0639\u0646\u0635\u0631"}`;
        return `\u0623\u0643\u0628\u0631 \u0645\u0646 \u0627\u0644\u0644\u0627\u0632\u0645: \u064A\u0641\u062A\u0631\u0636 \u0623\u0646 \u062A\u0643\u0648\u0646 ${issue3.origin ?? "\u0627\u0644\u0642\u064A\u0645\u0629"} ${adj} ${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0623\u0635\u063A\u0631 \u0645\u0646 \u0627\u0644\u0644\u0627\u0632\u0645: \u064A\u0641\u062A\u0631\u0636 \u0644\u0640 ${issue3.origin} \u0623\u0646 \u064A\u0643\u0648\u0646 ${adj} ${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u0623\u0635\u063A\u0631 \u0645\u0646 \u0627\u0644\u0644\u0627\u0632\u0645: \u064A\u0641\u062A\u0631\u0636 \u0644\u0640 ${issue3.origin} \u0623\u0646 \u064A\u0643\u0648\u0646 ${adj} ${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u0646\u064E\u0635 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062C\u0628 \u0623\u0646 \u064A\u0628\u062F\u0623 \u0628\u0640 "${issue3.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u0646\u064E\u0635 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062C\u0628 \u0623\u0646 \u064A\u0646\u062A\u0647\u064A \u0628\u0640 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u0646\u064E\u0635 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062C\u0628 \u0623\u0646 \u064A\u062A\u0636\u0645\u0651\u064E\u0646 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u0646\u064E\u0635 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062C\u0628 \u0623\u0646 \u064A\u0637\u0627\u0628\u0642 \u0627\u0644\u0646\u0645\u0637 ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644`;
      }
      case "not_multiple_of":
        return `\u0631\u0642\u0645 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644: \u064A\u062C\u0628 \u0623\u0646 \u064A\u0643\u0648\u0646 \u0645\u0646 \u0645\u0636\u0627\u0639\u0641\u0627\u062A ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u0645\u0639\u0631\u0641${issue3.keys.length > 1 ? "\u0627\u062A" : ""} \u063A\u0631\u064A\u0628${issue3.keys.length > 1 ? "\u0629" : ""}: ${joinValues(issue3.keys, "\u060C ")}`;
      case "invalid_key":
        return `\u0645\u0639\u0631\u0641 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644 \u0641\u064A ${issue3.origin}`;
      case "invalid_union":
        return "\u0645\u062F\u062E\u0644 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644";
      case "invalid_element":
        return `\u0645\u062F\u062E\u0644 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644 \u0641\u064A ${issue3.origin}`;
      default:
        return "\u0645\u062F\u062E\u0644 \u063A\u064A\u0631 \u0645\u0642\u0628\u0648\u0644";
    }
  };
};
function ar_default() {
  return {
    localeError: error()
  };
}

// node_modules/zod/v4/locales/az.js
var error2 = () => {
  const Sizable = {
    string: { unit: "simvol", verb: "olmal\u0131d\u0131r" },
    file: { unit: "bayt", verb: "olmal\u0131d\u0131r" },
    array: { unit: "element", verb: "olmal\u0131d\u0131r" },
    set: { unit: "element", verb: "olmal\u0131d\u0131r" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "email address",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO datetime",
    date: "ISO date",
    time: "ISO time",
    duration: "ISO duration",
    ipv4: "IPv4 address",
    ipv6: "IPv6 address",
    cidrv4: "IPv4 range",
    cidrv6: "IPv6 range",
    base64: "base64-encoded string",
    base64url: "base64url-encoded string",
    json_string: "JSON string",
    e164: "E.164 number",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Yanl\u0131\u015F d\u0259y\u0259r: g\xF6zl\u0259nil\u0259n instanceof ${issue3.expected}, daxil olan ${received}`;
        }
        return `Yanl\u0131\u015F d\u0259y\u0259r: g\xF6zl\u0259nil\u0259n ${expected}, daxil olan ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Yanl\u0131\u015F d\u0259y\u0259r: g\xF6zl\u0259nil\u0259n ${stringifyPrimitive(issue3.values[0])}`;
        return `Yanl\u0131\u015F se\xE7im: a\u015Fa\u011F\u0131dak\u0131lardan biri olmal\u0131d\u0131r: ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\xC7ox b\xF6y\xFCk: g\xF6zl\u0259nil\u0259n ${issue3.origin ?? "d\u0259y\u0259r"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "element"}`;
        return `\xC7ox b\xF6y\xFCk: g\xF6zl\u0259nil\u0259n ${issue3.origin ?? "d\u0259y\u0259r"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\xC7ox ki\xE7ik: g\xF6zl\u0259nil\u0259n ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        return `\xC7ox ki\xE7ik: g\xF6zl\u0259nil\u0259n ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Yanl\u0131\u015F m\u0259tn: "${_issue.prefix}" il\u0259 ba\u015Flamal\u0131d\u0131r`;
        if (_issue.format === "ends_with")
          return `Yanl\u0131\u015F m\u0259tn: "${_issue.suffix}" il\u0259 bitm\u0259lidir`;
        if (_issue.format === "includes")
          return `Yanl\u0131\u015F m\u0259tn: "${_issue.includes}" daxil olmal\u0131d\u0131r`;
        if (_issue.format === "regex")
          return `Yanl\u0131\u015F m\u0259tn: ${_issue.pattern} \u015Fablonuna uy\u011Fun olmal\u0131d\u0131r`;
        return `Yanl\u0131\u015F ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Yanl\u0131\u015F \u0259d\u0259d: ${issue3.divisor} il\u0259 b\xF6l\xFCn\u0259 bil\u0259n olmal\u0131d\u0131r`;
      case "unrecognized_keys":
        return `Tan\u0131nmayan a\xE7ar${issue3.keys.length > 1 ? "lar" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} daxilind\u0259 yanl\u0131\u015F a\xE7ar`;
      case "invalid_union":
        return "Yanl\u0131\u015F d\u0259y\u0259r";
      case "invalid_element":
        return `${issue3.origin} daxilind\u0259 yanl\u0131\u015F d\u0259y\u0259r`;
      default:
        return `Yanl\u0131\u015F d\u0259y\u0259r`;
    }
  };
};
function az_default() {
  return {
    localeError: error2()
  };
}

// node_modules/zod/v4/locales/be.js
function getBelarusianPlural(count, one, few, many) {
  const absCount = Math.abs(count);
  const lastDigit = absCount % 10;
  const lastTwoDigits = absCount % 100;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
    return many;
  }
  if (lastDigit === 1) {
    return one;
  }
  if (lastDigit >= 2 && lastDigit <= 4) {
    return few;
  }
  return many;
}
var error3 = () => {
  const Sizable = {
    string: {
      unit: {
        one: "\u0441\u0456\u043C\u0432\u0430\u043B",
        few: "\u0441\u0456\u043C\u0432\u0430\u043B\u044B",
        many: "\u0441\u0456\u043C\u0432\u0430\u043B\u0430\u045E"
      },
      verb: "\u043C\u0435\u0446\u044C"
    },
    array: {
      unit: {
        one: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442",
        few: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u044B",
        many: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u0430\u045E"
      },
      verb: "\u043C\u0435\u0446\u044C"
    },
    set: {
      unit: {
        one: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442",
        few: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u044B",
        many: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u0430\u045E"
      },
      verb: "\u043C\u0435\u0446\u044C"
    },
    file: {
      unit: {
        one: "\u0431\u0430\u0439\u0442",
        few: "\u0431\u0430\u0439\u0442\u044B",
        many: "\u0431\u0430\u0439\u0442\u0430\u045E"
      },
      verb: "\u043C\u0435\u0446\u044C"
    }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0443\u0432\u043E\u0434",
    email: "email \u0430\u0434\u0440\u0430\u0441",
    url: "URL",
    emoji: "\u044D\u043C\u043E\u0434\u0437\u0456",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0434\u0430\u0442\u0430 \u0456 \u0447\u0430\u0441",
    date: "ISO \u0434\u0430\u0442\u0430",
    time: "ISO \u0447\u0430\u0441",
    duration: "ISO \u043F\u0440\u0430\u0446\u044F\u0433\u043B\u0430\u0441\u0446\u044C",
    ipv4: "IPv4 \u0430\u0434\u0440\u0430\u0441",
    ipv6: "IPv6 \u0430\u0434\u0440\u0430\u0441",
    cidrv4: "IPv4 \u0434\u044B\u044F\u043F\u0430\u0437\u043E\u043D",
    cidrv6: "IPv6 \u0434\u044B\u044F\u043F\u0430\u0437\u043E\u043D",
    base64: "\u0440\u0430\u0434\u043E\u043A \u0443 \u0444\u0430\u0440\u043C\u0430\u0446\u0435 base64",
    base64url: "\u0440\u0430\u0434\u043E\u043A \u0443 \u0444\u0430\u0440\u043C\u0430\u0446\u0435 base64url",
    json_string: "JSON \u0440\u0430\u0434\u043E\u043A",
    e164: "\u043D\u0443\u043C\u0430\u0440 E.164",
    jwt: "JWT",
    template_literal: "\u0443\u0432\u043E\u0434"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u043B\u0456\u043A",
    array: "\u043C\u0430\u0441\u0456\u045E"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u045E\u0432\u043E\u0434: \u0447\u0430\u043A\u0430\u045E\u0441\u044F instanceof ${issue3.expected}, \u0430\u0442\u0440\u044B\u043C\u0430\u043D\u0430 ${received}`;
        }
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u045E\u0432\u043E\u0434: \u0447\u0430\u043A\u0430\u045E\u0441\u044F ${expected}, \u0430\u0442\u0440\u044B\u043C\u0430\u043D\u0430 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u045E\u0432\u043E\u0434: \u0447\u0430\u043A\u0430\u043B\u0430\u0441\u044F ${stringifyPrimitive(issue3.values[0])}`;
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u0432\u0430\u0440\u044B\u044F\u043D\u0442: \u0447\u0430\u043A\u0430\u045E\u0441\u044F \u0430\u0434\u0437\u0456\u043D \u0437 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const maxValue = Number(issue3.maximum);
          const unit = getBelarusianPlural(maxValue, sizing.unit.one, sizing.unit.few, sizing.unit.many);
          return `\u0417\u0430\u043D\u0430\u0434\u0442\u0430 \u0432\u044F\u043B\u0456\u043A\u0456: \u0447\u0430\u043A\u0430\u043B\u0430\u0441\u044F, \u0448\u0442\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u044D\u043D\u043D\u0435"} \u043F\u0430\u0432\u0456\u043D\u043D\u0430 ${sizing.verb} ${adj}${issue3.maximum.toString()} ${unit}`;
        }
        return `\u0417\u0430\u043D\u0430\u0434\u0442\u0430 \u0432\u044F\u043B\u0456\u043A\u0456: \u0447\u0430\u043A\u0430\u043B\u0430\u0441\u044F, \u0448\u0442\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u044D\u043D\u043D\u0435"} \u043F\u0430\u0432\u0456\u043D\u043D\u0430 \u0431\u044B\u0446\u044C ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const minValue = Number(issue3.minimum);
          const unit = getBelarusianPlural(minValue, sizing.unit.one, sizing.unit.few, sizing.unit.many);
          return `\u0417\u0430\u043D\u0430\u0434\u0442\u0430 \u043C\u0430\u043B\u044B: \u0447\u0430\u043A\u0430\u043B\u0430\u0441\u044F, \u0448\u0442\u043E ${issue3.origin} \u043F\u0430\u0432\u0456\u043D\u043D\u0430 ${sizing.verb} ${adj}${issue3.minimum.toString()} ${unit}`;
        }
        return `\u0417\u0430\u043D\u0430\u0434\u0442\u0430 \u043C\u0430\u043B\u044B: \u0447\u0430\u043A\u0430\u043B\u0430\u0441\u044F, \u0448\u0442\u043E ${issue3.origin} \u043F\u0430\u0432\u0456\u043D\u043D\u0430 \u0431\u044B\u0446\u044C ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u0440\u0430\u0434\u043E\u043A: \u043F\u0430\u0432\u0456\u043D\u0435\u043D \u043F\u0430\u0447\u044B\u043D\u0430\u0446\u0446\u0430 \u0437 "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u0440\u0430\u0434\u043E\u043A: \u043F\u0430\u0432\u0456\u043D\u0435\u043D \u0437\u0430\u043A\u0430\u043D\u0447\u0432\u0430\u0446\u0446\u0430 \u043D\u0430 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u0440\u0430\u0434\u043E\u043A: \u043F\u0430\u0432\u0456\u043D\u0435\u043D \u0437\u043C\u044F\u0448\u0447\u0430\u0446\u044C "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u0440\u0430\u0434\u043E\u043A: \u043F\u0430\u0432\u0456\u043D\u0435\u043D \u0430\u0434\u043F\u0430\u0432\u044F\u0434\u0430\u0446\u044C \u0448\u0430\u0431\u043B\u043E\u043D\u0443 ${_issue.pattern}`;
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u043B\u0456\u043A: \u043F\u0430\u0432\u0456\u043D\u0435\u043D \u0431\u044B\u0446\u044C \u043A\u0440\u0430\u0442\u043D\u044B\u043C ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u041D\u0435\u0440\u0430\u0441\u043F\u0430\u0437\u043D\u0430\u043D\u044B ${issue3.keys.length > 1 ? "\u043A\u043B\u044E\u0447\u044B" : "\u043A\u043B\u044E\u0447"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u043A\u043B\u044E\u0447 \u0443 ${issue3.origin}`;
      case "invalid_union":
        return "\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u045E\u0432\u043E\u0434";
      case "invalid_element":
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u0430\u0435 \u0437\u043D\u0430\u0447\u044D\u043D\u043D\u0435 \u045E ${issue3.origin}`;
      default:
        return `\u041D\u044F\u043F\u0440\u0430\u0432\u0456\u043B\u044C\u043D\u044B \u045E\u0432\u043E\u0434`;
    }
  };
};
function be_default() {
  return {
    localeError: error3()
  };
}

// node_modules/zod/v4/locales/bg.js
var error4 = () => {
  const Sizable = {
    string: { unit: "\u0441\u0438\u043C\u0432\u043E\u043B\u0430", verb: "\u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430" },
    file: { unit: "\u0431\u0430\u0439\u0442\u0430", verb: "\u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430" },
    array: { unit: "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0430", verb: "\u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430" },
    set: { unit: "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0430", verb: "\u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0432\u0445\u043E\u0434",
    email: "\u0438\u043C\u0435\u0439\u043B \u0430\u0434\u0440\u0435\u0441",
    url: "URL",
    emoji: "\u0435\u043C\u043E\u0434\u0436\u0438",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0432\u0440\u0435\u043C\u0435",
    date: "ISO \u0434\u0430\u0442\u0430",
    time: "ISO \u0432\u0440\u0435\u043C\u0435",
    duration: "ISO \u043F\u0440\u043E\u0434\u044A\u043B\u0436\u0438\u0442\u0435\u043B\u043D\u043E\u0441\u0442",
    ipv4: "IPv4 \u0430\u0434\u0440\u0435\u0441",
    ipv6: "IPv6 \u0430\u0434\u0440\u0435\u0441",
    cidrv4: "IPv4 \u0434\u0438\u0430\u043F\u0430\u0437\u043E\u043D",
    cidrv6: "IPv6 \u0434\u0438\u0430\u043F\u0430\u0437\u043E\u043D",
    base64: "base64-\u043A\u043E\u0434\u0438\u0440\u0430\u043D \u043D\u0438\u0437",
    base64url: "base64url-\u043A\u043E\u0434\u0438\u0440\u0430\u043D \u043D\u0438\u0437",
    json_string: "JSON \u043D\u0438\u0437",
    e164: "E.164 \u043D\u043E\u043C\u0435\u0440",
    jwt: "JWT",
    template_literal: "\u0432\u0445\u043E\u0434"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0447\u0438\u0441\u043B\u043E",
    array: "\u043C\u0430\u0441\u0438\u0432"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u0432\u0445\u043E\u0434: \u043E\u0447\u0430\u043A\u0432\u0430\u043D instanceof ${issue3.expected}, \u043F\u043E\u043B\u0443\u0447\u0435\u043D ${received}`;
        }
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u0432\u0445\u043E\u0434: \u043E\u0447\u0430\u043A\u0432\u0430\u043D ${expected}, \u043F\u043E\u043B\u0443\u0447\u0435\u043D ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u0432\u0445\u043E\u0434: \u043E\u0447\u0430\u043A\u0432\u0430\u043D ${stringifyPrimitive(issue3.values[0])}`;
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u0430 \u043E\u043F\u0446\u0438\u044F: \u043E\u0447\u0430\u043A\u0432\u0430\u043D\u043E \u0435\u0434\u043D\u043E \u043E\u0442 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u0422\u0432\u044A\u0440\u0434\u0435 \u0433\u043E\u043B\u044F\u043C\u043E: \u043E\u0447\u0430\u043A\u0432\u0430 \u0441\u0435 ${issue3.origin ?? "\u0441\u0442\u043E\u0439\u043D\u043E\u0441\u0442"} \u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430 ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0430"}`;
        return `\u0422\u0432\u044A\u0440\u0434\u0435 \u0433\u043E\u043B\u044F\u043C\u043E: \u043E\u0447\u0430\u043A\u0432\u0430 \u0441\u0435 ${issue3.origin ?? "\u0441\u0442\u043E\u0439\u043D\u043E\u0441\u0442"} \u0434\u0430 \u0431\u044A\u0434\u0435 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0422\u0432\u044A\u0440\u0434\u0435 \u043C\u0430\u043B\u043A\u043E: \u043E\u0447\u0430\u043A\u0432\u0430 \u0441\u0435 ${issue3.origin} \u0434\u0430 \u0441\u044A\u0434\u044A\u0440\u0436\u0430 ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u0422\u0432\u044A\u0440\u0434\u0435 \u043C\u0430\u043B\u043A\u043E: \u043E\u0447\u0430\u043A\u0432\u0430 \u0441\u0435 ${issue3.origin} \u0434\u0430 \u0431\u044A\u0434\u0435 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u043D\u0438\u0437: \u0442\u0440\u044F\u0431\u0432\u0430 \u0434\u0430 \u0437\u0430\u043F\u043E\u0447\u0432\u0430 \u0441 "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u043D\u0438\u0437: \u0442\u0440\u044F\u0431\u0432\u0430 \u0434\u0430 \u0437\u0430\u0432\u044A\u0440\u0448\u0432\u0430 \u0441 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u043D\u0438\u0437: \u0442\u0440\u044F\u0431\u0432\u0430 \u0434\u0430 \u0432\u043A\u043B\u044E\u0447\u0432\u0430 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u043D\u0438\u0437: \u0442\u0440\u044F\u0431\u0432\u0430 \u0434\u0430 \u0441\u044A\u0432\u043F\u0430\u0434\u0430 \u0441 ${_issue.pattern}`;
        let invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D";
        if (_issue.format === "emoji")
          invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u043E";
        if (_issue.format === "datetime")
          invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u043E";
        if (_issue.format === "date")
          invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u0430";
        if (_issue.format === "time")
          invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u043E";
        if (_issue.format === "duration")
          invalid_adj = "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u0430";
        return `${invalid_adj} ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u043E \u0447\u0438\u0441\u043B\u043E: \u0442\u0440\u044F\u0431\u0432\u0430 \u0434\u0430 \u0431\u044A\u0434\u0435 \u043A\u0440\u0430\u0442\u043D\u043E \u043D\u0430 ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u041D\u0435\u0440\u0430\u0437\u043F\u043E\u0437\u043D\u0430\u0442${issue3.keys.length > 1 ? "\u0438" : ""} \u043A\u043B\u044E\u0447${issue3.keys.length > 1 ? "\u043E\u0432\u0435" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u043A\u043B\u044E\u0447 \u0432 ${issue3.origin}`;
      case "invalid_union":
        return "\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u0432\u0445\u043E\u0434";
      case "invalid_element":
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u043D\u0430 \u0441\u0442\u043E\u0439\u043D\u043E\u0441\u0442 \u0432 ${issue3.origin}`;
      default:
        return `\u041D\u0435\u0432\u0430\u043B\u0438\u0434\u0435\u043D \u0432\u0445\u043E\u0434`;
    }
  };
};
function bg_default() {
  return {
    localeError: error4()
  };
}

// node_modules/zod/v4/locales/ca.js
var error5 = () => {
  const Sizable = {
    string: { unit: "car\xE0cters", verb: "contenir" },
    file: { unit: "bytes", verb: "contenir" },
    array: { unit: "elements", verb: "contenir" },
    set: { unit: "elements", verb: "contenir" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "entrada",
    email: "adre\xE7a electr\xF2nica",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "data i hora ISO",
    date: "data ISO",
    time: "hora ISO",
    duration: "durada ISO",
    ipv4: "adre\xE7a IPv4",
    ipv6: "adre\xE7a IPv6",
    cidrv4: "rang IPv4",
    cidrv6: "rang IPv6",
    base64: "cadena codificada en base64",
    base64url: "cadena codificada en base64url",
    json_string: "cadena JSON",
    e164: "n\xFAmero E.164",
    jwt: "JWT",
    template_literal: "entrada"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Tipus inv\xE0lid: s'esperava instanceof ${issue3.expected}, s'ha rebut ${received}`;
        }
        return `Tipus inv\xE0lid: s'esperava ${expected}, s'ha rebut ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Valor inv\xE0lid: s'esperava ${stringifyPrimitive(issue3.values[0])}`;
        return `Opci\xF3 inv\xE0lida: s'esperava una de ${joinValues(issue3.values, " o ")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "com a m\xE0xim" : "menys de";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Massa gran: s'esperava que ${issue3.origin ?? "el valor"} contingu\xE9s ${adj} ${issue3.maximum.toString()} ${sizing.unit ?? "elements"}`;
        return `Massa gran: s'esperava que ${issue3.origin ?? "el valor"} fos ${adj} ${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? "com a m\xEDnim" : "m\xE9s de";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Massa petit: s'esperava que ${issue3.origin} contingu\xE9s ${adj} ${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Massa petit: s'esperava que ${issue3.origin} fos ${adj} ${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Format inv\xE0lid: ha de comen\xE7ar amb "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Format inv\xE0lid: ha d'acabar amb "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Format inv\xE0lid: ha d'incloure "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Format inv\xE0lid: ha de coincidir amb el patr\xF3 ${_issue.pattern}`;
        return `Format inv\xE0lid per a ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `N\xFAmero inv\xE0lid: ha de ser m\xFAltiple de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Clau${issue3.keys.length > 1 ? "s" : ""} no reconeguda${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Clau inv\xE0lida a ${issue3.origin}`;
      case "invalid_union":
        return "Entrada inv\xE0lida";
      // Could also be "Tipus d'unió invàlid" but "Entrada invàlida" is more general
      case "invalid_element":
        return `Element inv\xE0lid a ${issue3.origin}`;
      default:
        return `Entrada inv\xE0lida`;
    }
  };
};
function ca_default() {
  return {
    localeError: error5()
  };
}

// node_modules/zod/v4/locales/cs.js
var error6 = () => {
  const Sizable = {
    string: { unit: "znak\u016F", verb: "m\xEDt" },
    file: { unit: "bajt\u016F", verb: "m\xEDt" },
    array: { unit: "prvk\u016F", verb: "m\xEDt" },
    set: { unit: "prvk\u016F", verb: "m\xEDt" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "regul\xE1rn\xED v\xFDraz",
    email: "e-mailov\xE1 adresa",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "datum a \u010Das ve form\xE1tu ISO",
    date: "datum ve form\xE1tu ISO",
    time: "\u010Das ve form\xE1tu ISO",
    duration: "doba trv\xE1n\xED ISO",
    ipv4: "IPv4 adresa",
    ipv6: "IPv6 adresa",
    cidrv4: "rozsah IPv4",
    cidrv6: "rozsah IPv6",
    base64: "\u0159et\u011Bzec zak\xF3dovan\xFD ve form\xE1tu base64",
    base64url: "\u0159et\u011Bzec zak\xF3dovan\xFD ve form\xE1tu base64url",
    json_string: "\u0159et\u011Bzec ve form\xE1tu JSON",
    e164: "\u010D\xEDslo E.164",
    jwt: "JWT",
    template_literal: "vstup"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u010D\xEDslo",
    string: "\u0159et\u011Bzec",
    function: "funkce",
    array: "pole"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Neplatn\xFD vstup: o\u010Dek\xE1v\xE1no instanceof ${issue3.expected}, obdr\u017Eeno ${received}`;
        }
        return `Neplatn\xFD vstup: o\u010Dek\xE1v\xE1no ${expected}, obdr\u017Eeno ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Neplatn\xFD vstup: o\u010Dek\xE1v\xE1no ${stringifyPrimitive(issue3.values[0])}`;
        return `Neplatn\xE1 mo\u017Enost: o\u010Dek\xE1v\xE1na jedna z hodnot ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Hodnota je p\u0159\xEDli\u0161 velk\xE1: ${issue3.origin ?? "hodnota"} mus\xED m\xEDt ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "prvk\u016F"}`;
        }
        return `Hodnota je p\u0159\xEDli\u0161 velk\xE1: ${issue3.origin ?? "hodnota"} mus\xED b\xFDt ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Hodnota je p\u0159\xEDli\u0161 mal\xE1: ${issue3.origin ?? "hodnota"} mus\xED m\xEDt ${adj}${issue3.minimum.toString()} ${sizing.unit ?? "prvk\u016F"}`;
        }
        return `Hodnota je p\u0159\xEDli\u0161 mal\xE1: ${issue3.origin ?? "hodnota"} mus\xED b\xFDt ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Neplatn\xFD \u0159et\u011Bzec: mus\xED za\u010D\xEDnat na "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Neplatn\xFD \u0159et\u011Bzec: mus\xED kon\u010Dit na "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Neplatn\xFD \u0159et\u011Bzec: mus\xED obsahovat "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Neplatn\xFD \u0159et\u011Bzec: mus\xED odpov\xEDdat vzoru ${_issue.pattern}`;
        return `Neplatn\xFD form\xE1t ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Neplatn\xE9 \u010D\xEDslo: mus\xED b\xFDt n\xE1sobkem ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Nezn\xE1m\xE9 kl\xED\u010De: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Neplatn\xFD kl\xED\u010D v ${issue3.origin}`;
      case "invalid_union":
        return "Neplatn\xFD vstup";
      case "invalid_element":
        return `Neplatn\xE1 hodnota v ${issue3.origin}`;
      default:
        return `Neplatn\xFD vstup`;
    }
  };
};
function cs_default() {
  return {
    localeError: error6()
  };
}

// node_modules/zod/v4/locales/da.js
var error7 = () => {
  const Sizable = {
    string: { unit: "tegn", verb: "havde" },
    file: { unit: "bytes", verb: "havde" },
    array: { unit: "elementer", verb: "indeholdt" },
    set: { unit: "elementer", verb: "indeholdt" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "e-mailadresse",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO dato- og klokkesl\xE6t",
    date: "ISO-dato",
    time: "ISO-klokkesl\xE6t",
    duration: "ISO-varighed",
    ipv4: "IPv4-omr\xE5de",
    ipv6: "IPv6-omr\xE5de",
    cidrv4: "IPv4-spektrum",
    cidrv6: "IPv6-spektrum",
    base64: "base64-kodet streng",
    base64url: "base64url-kodet streng",
    json_string: "JSON-streng",
    e164: "E.164-nummer",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN",
    string: "streng",
    number: "tal",
    boolean: "boolean",
    array: "liste",
    object: "objekt",
    set: "s\xE6t",
    file: "fil"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ugyldigt input: forventede instanceof ${issue3.expected}, fik ${received}`;
        }
        return `Ugyldigt input: forventede ${expected}, fik ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ugyldig v\xE6rdi: forventede ${stringifyPrimitive(issue3.values[0])}`;
        return `Ugyldigt valg: forventede en af f\xF8lgende ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing)
          return `For stor: forventede ${origin ?? "value"} ${sizing.verb} ${adj} ${issue3.maximum.toString()} ${sizing.unit ?? "elementer"}`;
        return `For stor: forventede ${origin ?? "value"} havde ${adj} ${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing) {
          return `For lille: forventede ${origin} ${sizing.verb} ${adj} ${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `For lille: forventede ${origin} havde ${adj} ${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Ugyldig streng: skal starte med "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Ugyldig streng: skal ende med "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Ugyldig streng: skal indeholde "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Ugyldig streng: skal matche m\xF8nsteret ${_issue.pattern}`;
        return `Ugyldig ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ugyldigt tal: skal v\xE6re deleligt med ${issue3.divisor}`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "Ukendte n\xF8gler" : "Ukendt n\xF8gle"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Ugyldig n\xF8gle i ${issue3.origin}`;
      case "invalid_union":
        return "Ugyldigt input: matcher ingen af de tilladte typer";
      case "invalid_element":
        return `Ugyldig v\xE6rdi i ${issue3.origin}`;
      default:
        return `Ugyldigt input`;
    }
  };
};
function da_default() {
  return {
    localeError: error7()
  };
}

// node_modules/zod/v4/locales/de.js
var error8 = () => {
  const Sizable = {
    string: { unit: "Zeichen", verb: "zu haben" },
    file: { unit: "Bytes", verb: "zu haben" },
    array: { unit: "Elemente", verb: "zu haben" },
    set: { unit: "Elemente", verb: "zu haben" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "Eingabe",
    email: "E-Mail-Adresse",
    url: "URL",
    emoji: "Emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO-Datum und -Uhrzeit",
    date: "ISO-Datum",
    time: "ISO-Uhrzeit",
    duration: "ISO-Dauer",
    ipv4: "IPv4-Adresse",
    ipv6: "IPv6-Adresse",
    cidrv4: "IPv4-Bereich",
    cidrv6: "IPv6-Bereich",
    base64: "Base64-codierter String",
    base64url: "Base64-URL-codierter String",
    json_string: "JSON-String",
    e164: "E.164-Nummer",
    jwt: "JWT",
    template_literal: "Eingabe"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "Zahl",
    array: "Array"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ung\xFCltige Eingabe: erwartet instanceof ${issue3.expected}, erhalten ${received}`;
        }
        return `Ung\xFCltige Eingabe: erwartet ${expected}, erhalten ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ung\xFCltige Eingabe: erwartet ${stringifyPrimitive(issue3.values[0])}`;
        return `Ung\xFCltige Option: erwartet eine von ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Zu gro\xDF: erwartet, dass ${issue3.origin ?? "Wert"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "Elemente"} hat`;
        return `Zu gro\xDF: erwartet, dass ${issue3.origin ?? "Wert"} ${adj}${issue3.maximum.toString()} ist`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Zu klein: erwartet, dass ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit} hat`;
        }
        return `Zu klein: erwartet, dass ${issue3.origin} ${adj}${issue3.minimum.toString()} ist`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Ung\xFCltiger String: muss mit "${_issue.prefix}" beginnen`;
        if (_issue.format === "ends_with")
          return `Ung\xFCltiger String: muss mit "${_issue.suffix}" enden`;
        if (_issue.format === "includes")
          return `Ung\xFCltiger String: muss "${_issue.includes}" enthalten`;
        if (_issue.format === "regex")
          return `Ung\xFCltiger String: muss dem Muster ${_issue.pattern} entsprechen`;
        return `Ung\xFCltig: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ung\xFCltige Zahl: muss ein Vielfaches von ${issue3.divisor} sein`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "Unbekannte Schl\xFCssel" : "Unbekannter Schl\xFCssel"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Ung\xFCltiger Schl\xFCssel in ${issue3.origin}`;
      case "invalid_union":
        return "Ung\xFCltige Eingabe";
      case "invalid_element":
        return `Ung\xFCltiger Wert in ${issue3.origin}`;
      default:
        return `Ung\xFCltige Eingabe`;
    }
  };
};
function de_default() {
  return {
    localeError: error8()
  };
}

// node_modules/zod/v4/locales/el.js
var error9 = () => {
  const Sizable = {
    string: { unit: "\u03C7\u03B1\u03C1\u03B1\u03BA\u03C4\u03AE\u03C1\u03B5\u03C2", verb: "\u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9" },
    file: { unit: "bytes", verb: "\u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9" },
    array: { unit: "\u03C3\u03C4\u03BF\u03B9\u03C7\u03B5\u03AF\u03B1", verb: "\u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9" },
    set: { unit: "\u03C3\u03C4\u03BF\u03B9\u03C7\u03B5\u03AF\u03B1", verb: "\u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9" },
    map: { unit: "\u03BA\u03B1\u03C4\u03B1\u03C7\u03C9\u03C1\u03AE\u03C3\u03B5\u03B9\u03C2", verb: "\u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2",
    email: "\u03B4\u03B9\u03B5\u03CD\u03B8\u03C5\u03BD\u03C3\u03B7 email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u03B7\u03BC\u03B5\u03C1\u03BF\u03BC\u03B7\u03BD\u03AF\u03B1 \u03BA\u03B1\u03B9 \u03CE\u03C1\u03B1",
    date: "ISO \u03B7\u03BC\u03B5\u03C1\u03BF\u03BC\u03B7\u03BD\u03AF\u03B1",
    time: "ISO \u03CE\u03C1\u03B1",
    duration: "ISO \u03B4\u03B9\u03AC\u03C1\u03BA\u03B5\u03B9\u03B1",
    ipv4: "\u03B4\u03B9\u03B5\u03CD\u03B8\u03C5\u03BD\u03C3\u03B7 IPv4",
    ipv6: "\u03B4\u03B9\u03B5\u03CD\u03B8\u03C5\u03BD\u03C3\u03B7 IPv6",
    mac: "\u03B4\u03B9\u03B5\u03CD\u03B8\u03C5\u03BD\u03C3\u03B7 MAC",
    cidrv4: "\u03B5\u03CD\u03C1\u03BF\u03C2 IPv4",
    cidrv6: "\u03B5\u03CD\u03C1\u03BF\u03C2 IPv6",
    base64: "\u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC \u03BA\u03C9\u03B4\u03B9\u03BA\u03BF\u03C0\u03BF\u03B9\u03B7\u03BC\u03AD\u03BD\u03B7 \u03C3\u03B5 base64",
    base64url: "\u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC \u03BA\u03C9\u03B4\u03B9\u03BA\u03BF\u03C0\u03BF\u03B9\u03B7\u03BC\u03AD\u03BD\u03B7 \u03C3\u03B5 base64url",
    json_string: "\u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC JSON",
    e164: "\u03B1\u03C1\u03B9\u03B8\u03BC\u03CC\u03C2 E.164",
    jwt: "JWT",
    template_literal: "\u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (typeof issue3.expected === "string" && /^[A-Z]/.test(issue3.expected)) {
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD instanceof ${issue3.expected}, \u03BB\u03AE\u03C6\u03B8\u03B7\u03BA\u03B5 ${received}`;
        }
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${expected}, \u03BB\u03AE\u03C6\u03B8\u03B7\u03BA\u03B5 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${stringifyPrimitive(issue3.values[0])}`;
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03C0\u03B9\u03BB\u03BF\u03B3\u03AE: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD \u03AD\u03BD\u03B1 \u03B1\u03C0\u03CC ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u03A0\u03BF\u03BB\u03CD \u03BC\u03B5\u03B3\u03AC\u03BB\u03BF: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${issue3.origin ?? "\u03C4\u03B9\u03BC\u03AE"} \u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9 ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u03C3\u03C4\u03BF\u03B9\u03C7\u03B5\u03AF\u03B1"}`;
        return `\u03A0\u03BF\u03BB\u03CD \u03BC\u03B5\u03B3\u03AC\u03BB\u03BF: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${issue3.origin ?? "\u03C4\u03B9\u03BC\u03AE"} \u03BD\u03B1 \u03B5\u03AF\u03BD\u03B1\u03B9 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u03A0\u03BF\u03BB\u03CD \u03BC\u03B9\u03BA\u03C1\u03CC: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${issue3.origin} \u03BD\u03B1 \u03AD\u03C7\u03B5\u03B9 ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u03A0\u03BF\u03BB\u03CD \u03BC\u03B9\u03BA\u03C1\u03CC: \u03B1\u03BD\u03B1\u03BC\u03B5\u03BD\u03CC\u03C4\u03B1\u03BD ${issue3.origin} \u03BD\u03B1 \u03B5\u03AF\u03BD\u03B1\u03B9 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC: \u03C0\u03C1\u03AD\u03C0\u03B5\u03B9 \u03BD\u03B1 \u03BE\u03B5\u03BA\u03B9\u03BD\u03AC \u03BC\u03B5 "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC: \u03C0\u03C1\u03AD\u03C0\u03B5\u03B9 \u03BD\u03B1 \u03C4\u03B5\u03BB\u03B5\u03B9\u03CE\u03BD\u03B5\u03B9 \u03BC\u03B5 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC: \u03C0\u03C1\u03AD\u03C0\u03B5\u03B9 \u03BD\u03B1 \u03C0\u03B5\u03C1\u03B9\u03AD\u03C7\u03B5\u03B9 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03C3\u03C5\u03BC\u03B2\u03BF\u03BB\u03BF\u03C3\u03B5\u03B9\u03C1\u03AC: \u03C0\u03C1\u03AD\u03C0\u03B5\u03B9 \u03BD\u03B1 \u03C4\u03B1\u03B9\u03C1\u03B9\u03AC\u03B6\u03B5\u03B9 \u03BC\u03B5 \u03C4\u03BF \u03BC\u03BF\u03C4\u03AF\u03B2\u03BF ${_issue.pattern}`;
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03BF: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03BF\u03C2 \u03B1\u03C1\u03B9\u03B8\u03BC\u03CC\u03C2: \u03C0\u03C1\u03AD\u03C0\u03B5\u03B9 \u03BD\u03B1 \u03B5\u03AF\u03BD\u03B1\u03B9 \u03C0\u03BF\u03BB\u03BB\u03B1\u03C0\u03BB\u03AC\u03C3\u03B9\u03BF \u03C4\u03BF\u03C5 ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u0386\u03B3\u03BD\u03C9\u03C3\u03C4${issue3.keys.length > 1 ? "\u03B1" : "\u03BF"} \u03BA\u03BB\u03B5\u03B9\u03B4${issue3.keys.length > 1 ? "\u03B9\u03AC" : "\u03AF"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03BF \u03BA\u03BB\u03B5\u03B9\u03B4\u03AF \u03C3\u03C4\u03BF ${issue3.origin}`;
      case "invalid_union":
        return "\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2";
      case "invalid_element":
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03C4\u03B9\u03BC\u03AE \u03C3\u03C4\u03BF ${issue3.origin}`;
      default:
        return `\u039C\u03B7 \u03AD\u03B3\u03BA\u03C5\u03C1\u03B7 \u03B5\u03AF\u03C3\u03BF\u03B4\u03BF\u03C2`;
    }
  };
};
function el_default() {
  return {
    localeError: error9()
  };
}

// node_modules/zod/v4/locales/en.js
var error10 = () => {
  const Sizable = {
    string: { unit: "characters", verb: "to have" },
    file: { unit: "bytes", verb: "to have" },
    array: { unit: "items", verb: "to have" },
    set: { unit: "items", verb: "to have" },
    map: { unit: "entries", verb: "to have" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "email address",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO datetime",
    date: "ISO date",
    time: "ISO time",
    duration: "ISO duration",
    ipv4: "IPv4 address",
    ipv6: "IPv6 address",
    mac: "MAC address",
    cidrv4: "IPv4 range",
    cidrv6: "IPv6 range",
    base64: "base64-encoded string",
    base64url: "base64url-encoded string",
    json_string: "JSON string",
    e164: "E.164 number",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    // Compatibility: "nan" -> "NaN" for display
    nan: "NaN"
    // All other type names omitted - they fall back to raw values via ?? operator
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        return `Invalid input: expected ${expected}, received ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Invalid input: expected ${stringifyPrimitive(issue3.values[0])}`;
        return `Invalid option: expected one of ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Too big: expected ${issue3.origin ?? "value"} to have ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elements"}`;
        return `Too big: expected ${issue3.origin ?? "value"} to be ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Too small: expected ${issue3.origin} to have ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Too small: expected ${issue3.origin} to be ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Invalid string: must start with "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Invalid string: must end with "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Invalid string: must include "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Invalid string: must match pattern ${_issue.pattern}`;
        return `Invalid ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Invalid number: must be a multiple of ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Unrecognized key${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Invalid key in ${issue3.origin}`;
      case "invalid_union":
        if (issue3.options && Array.isArray(issue3.options) && issue3.options.length > 0) {
          const opts = issue3.options.map((o) => `'${o}'`).join(" | ");
          return `Invalid discriminator value. Expected ${opts}`;
        }
        return "Invalid input";
      case "invalid_element":
        return `Invalid value in ${issue3.origin}`;
      default:
        return `Invalid input`;
    }
  };
};
function en_default() {
  return {
    localeError: error10()
  };
}

// node_modules/zod/v4/locales/eo.js
var error11 = () => {
  const Sizable = {
    string: { unit: "karaktrojn", verb: "havi" },
    file: { unit: "bajtojn", verb: "havi" },
    array: { unit: "elementojn", verb: "havi" },
    set: { unit: "elementojn", verb: "havi" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "enigo",
    email: "retadreso",
    url: "URL",
    emoji: "emo\u011Dio",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO-datotempo",
    date: "ISO-dato",
    time: "ISO-tempo",
    duration: "ISO-da\u016Dro",
    ipv4: "IPv4-adreso",
    ipv6: "IPv6-adreso",
    cidrv4: "IPv4-rango",
    cidrv6: "IPv6-rango",
    base64: "64-ume kodita karaktraro",
    base64url: "URL-64-ume kodita karaktraro",
    json_string: "JSON-karaktraro",
    e164: "E.164-nombro",
    jwt: "JWT",
    template_literal: "enigo"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "nombro",
    array: "tabelo",
    null: "senvalora"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Nevalida enigo: atendi\u011Dis instanceof ${issue3.expected}, ricevi\u011Dis ${received}`;
        }
        return `Nevalida enigo: atendi\u011Dis ${expected}, ricevi\u011Dis ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Nevalida enigo: atendi\u011Dis ${stringifyPrimitive(issue3.values[0])}`;
        return `Nevalida opcio: atendi\u011Dis unu el ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Tro granda: atendi\u011Dis ke ${issue3.origin ?? "valoro"} havu ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementojn"}`;
        return `Tro granda: atendi\u011Dis ke ${issue3.origin ?? "valoro"} havu ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Tro malgranda: atendi\u011Dis ke ${issue3.origin} havu ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Tro malgranda: atendi\u011Dis ke ${issue3.origin} estu ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Nevalida karaktraro: devas komenci\u011Di per "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Nevalida karaktraro: devas fini\u011Di per "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Nevalida karaktraro: devas inkluzivi "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Nevalida karaktraro: devas kongrui kun la modelo ${_issue.pattern}`;
        return `Nevalida ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Nevalida nombro: devas esti oblo de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Nekonata${issue3.keys.length > 1 ? "j" : ""} \u015Dlosilo${issue3.keys.length > 1 ? "j" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Nevalida \u015Dlosilo en ${issue3.origin}`;
      case "invalid_union":
        return "Nevalida enigo";
      case "invalid_element":
        return `Nevalida valoro en ${issue3.origin}`;
      default:
        return `Nevalida enigo`;
    }
  };
};
function eo_default() {
  return {
    localeError: error11()
  };
}

// node_modules/zod/v4/locales/es.js
var error12 = () => {
  const Sizable = {
    string: { unit: "caracteres", verb: "tener" },
    file: { unit: "bytes", verb: "tener" },
    array: { unit: "elementos", verb: "tener" },
    set: { unit: "elementos", verb: "tener" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "entrada",
    email: "direcci\xF3n de correo electr\xF3nico",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "fecha y hora ISO",
    date: "fecha ISO",
    time: "hora ISO",
    duration: "duraci\xF3n ISO",
    ipv4: "direcci\xF3n IPv4",
    ipv6: "direcci\xF3n IPv6",
    cidrv4: "rango IPv4",
    cidrv6: "rango IPv6",
    base64: "cadena codificada en base64",
    base64url: "URL codificada en base64",
    json_string: "cadena JSON",
    e164: "n\xFAmero E.164",
    jwt: "JWT",
    template_literal: "entrada"
  };
  const TypeDictionary = {
    nan: "NaN",
    string: "texto",
    number: "n\xFAmero",
    boolean: "booleano",
    array: "arreglo",
    object: "objeto",
    set: "conjunto",
    file: "archivo",
    date: "fecha",
    bigint: "n\xFAmero grande",
    symbol: "s\xEDmbolo",
    undefined: "indefinido",
    null: "nulo",
    function: "funci\xF3n",
    map: "mapa",
    record: "registro",
    tuple: "tupla",
    enum: "enumeraci\xF3n",
    union: "uni\xF3n",
    literal: "literal",
    promise: "promesa",
    void: "vac\xEDo",
    never: "nunca",
    unknown: "desconocido",
    any: "cualquiera"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Entrada inv\xE1lida: se esperaba instanceof ${issue3.expected}, recibido ${received}`;
        }
        return `Entrada inv\xE1lida: se esperaba ${expected}, recibido ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Entrada inv\xE1lida: se esperaba ${stringifyPrimitive(issue3.values[0])}`;
        return `Opci\xF3n inv\xE1lida: se esperaba una de ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing)
          return `Demasiado grande: se esperaba que ${origin ?? "valor"} tuviera ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementos"}`;
        return `Demasiado grande: se esperaba que ${origin ?? "valor"} fuera ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing) {
          return `Demasiado peque\xF1o: se esperaba que ${origin} tuviera ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Demasiado peque\xF1o: se esperaba que ${origin} fuera ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Cadena inv\xE1lida: debe comenzar con "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Cadena inv\xE1lida: debe terminar en "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Cadena inv\xE1lida: debe incluir "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Cadena inv\xE1lida: debe coincidir con el patr\xF3n ${_issue.pattern}`;
        return `Inv\xE1lido ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `N\xFAmero inv\xE1lido: debe ser m\xFAltiplo de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Llave${issue3.keys.length > 1 ? "s" : ""} desconocida${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Llave inv\xE1lida en ${TypeDictionary[issue3.origin] ?? issue3.origin}`;
      case "invalid_union":
        return "Entrada inv\xE1lida";
      case "invalid_element":
        return `Valor inv\xE1lido en ${TypeDictionary[issue3.origin] ?? issue3.origin}`;
      default:
        return `Entrada inv\xE1lida`;
    }
  };
};
function es_default() {
  return {
    localeError: error12()
  };
}

// node_modules/zod/v4/locales/fa.js
var error13 = () => {
  const Sizable = {
    string: { unit: "\u06A9\u0627\u0631\u0627\u06A9\u062A\u0631", verb: "\u062F\u0627\u0634\u062A\u0647 \u0628\u0627\u0634\u062F" },
    file: { unit: "\u0628\u0627\u06CC\u062A", verb: "\u062F\u0627\u0634\u062A\u0647 \u0628\u0627\u0634\u062F" },
    array: { unit: "\u0622\u06CC\u062A\u0645", verb: "\u062F\u0627\u0634\u062A\u0647 \u0628\u0627\u0634\u062F" },
    set: { unit: "\u0622\u06CC\u062A\u0645", verb: "\u062F\u0627\u0634\u062A\u0647 \u0628\u0627\u0634\u062F" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0648\u0631\u0648\u062F\u06CC",
    email: "\u0622\u062F\u0631\u0633 \u0627\u06CC\u0645\u06CC\u0644",
    url: "URL",
    emoji: "\u0627\u06CC\u0645\u0648\u062C\u06CC",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u062A\u0627\u0631\u06CC\u062E \u0648 \u0632\u0645\u0627\u0646 \u0627\u06CC\u0632\u0648",
    date: "\u062A\u0627\u0631\u06CC\u062E \u0627\u06CC\u0632\u0648",
    time: "\u0632\u0645\u0627\u0646 \u0627\u06CC\u0632\u0648",
    duration: "\u0645\u062F\u062A \u0632\u0645\u0627\u0646 \u0627\u06CC\u0632\u0648",
    ipv4: "IPv4 \u0622\u062F\u0631\u0633",
    ipv6: "IPv6 \u0622\u062F\u0631\u0633",
    cidrv4: "IPv4 \u062F\u0627\u0645\u0646\u0647",
    cidrv6: "IPv6 \u062F\u0627\u0645\u0646\u0647",
    base64: "base64-encoded \u0631\u0634\u062A\u0647",
    base64url: "base64url-encoded \u0631\u0634\u062A\u0647",
    json_string: "JSON \u0631\u0634\u062A\u0647",
    e164: "E.164 \u0639\u062F\u062F",
    jwt: "JWT",
    template_literal: "\u0648\u0631\u0648\u062F\u06CC"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0639\u062F\u062F",
    array: "\u0622\u0631\u0627\u06CC\u0647"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0648\u0631\u0648\u062F\u06CC \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0645\u06CC\u200C\u0628\u0627\u06CC\u0633\u062A instanceof ${issue3.expected} \u0645\u06CC\u200C\u0628\u0648\u062F\u060C ${received} \u062F\u0631\u06CC\u0627\u0641\u062A \u0634\u062F`;
        }
        return `\u0648\u0631\u0648\u062F\u06CC \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0645\u06CC\u200C\u0628\u0627\u06CC\u0633\u062A ${expected} \u0645\u06CC\u200C\u0628\u0648\u062F\u060C ${received} \u062F\u0631\u06CC\u0627\u0641\u062A \u0634\u062F`;
      }
      case "invalid_value":
        if (issue3.values.length === 1) {
          return `\u0648\u0631\u0648\u062F\u06CC \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0645\u06CC\u200C\u0628\u0627\u06CC\u0633\u062A ${stringifyPrimitive(issue3.values[0])} \u0645\u06CC\u200C\u0628\u0648\u062F`;
        }
        return `\u06AF\u0632\u06CC\u0646\u0647 \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0645\u06CC\u200C\u0628\u0627\u06CC\u0633\u062A \u06CC\u06A9\u06CC \u0627\u0632 ${joinValues(issue3.values, "|")} \u0645\u06CC\u200C\u0628\u0648\u062F`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u062E\u06CC\u0644\u06CC \u0628\u0632\u0631\u06AF: ${issue3.origin ?? "\u0645\u0642\u062F\u0627\u0631"} \u0628\u0627\u06CC\u062F ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0639\u0646\u0635\u0631"} \u0628\u0627\u0634\u062F`;
        }
        return `\u062E\u06CC\u0644\u06CC \u0628\u0632\u0631\u06AF: ${issue3.origin ?? "\u0645\u0642\u062F\u0627\u0631"} \u0628\u0627\u06CC\u062F ${adj}${issue3.maximum.toString()} \u0628\u0627\u0634\u062F`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u062E\u06CC\u0644\u06CC \u06A9\u0648\u0686\u06A9: ${issue3.origin} \u0628\u0627\u06CC\u062F ${adj}${issue3.minimum.toString()} ${sizing.unit} \u0628\u0627\u0634\u062F`;
        }
        return `\u062E\u06CC\u0644\u06CC \u06A9\u0648\u0686\u06A9: ${issue3.origin} \u0628\u0627\u06CC\u062F ${adj}${issue3.minimum.toString()} \u0628\u0627\u0634\u062F`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u0631\u0634\u062A\u0647 \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0628\u0627\u06CC\u062F \u0628\u0627 "${_issue.prefix}" \u0634\u0631\u0648\u0639 \u0634\u0648\u062F`;
        }
        if (_issue.format === "ends_with") {
          return `\u0631\u0634\u062A\u0647 \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0628\u0627\u06CC\u062F \u0628\u0627 "${_issue.suffix}" \u062A\u0645\u0627\u0645 \u0634\u0648\u062F`;
        }
        if (_issue.format === "includes") {
          return `\u0631\u0634\u062A\u0647 \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0628\u0627\u06CC\u062F \u0634\u0627\u0645\u0644 "${_issue.includes}" \u0628\u0627\u0634\u062F`;
        }
        if (_issue.format === "regex") {
          return `\u0631\u0634\u062A\u0647 \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0628\u0627\u06CC\u062F \u0628\u0627 \u0627\u0644\u06AF\u0648\u06CC ${_issue.pattern} \u0645\u0637\u0627\u0628\u0642\u062A \u062F\u0627\u0634\u062A\u0647 \u0628\u0627\u0634\u062F`;
        }
        return `${FormatDictionary[_issue.format] ?? issue3.format} \u0646\u0627\u0645\u0639\u062A\u0628\u0631`;
      }
      case "not_multiple_of":
        return `\u0639\u062F\u062F \u0646\u0627\u0645\u0639\u062A\u0628\u0631: \u0628\u0627\u06CC\u062F \u0645\u0636\u0631\u0628 ${issue3.divisor} \u0628\u0627\u0634\u062F`;
      case "unrecognized_keys":
        return `\u06A9\u0644\u06CC\u062F${issue3.keys.length > 1 ? "\u0647\u0627\u06CC" : ""} \u0646\u0627\u0634\u0646\u0627\u0633: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u06A9\u0644\u06CC\u062F \u0646\u0627\u0634\u0646\u0627\u0633 \u062F\u0631 ${issue3.origin}`;
      case "invalid_union":
        return `\u0648\u0631\u0648\u062F\u06CC \u0646\u0627\u0645\u0639\u062A\u0628\u0631`;
      case "invalid_element":
        return `\u0645\u0642\u062F\u0627\u0631 \u0646\u0627\u0645\u0639\u062A\u0628\u0631 \u062F\u0631 ${issue3.origin}`;
      default:
        return `\u0648\u0631\u0648\u062F\u06CC \u0646\u0627\u0645\u0639\u062A\u0628\u0631`;
    }
  };
};
function fa_default() {
  return {
    localeError: error13()
  };
}

// node_modules/zod/v4/locales/fi.js
var error14 = () => {
  const Sizable = {
    string: { unit: "merkki\xE4", subject: "merkkijonon" },
    file: { unit: "tavua", subject: "tiedoston" },
    array: { unit: "alkiota", subject: "listan" },
    set: { unit: "alkiota", subject: "joukon" },
    number: { unit: "", subject: "luvun" },
    bigint: { unit: "", subject: "suuren kokonaisluvun" },
    int: { unit: "", subject: "kokonaisluvun" },
    date: { unit: "", subject: "p\xE4iv\xE4m\xE4\xE4r\xE4n" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "s\xE4\xE4nn\xF6llinen lauseke",
    email: "s\xE4hk\xF6postiosoite",
    url: "URL-osoite",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO-aikaleima",
    date: "ISO-p\xE4iv\xE4m\xE4\xE4r\xE4",
    time: "ISO-aika",
    duration: "ISO-kesto",
    ipv4: "IPv4-osoite",
    ipv6: "IPv6-osoite",
    cidrv4: "IPv4-alue",
    cidrv6: "IPv6-alue",
    base64: "base64-koodattu merkkijono",
    base64url: "base64url-koodattu merkkijono",
    json_string: "JSON-merkkijono",
    e164: "E.164-luku",
    jwt: "JWT",
    template_literal: "templaattimerkkijono"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Virheellinen tyyppi: odotettiin instanceof ${issue3.expected}, oli ${received}`;
        }
        return `Virheellinen tyyppi: odotettiin ${expected}, oli ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Virheellinen sy\xF6te: t\xE4ytyy olla ${stringifyPrimitive(issue3.values[0])}`;
        return `Virheellinen valinta: t\xE4ytyy olla yksi seuraavista: ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Liian suuri: ${sizing.subject} t\xE4ytyy olla ${adj}${issue3.maximum.toString()} ${sizing.unit}`.trim();
        }
        return `Liian suuri: arvon t\xE4ytyy olla ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Liian pieni: ${sizing.subject} t\xE4ytyy olla ${adj}${issue3.minimum.toString()} ${sizing.unit}`.trim();
        }
        return `Liian pieni: arvon t\xE4ytyy olla ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Virheellinen sy\xF6te: t\xE4ytyy alkaa "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Virheellinen sy\xF6te: t\xE4ytyy loppua "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Virheellinen sy\xF6te: t\xE4ytyy sis\xE4lt\xE4\xE4 "${_issue.includes}"`;
        if (_issue.format === "regex") {
          return `Virheellinen sy\xF6te: t\xE4ytyy vastata s\xE4\xE4nn\xF6llist\xE4 lauseketta ${_issue.pattern}`;
        }
        return `Virheellinen ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Virheellinen luku: t\xE4ytyy olla luvun ${issue3.divisor} monikerta`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "Tuntemattomat avaimet" : "Tuntematon avain"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return "Virheellinen avain tietueessa";
      case "invalid_union":
        return "Virheellinen unioni";
      case "invalid_element":
        return "Virheellinen arvo joukossa";
      default:
        return `Virheellinen sy\xF6te`;
    }
  };
};
function fi_default() {
  return {
    localeError: error14()
  };
}

// node_modules/zod/v4/locales/fr.js
var error15 = () => {
  const Sizable = {
    string: { unit: "caract\xE8res", verb: "avoir" },
    file: { unit: "octets", verb: "avoir" },
    array: { unit: "\xE9l\xE9ments", verb: "avoir" },
    set: { unit: "\xE9l\xE9ments", verb: "avoir" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "entr\xE9e",
    email: "adresse e-mail",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "date et heure ISO",
    date: "date ISO",
    time: "heure ISO",
    duration: "dur\xE9e ISO",
    ipv4: "adresse IPv4",
    ipv6: "adresse IPv6",
    cidrv4: "plage IPv4",
    cidrv6: "plage IPv6",
    base64: "cha\xEEne encod\xE9e en base64",
    base64url: "cha\xEEne encod\xE9e en base64url",
    json_string: "cha\xEEne JSON",
    e164: "num\xE9ro E.164",
    jwt: "JWT",
    template_literal: "entr\xE9e"
  };
  const TypeDictionary = {
    string: "cha\xEEne",
    number: "nombre",
    int: "entier",
    boolean: "bool\xE9en",
    bigint: "grand entier",
    symbol: "symbole",
    undefined: "ind\xE9fini",
    null: "null",
    never: "jamais",
    void: "vide",
    date: "date",
    array: "tableau",
    object: "objet",
    tuple: "tuple",
    record: "enregistrement",
    map: "carte",
    set: "ensemble",
    file: "fichier",
    nonoptional: "non-optionnel",
    nan: "NaN",
    function: "fonction"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Entr\xE9e invalide : instanceof ${issue3.expected} attendu, ${received} re\xE7u`;
        }
        return `Entr\xE9e invalide : ${expected} attendu, ${received} re\xE7u`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Entr\xE9e invalide : ${stringifyPrimitive(issue3.values[0])} attendu`;
        return `Option invalide : une valeur parmi ${joinValues(issue3.values, "|")} attendue`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Trop grand : ${TypeDictionary[issue3.origin] ?? "valeur"} doit ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\xE9l\xE9ment(s)"}`;
        return `Trop grand : ${TypeDictionary[issue3.origin] ?? "valeur"} doit \xEAtre ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Trop petit : ${TypeDictionary[issue3.origin] ?? "valeur"} doit ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        return `Trop petit : ${TypeDictionary[issue3.origin] ?? "valeur"} doit \xEAtre ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Cha\xEEne invalide : doit commencer par "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Cha\xEEne invalide : doit se terminer par "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Cha\xEEne invalide : doit inclure "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Cha\xEEne invalide : doit correspondre au mod\xE8le ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} invalide`;
      }
      case "not_multiple_of":
        return `Nombre invalide : doit \xEAtre un multiple de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Cl\xE9${issue3.keys.length > 1 ? "s" : ""} non reconnue${issue3.keys.length > 1 ? "s" : ""} : ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Cl\xE9 invalide dans ${issue3.origin}`;
      case "invalid_union":
        return "Entr\xE9e invalide";
      case "invalid_element":
        return `Valeur invalide dans ${issue3.origin}`;
      default:
        return `Entr\xE9e invalide`;
    }
  };
};
function fr_default() {
  return {
    localeError: error15()
  };
}

// node_modules/zod/v4/locales/fr-CA.js
var error16 = () => {
  const Sizable = {
    string: { unit: "caract\xE8res", verb: "avoir" },
    file: { unit: "octets", verb: "avoir" },
    array: { unit: "\xE9l\xE9ments", verb: "avoir" },
    set: { unit: "\xE9l\xE9ments", verb: "avoir" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "entr\xE9e",
    email: "adresse courriel",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "date-heure ISO",
    date: "date ISO",
    time: "heure ISO",
    duration: "dur\xE9e ISO",
    ipv4: "adresse IPv4",
    ipv6: "adresse IPv6",
    cidrv4: "plage IPv4",
    cidrv6: "plage IPv6",
    base64: "cha\xEEne encod\xE9e en base64",
    base64url: "cha\xEEne encod\xE9e en base64url",
    json_string: "cha\xEEne JSON",
    e164: "num\xE9ro E.164",
    jwt: "JWT",
    template_literal: "entr\xE9e"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Entr\xE9e invalide : attendu instanceof ${issue3.expected}, re\xE7u ${received}`;
        }
        return `Entr\xE9e invalide : attendu ${expected}, re\xE7u ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Entr\xE9e invalide : attendu ${stringifyPrimitive(issue3.values[0])}`;
        return `Option invalide : attendu l'une des valeurs suivantes ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "\u2264" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Trop grand : attendu que ${issue3.origin ?? "la valeur"} ait ${adj}${issue3.maximum.toString()} ${sizing.unit}`;
        return `Trop grand : attendu que ${issue3.origin ?? "la valeur"} soit ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? "\u2265" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Trop petit : attendu que ${issue3.origin} ait ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Trop petit : attendu que ${issue3.origin} soit ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Cha\xEEne invalide : doit commencer par "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Cha\xEEne invalide : doit se terminer par "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Cha\xEEne invalide : doit inclure "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Cha\xEEne invalide : doit correspondre au motif ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} invalide`;
      }
      case "not_multiple_of":
        return `Nombre invalide : doit \xEAtre un multiple de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Cl\xE9${issue3.keys.length > 1 ? "s" : ""} non reconnue${issue3.keys.length > 1 ? "s" : ""} : ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Cl\xE9 invalide dans ${issue3.origin}`;
      case "invalid_union":
        return "Entr\xE9e invalide";
      case "invalid_element":
        return `Valeur invalide dans ${issue3.origin}`;
      default:
        return `Entr\xE9e invalide`;
    }
  };
};
function fr_CA_default() {
  return {
    localeError: error16()
  };
}

// node_modules/zod/v4/locales/he.js
var error17 = () => {
  const TypeNames = {
    string: { label: "\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA", gender: "f" },
    number: { label: "\u05DE\u05E1\u05E4\u05E8", gender: "m" },
    boolean: { label: "\u05E2\u05E8\u05DA \u05D1\u05D5\u05DC\u05D9\u05D0\u05E0\u05D9", gender: "m" },
    bigint: { label: "BigInt", gender: "m" },
    date: { label: "\u05EA\u05D0\u05E8\u05D9\u05DA", gender: "m" },
    array: { label: "\u05DE\u05E2\u05E8\u05DA", gender: "m" },
    object: { label: "\u05D0\u05D5\u05D1\u05D9\u05D9\u05E7\u05D8", gender: "m" },
    null: { label: "\u05E2\u05E8\u05DA \u05E8\u05D9\u05E7 (null)", gender: "m" },
    undefined: { label: "\u05E2\u05E8\u05DA \u05DC\u05D0 \u05DE\u05D5\u05D2\u05D3\u05E8 (undefined)", gender: "m" },
    symbol: { label: "\u05E1\u05D9\u05DE\u05D1\u05D5\u05DC (Symbol)", gender: "m" },
    function: { label: "\u05E4\u05D5\u05E0\u05E7\u05E6\u05D9\u05D4", gender: "f" },
    map: { label: "\u05DE\u05E4\u05D4 (Map)", gender: "f" },
    set: { label: "\u05E7\u05D1\u05D5\u05E6\u05D4 (Set)", gender: "f" },
    file: { label: "\u05E7\u05D5\u05D1\u05E5", gender: "m" },
    promise: { label: "Promise", gender: "m" },
    NaN: { label: "NaN", gender: "m" },
    unknown: { label: "\u05E2\u05E8\u05DA \u05DC\u05D0 \u05D9\u05D3\u05D5\u05E2", gender: "m" },
    value: { label: "\u05E2\u05E8\u05DA", gender: "m" }
  };
  const Sizable = {
    string: { unit: "\u05EA\u05D5\u05D5\u05D9\u05DD", shortLabel: "\u05E7\u05E6\u05E8", longLabel: "\u05D0\u05E8\u05D5\u05DA" },
    file: { unit: "\u05D1\u05D9\u05D9\u05D8\u05D9\u05DD", shortLabel: "\u05E7\u05D8\u05DF", longLabel: "\u05D2\u05D3\u05D5\u05DC" },
    array: { unit: "\u05E4\u05E8\u05D9\u05D8\u05D9\u05DD", shortLabel: "\u05E7\u05D8\u05DF", longLabel: "\u05D2\u05D3\u05D5\u05DC" },
    set: { unit: "\u05E4\u05E8\u05D9\u05D8\u05D9\u05DD", shortLabel: "\u05E7\u05D8\u05DF", longLabel: "\u05D2\u05D3\u05D5\u05DC" },
    number: { unit: "", shortLabel: "\u05E7\u05D8\u05DF", longLabel: "\u05D2\u05D3\u05D5\u05DC" }
    // no unit
  };
  const typeEntry = (t) => t ? TypeNames[t] : void 0;
  const typeLabel = (t) => {
    const e = typeEntry(t);
    if (e)
      return e.label;
    return t ?? TypeNames.unknown.label;
  };
  const withDefinite = (t) => `\u05D4${typeLabel(t)}`;
  const verbFor = (t) => {
    const e = typeEntry(t);
    const gender = e?.gender ?? "m";
    return gender === "f" ? "\u05E6\u05E8\u05D9\u05DB\u05D4 \u05DC\u05D4\u05D9\u05D5\u05EA" : "\u05E6\u05E8\u05D9\u05DA \u05DC\u05D4\u05D9\u05D5\u05EA";
  };
  const getSizing = (origin) => {
    if (!origin)
      return null;
    return Sizable[origin] ?? null;
  };
  const FormatDictionary = {
    regex: { label: "\u05E7\u05DC\u05D8", gender: "m" },
    email: { label: "\u05DB\u05EA\u05D5\u05D1\u05EA \u05D0\u05D9\u05DE\u05D9\u05D9\u05DC", gender: "f" },
    url: { label: "\u05DB\u05EA\u05D5\u05D1\u05EA \u05E8\u05E9\u05EA", gender: "f" },
    emoji: { label: "\u05D0\u05D9\u05DE\u05D5\u05D2'\u05D9", gender: "m" },
    uuid: { label: "UUID", gender: "m" },
    nanoid: { label: "nanoid", gender: "m" },
    guid: { label: "GUID", gender: "m" },
    cuid: { label: "cuid", gender: "m" },
    cuid2: { label: "cuid2", gender: "m" },
    ulid: { label: "ULID", gender: "m" },
    xid: { label: "XID", gender: "m" },
    ksuid: { label: "KSUID", gender: "m" },
    datetime: { label: "\u05EA\u05D0\u05E8\u05D9\u05DA \u05D5\u05D6\u05DE\u05DF ISO", gender: "m" },
    date: { label: "\u05EA\u05D0\u05E8\u05D9\u05DA ISO", gender: "m" },
    time: { label: "\u05D6\u05DE\u05DF ISO", gender: "m" },
    duration: { label: "\u05DE\u05E9\u05DA \u05D6\u05DE\u05DF ISO", gender: "m" },
    ipv4: { label: "\u05DB\u05EA\u05D5\u05D1\u05EA IPv4", gender: "f" },
    ipv6: { label: "\u05DB\u05EA\u05D5\u05D1\u05EA IPv6", gender: "f" },
    cidrv4: { label: "\u05D8\u05D5\u05D5\u05D7 IPv4", gender: "m" },
    cidrv6: { label: "\u05D8\u05D5\u05D5\u05D7 IPv6", gender: "m" },
    base64: { label: "\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D1\u05D1\u05E1\u05D9\u05E1 64", gender: "f" },
    base64url: { label: "\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D1\u05D1\u05E1\u05D9\u05E1 64 \u05DC\u05DB\u05EA\u05D5\u05D1\u05D5\u05EA \u05E8\u05E9\u05EA", gender: "f" },
    json_string: { label: "\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA JSON", gender: "f" },
    e164: { label: "\u05DE\u05E1\u05E4\u05E8 E.164", gender: "m" },
    jwt: { label: "JWT", gender: "m" },
    ends_with: { label: "\u05E7\u05DC\u05D8", gender: "m" },
    includes: { label: "\u05E7\u05DC\u05D8", gender: "m" },
    lowercase: { label: "\u05E7\u05DC\u05D8", gender: "m" },
    starts_with: { label: "\u05E7\u05DC\u05D8", gender: "m" },
    uppercase: { label: "\u05E7\u05DC\u05D8", gender: "m" }
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expectedKey = issue3.expected;
        const expected = TypeDictionary[expectedKey ?? ""] ?? typeLabel(expectedKey);
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? TypeNames[receivedType]?.label ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u05E7\u05DC\u05D8 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05E6\u05E8\u05D9\u05DA \u05DC\u05D4\u05D9\u05D5\u05EA instanceof ${issue3.expected}, \u05D4\u05EA\u05E7\u05D1\u05DC ${received}`;
        }
        return `\u05E7\u05DC\u05D8 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05E6\u05E8\u05D9\u05DA \u05DC\u05D4\u05D9\u05D5\u05EA ${expected}, \u05D4\u05EA\u05E7\u05D1\u05DC ${received}`;
      }
      case "invalid_value": {
        if (issue3.values.length === 1) {
          return `\u05E2\u05E8\u05DA \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05D4\u05E2\u05E8\u05DA \u05D7\u05D9\u05D9\u05D1 \u05DC\u05D4\u05D9\u05D5\u05EA ${stringifyPrimitive(issue3.values[0])}`;
        }
        const stringified = issue3.values.map((v) => stringifyPrimitive(v));
        if (issue3.values.length === 2) {
          return `\u05E2\u05E8\u05DA \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05D4\u05D0\u05E4\u05E9\u05E8\u05D5\u05D9\u05D5\u05EA \u05D4\u05DE\u05EA\u05D0\u05D9\u05DE\u05D5\u05EA \u05D4\u05DF ${stringified[0]} \u05D0\u05D5 ${stringified[1]}`;
        }
        const lastValue = stringified[stringified.length - 1];
        const restValues = stringified.slice(0, -1).join(", ");
        return `\u05E2\u05E8\u05DA \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05D4\u05D0\u05E4\u05E9\u05E8\u05D5\u05D9\u05D5\u05EA \u05D4\u05DE\u05EA\u05D0\u05D9\u05DE\u05D5\u05EA \u05D4\u05DF ${restValues} \u05D0\u05D5 ${lastValue}`;
      }
      case "too_big": {
        const sizing = getSizing(issue3.origin);
        const subject = withDefinite(issue3.origin ?? "value");
        if (issue3.origin === "string") {
          return `${sizing?.longLabel ?? "\u05D0\u05E8\u05D5\u05DA"} \u05DE\u05D3\u05D9: ${subject} \u05E6\u05E8\u05D9\u05DB\u05D4 \u05DC\u05D4\u05DB\u05D9\u05DC ${issue3.maximum.toString()} ${sizing?.unit ?? ""} ${issue3.inclusive ? "\u05D0\u05D5 \u05E4\u05D7\u05D5\u05EA" : "\u05DC\u05DB\u05DC \u05D4\u05D9\u05D5\u05EA\u05E8"}`.trim();
        }
        if (issue3.origin === "number") {
          const comparison = issue3.inclusive ? `\u05E7\u05D8\u05DF \u05D0\u05D5 \u05E9\u05D5\u05D5\u05D4 \u05DC-${issue3.maximum}` : `\u05E7\u05D8\u05DF \u05DE-${issue3.maximum}`;
          return `\u05D2\u05D3\u05D5\u05DC \u05DE\u05D3\u05D9: ${subject} \u05E6\u05E8\u05D9\u05DA \u05DC\u05D4\u05D9\u05D5\u05EA ${comparison}`;
        }
        if (issue3.origin === "array" || issue3.origin === "set") {
          const verb = issue3.origin === "set" ? "\u05E6\u05E8\u05D9\u05DB\u05D4" : "\u05E6\u05E8\u05D9\u05DA";
          const comparison = issue3.inclusive ? `${issue3.maximum} ${sizing?.unit ?? ""} \u05D0\u05D5 \u05E4\u05D7\u05D5\u05EA` : `\u05E4\u05D7\u05D5\u05EA \u05DE-${issue3.maximum} ${sizing?.unit ?? ""}`;
          return `\u05D2\u05D3\u05D5\u05DC \u05DE\u05D3\u05D9: ${subject} ${verb} \u05DC\u05D4\u05DB\u05D9\u05DC ${comparison}`.trim();
        }
        const adj = issue3.inclusive ? "<=" : "<";
        const be = verbFor(issue3.origin ?? "value");
        if (sizing?.unit) {
          return `${sizing.longLabel} \u05DE\u05D3\u05D9: ${subject} ${be} ${adj}${issue3.maximum.toString()} ${sizing.unit}`;
        }
        return `${sizing?.longLabel ?? "\u05D2\u05D3\u05D5\u05DC"} \u05DE\u05D3\u05D9: ${subject} ${be} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const sizing = getSizing(issue3.origin);
        const subject = withDefinite(issue3.origin ?? "value");
        if (issue3.origin === "string") {
          return `${sizing?.shortLabel ?? "\u05E7\u05E6\u05E8"} \u05DE\u05D3\u05D9: ${subject} \u05E6\u05E8\u05D9\u05DB\u05D4 \u05DC\u05D4\u05DB\u05D9\u05DC ${issue3.minimum.toString()} ${sizing?.unit ?? ""} ${issue3.inclusive ? "\u05D0\u05D5 \u05D9\u05D5\u05EA\u05E8" : "\u05DC\u05E4\u05D7\u05D5\u05EA"}`.trim();
        }
        if (issue3.origin === "number") {
          const comparison = issue3.inclusive ? `\u05D2\u05D3\u05D5\u05DC \u05D0\u05D5 \u05E9\u05D5\u05D5\u05D4 \u05DC-${issue3.minimum}` : `\u05D2\u05D3\u05D5\u05DC \u05DE-${issue3.minimum}`;
          return `\u05E7\u05D8\u05DF \u05DE\u05D3\u05D9: ${subject} \u05E6\u05E8\u05D9\u05DA \u05DC\u05D4\u05D9\u05D5\u05EA ${comparison}`;
        }
        if (issue3.origin === "array" || issue3.origin === "set") {
          const verb = issue3.origin === "set" ? "\u05E6\u05E8\u05D9\u05DB\u05D4" : "\u05E6\u05E8\u05D9\u05DA";
          if (issue3.minimum === 1 && issue3.inclusive) {
            const singularPhrase = issue3.origin === "set" ? "\u05DC\u05E4\u05D7\u05D5\u05EA \u05E4\u05E8\u05D9\u05D8 \u05D0\u05D7\u05D3" : "\u05DC\u05E4\u05D7\u05D5\u05EA \u05E4\u05E8\u05D9\u05D8 \u05D0\u05D7\u05D3";
            return `\u05E7\u05D8\u05DF \u05DE\u05D3\u05D9: ${subject} ${verb} \u05DC\u05D4\u05DB\u05D9\u05DC ${singularPhrase}`;
          }
          const comparison = issue3.inclusive ? `${issue3.minimum} ${sizing?.unit ?? ""} \u05D0\u05D5 \u05D9\u05D5\u05EA\u05E8` : `\u05D9\u05D5\u05EA\u05E8 \u05DE-${issue3.minimum} ${sizing?.unit ?? ""}`;
          return `\u05E7\u05D8\u05DF \u05DE\u05D3\u05D9: ${subject} ${verb} \u05DC\u05D4\u05DB\u05D9\u05DC ${comparison}`.trim();
        }
        const adj = issue3.inclusive ? ">=" : ">";
        const be = verbFor(issue3.origin ?? "value");
        if (sizing?.unit) {
          return `${sizing.shortLabel} \u05DE\u05D3\u05D9: ${subject} ${be} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `${sizing?.shortLabel ?? "\u05E7\u05D8\u05DF"} \u05DE\u05D3\u05D9: ${subject} ${be} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u05D4\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D7\u05D9\u05D9\u05D1\u05EA \u05DC\u05D4\u05EA\u05D7\u05D9\u05DC \u05D1 "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u05D4\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D7\u05D9\u05D9\u05D1\u05EA \u05DC\u05D4\u05E1\u05EA\u05D9\u05D9\u05DD \u05D1 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u05D4\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D7\u05D9\u05D9\u05D1\u05EA \u05DC\u05DB\u05DC\u05D5\u05DC "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u05D4\u05DE\u05D7\u05E8\u05D5\u05D6\u05EA \u05D7\u05D9\u05D9\u05D1\u05EA \u05DC\u05D4\u05EA\u05D0\u05D9\u05DD \u05DC\u05EA\u05D1\u05E0\u05D9\u05EA ${_issue.pattern}`;
        const nounEntry = FormatDictionary[_issue.format];
        const noun = nounEntry?.label ?? _issue.format;
        const gender = nounEntry?.gender ?? "m";
        const adjective = gender === "f" ? "\u05EA\u05E7\u05D9\u05E0\u05D4" : "\u05EA\u05E7\u05D9\u05DF";
        return `${noun} \u05DC\u05D0 ${adjective}`;
      }
      case "not_multiple_of":
        return `\u05DE\u05E1\u05E4\u05E8 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF: \u05D7\u05D9\u05D9\u05D1 \u05DC\u05D4\u05D9\u05D5\u05EA \u05DE\u05DB\u05E4\u05DC\u05D4 \u05E9\u05DC ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u05DE\u05E4\u05EA\u05D7${issue3.keys.length > 1 ? "\u05D5\u05EA" : ""} \u05DC\u05D0 \u05DE\u05D6\u05D5\u05D4${issue3.keys.length > 1 ? "\u05D9\u05DD" : "\u05D4"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key": {
        return `\u05E9\u05D3\u05D4 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF \u05D1\u05D0\u05D5\u05D1\u05D9\u05D9\u05E7\u05D8`;
      }
      case "invalid_union":
        return "\u05E7\u05DC\u05D8 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF";
      case "invalid_element": {
        const place = withDefinite(issue3.origin ?? "array");
        return `\u05E2\u05E8\u05DA \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF \u05D1${place}`;
      }
      default:
        return `\u05E7\u05DC\u05D8 \u05DC\u05D0 \u05EA\u05E7\u05D9\u05DF`;
    }
  };
};
function he_default() {
  return {
    localeError: error17()
  };
}

// node_modules/zod/v4/locales/hr.js
var error18 = () => {
  const Sizable = {
    string: { unit: "znakova", verb: "imati" },
    file: { unit: "bajtova", verb: "imati" },
    array: { unit: "stavki", verb: "imati" },
    set: { unit: "stavki", verb: "imati" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "unos",
    email: "email adresa",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO datum i vrijeme",
    date: "ISO datum",
    time: "ISO vrijeme",
    duration: "ISO trajanje",
    ipv4: "IPv4 adresa",
    ipv6: "IPv6 adresa",
    cidrv4: "IPv4 raspon",
    cidrv6: "IPv6 raspon",
    base64: "base64 kodirani tekst",
    base64url: "base64url kodirani tekst",
    json_string: "JSON tekst",
    e164: "E.164 broj",
    jwt: "JWT",
    template_literal: "unos"
  };
  const TypeDictionary = {
    nan: "NaN",
    string: "tekst",
    number: "broj",
    boolean: "boolean",
    array: "niz",
    object: "objekt",
    set: "skup",
    file: "datoteka",
    date: "datum",
    bigint: "bigint",
    symbol: "simbol",
    undefined: "undefined",
    null: "null",
    function: "funkcija",
    map: "mapa"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Neispravan unos: o\u010Dekuje se instanceof ${issue3.expected}, a primljeno je ${received}`;
        }
        return `Neispravan unos: o\u010Dekuje se ${expected}, a primljeno je ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Neispravna vrijednost: o\u010Dekivano ${stringifyPrimitive(issue3.values[0])}`;
        return `Neispravna opcija: o\u010Dekivano jedno od ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing)
          return `Preveliko: o\u010Dekivano da ${origin ?? "vrijednost"} ima ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elemenata"}`;
        return `Preveliko: o\u010Dekivano da ${origin ?? "vrijednost"} bude ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        if (sizing) {
          return `Premalo: o\u010Dekivano da ${origin} ima ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Premalo: o\u010Dekivano da ${origin} bude ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Neispravan tekst: mora zapo\u010Dinjati s "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Neispravan tekst: mora zavr\u0161avati s "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Neispravan tekst: mora sadr\u017Eavati "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Neispravan tekst: mora odgovarati uzorku ${_issue.pattern}`;
        return `Neispravna ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Neispravan broj: mora biti vi\u0161ekratnik od ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Neprepoznat${issue3.keys.length > 1 ? "i klju\u010Devi" : " klju\u010D"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Neispravan klju\u010D u ${TypeDictionary[issue3.origin] ?? issue3.origin}`;
      case "invalid_union":
        return "Neispravan unos";
      case "invalid_element":
        return `Neispravna vrijednost u ${TypeDictionary[issue3.origin] ?? issue3.origin}`;
      default:
        return `Neispravan unos`;
    }
  };
};
function hr_default() {
  return {
    localeError: error18()
  };
}

// node_modules/zod/v4/locales/hu.js
var error19 = () => {
  const Sizable = {
    string: { unit: "karakter", verb: "legyen" },
    file: { unit: "byte", verb: "legyen" },
    array: { unit: "elem", verb: "legyen" },
    set: { unit: "elem", verb: "legyen" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "bemenet",
    email: "email c\xEDm",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO id\u0151b\xE9lyeg",
    date: "ISO d\xE1tum",
    time: "ISO id\u0151",
    duration: "ISO id\u0151intervallum",
    ipv4: "IPv4 c\xEDm",
    ipv6: "IPv6 c\xEDm",
    cidrv4: "IPv4 tartom\xE1ny",
    cidrv6: "IPv6 tartom\xE1ny",
    base64: "base64-k\xF3dolt string",
    base64url: "base64url-k\xF3dolt string",
    json_string: "JSON string",
    e164: "E.164 sz\xE1m",
    jwt: "JWT",
    template_literal: "bemenet"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "sz\xE1m",
    array: "t\xF6mb"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\xC9rv\xE9nytelen bemenet: a v\xE1rt \xE9rt\xE9k instanceof ${issue3.expected}, a kapott \xE9rt\xE9k ${received}`;
        }
        return `\xC9rv\xE9nytelen bemenet: a v\xE1rt \xE9rt\xE9k ${expected}, a kapott \xE9rt\xE9k ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\xC9rv\xE9nytelen bemenet: a v\xE1rt \xE9rt\xE9k ${stringifyPrimitive(issue3.values[0])}`;
        return `\xC9rv\xE9nytelen opci\xF3: valamelyik \xE9rt\xE9k v\xE1rt ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `T\xFAl nagy: ${issue3.origin ?? "\xE9rt\xE9k"} m\xE9rete t\xFAl nagy ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elem"}`;
        return `T\xFAl nagy: a bemeneti \xE9rt\xE9k ${issue3.origin ?? "\xE9rt\xE9k"} t\xFAl nagy: ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `T\xFAl kicsi: a bemeneti \xE9rt\xE9k ${issue3.origin} m\xE9rete t\xFAl kicsi ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `T\xFAl kicsi: a bemeneti \xE9rt\xE9k ${issue3.origin} t\xFAl kicsi ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\xC9rv\xE9nytelen string: "${_issue.prefix}" \xE9rt\xE9kkel kell kezd\u0151dnie`;
        if (_issue.format === "ends_with")
          return `\xC9rv\xE9nytelen string: "${_issue.suffix}" \xE9rt\xE9kkel kell v\xE9gz\u0151dnie`;
        if (_issue.format === "includes")
          return `\xC9rv\xE9nytelen string: "${_issue.includes}" \xE9rt\xE9ket kell tartalmaznia`;
        if (_issue.format === "regex")
          return `\xC9rv\xE9nytelen string: ${_issue.pattern} mint\xE1nak kell megfelelnie`;
        return `\xC9rv\xE9nytelen ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\xC9rv\xE9nytelen sz\xE1m: ${issue3.divisor} t\xF6bbsz\xF6r\xF6s\xE9nek kell lennie`;
      case "unrecognized_keys":
        return `Ismeretlen kulcs${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\xC9rv\xE9nytelen kulcs ${issue3.origin}`;
      case "invalid_union":
        return "\xC9rv\xE9nytelen bemenet";
      case "invalid_element":
        return `\xC9rv\xE9nytelen \xE9rt\xE9k: ${issue3.origin}`;
      default:
        return `\xC9rv\xE9nytelen bemenet`;
    }
  };
};
function hu_default() {
  return {
    localeError: error19()
  };
}

// node_modules/zod/v4/locales/hy.js
function getArmenianPlural(count, one, many) {
  return Math.abs(count) === 1 ? one : many;
}
function withDefiniteArticle(word) {
  if (!word)
    return "";
  const vowels = ["\u0561", "\u0565", "\u0568", "\u056B", "\u0578", "\u0578\u0582", "\u0585"];
  const lastChar = word[word.length - 1];
  return word + (vowels.includes(lastChar) ? "\u0576" : "\u0568");
}
var error20 = () => {
  const Sizable = {
    string: {
      unit: {
        one: "\u0576\u0577\u0561\u0576",
        many: "\u0576\u0577\u0561\u0576\u0576\u0565\u0580"
      },
      verb: "\u0578\u0582\u0576\u0565\u0576\u0561\u056C"
    },
    file: {
      unit: {
        one: "\u0562\u0561\u0575\u0569",
        many: "\u0562\u0561\u0575\u0569\u0565\u0580"
      },
      verb: "\u0578\u0582\u0576\u0565\u0576\u0561\u056C"
    },
    array: {
      unit: {
        one: "\u057F\u0561\u0580\u0580",
        many: "\u057F\u0561\u0580\u0580\u0565\u0580"
      },
      verb: "\u0578\u0582\u0576\u0565\u0576\u0561\u056C"
    },
    set: {
      unit: {
        one: "\u057F\u0561\u0580\u0580",
        many: "\u057F\u0561\u0580\u0580\u0565\u0580"
      },
      verb: "\u0578\u0582\u0576\u0565\u0576\u0561\u056C"
    }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0574\u0578\u0582\u057F\u0584",
    email: "\u0567\u056C. \u0570\u0561\u057D\u0581\u0565",
    url: "URL",
    emoji: "\u0567\u0574\u0578\u057B\u056B",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0561\u0574\u057D\u0561\u0569\u056B\u057E \u0587 \u056A\u0561\u0574",
    date: "ISO \u0561\u0574\u057D\u0561\u0569\u056B\u057E",
    time: "ISO \u056A\u0561\u0574",
    duration: "ISO \u057F\u0587\u0578\u0572\u0578\u0582\u0569\u0575\u0578\u0582\u0576",
    ipv4: "IPv4 \u0570\u0561\u057D\u0581\u0565",
    ipv6: "IPv6 \u0570\u0561\u057D\u0581\u0565",
    cidrv4: "IPv4 \u0574\u056B\u057B\u0561\u056F\u0561\u0575\u0584",
    cidrv6: "IPv6 \u0574\u056B\u057B\u0561\u056F\u0561\u0575\u0584",
    base64: "base64 \u0571\u0587\u0561\u0579\u0561\u0583\u0578\u057E \u057F\u0578\u0572",
    base64url: "base64url \u0571\u0587\u0561\u0579\u0561\u0583\u0578\u057E \u057F\u0578\u0572",
    json_string: "JSON \u057F\u0578\u0572",
    e164: "E.164 \u0570\u0561\u0574\u0561\u0580",
    jwt: "JWT",
    template_literal: "\u0574\u0578\u0582\u057F\u0584"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0569\u056B\u057E",
    array: "\u0566\u0561\u0576\u0563\u057E\u0561\u056E"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u054D\u056D\u0561\u056C \u0574\u0578\u0582\u057F\u0584\u0561\u0563\u0580\u0578\u0582\u0574\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567\u0580 instanceof ${issue3.expected}, \u057D\u057F\u0561\u0581\u057E\u0565\u056C \u0567 ${received}`;
        }
        return `\u054D\u056D\u0561\u056C \u0574\u0578\u0582\u057F\u0584\u0561\u0563\u0580\u0578\u0582\u0574\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567\u0580 ${expected}, \u057D\u057F\u0561\u0581\u057E\u0565\u056C \u0567 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u054D\u056D\u0561\u056C \u0574\u0578\u0582\u057F\u0584\u0561\u0563\u0580\u0578\u0582\u0574\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567\u0580 ${stringifyPrimitive(issue3.values[1])}`;
        return `\u054D\u056D\u0561\u056C \u057F\u0561\u0580\u0562\u0565\u0580\u0561\u056F\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567\u0580 \u0570\u0565\u057F\u0587\u0575\u0561\u056C\u0576\u0565\u0580\u056B\u0581 \u0574\u0565\u056F\u0568\u055D ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const maxValue = Number(issue3.maximum);
          const unit = getArmenianPlural(maxValue, sizing.unit.one, sizing.unit.many);
          return `\u0549\u0561\u0583\u0561\u0566\u0561\u0576\u0581 \u0574\u0565\u056E \u0561\u0580\u056A\u0565\u0584\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567, \u0578\u0580 ${withDefiniteArticle(issue3.origin ?? "\u0561\u0580\u056A\u0565\u0584")} \u056F\u0578\u0582\u0576\u0565\u0576\u0561 ${adj}${issue3.maximum.toString()} ${unit}`;
        }
        return `\u0549\u0561\u0583\u0561\u0566\u0561\u0576\u0581 \u0574\u0565\u056E \u0561\u0580\u056A\u0565\u0584\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567, \u0578\u0580 ${withDefiniteArticle(issue3.origin ?? "\u0561\u0580\u056A\u0565\u0584")} \u056C\u056B\u0576\u056B ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const minValue = Number(issue3.minimum);
          const unit = getArmenianPlural(minValue, sizing.unit.one, sizing.unit.many);
          return `\u0549\u0561\u0583\u0561\u0566\u0561\u0576\u0581 \u0583\u0578\u0584\u0580 \u0561\u0580\u056A\u0565\u0584\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567, \u0578\u0580 ${withDefiniteArticle(issue3.origin)} \u056F\u0578\u0582\u0576\u0565\u0576\u0561 ${adj}${issue3.minimum.toString()} ${unit}`;
        }
        return `\u0549\u0561\u0583\u0561\u0566\u0561\u0576\u0581 \u0583\u0578\u0584\u0580 \u0561\u0580\u056A\u0565\u0584\u2024 \u057D\u057A\u0561\u057D\u057E\u0578\u0582\u0574 \u0567, \u0578\u0580 ${withDefiniteArticle(issue3.origin)} \u056C\u056B\u0576\u056B ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u054D\u056D\u0561\u056C \u057F\u0578\u0572\u2024 \u057A\u0565\u057F\u0584 \u0567 \u057D\u056F\u057D\u057E\u056B "${_issue.prefix}"-\u0578\u057E`;
        if (_issue.format === "ends_with")
          return `\u054D\u056D\u0561\u056C \u057F\u0578\u0572\u2024 \u057A\u0565\u057F\u0584 \u0567 \u0561\u057E\u0561\u0580\u057F\u057E\u056B "${_issue.suffix}"-\u0578\u057E`;
        if (_issue.format === "includes")
          return `\u054D\u056D\u0561\u056C \u057F\u0578\u0572\u2024 \u057A\u0565\u057F\u0584 \u0567 \u057A\u0561\u0580\u0578\u0582\u0576\u0561\u056F\u056B "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u054D\u056D\u0561\u056C \u057F\u0578\u0572\u2024 \u057A\u0565\u057F\u0584 \u0567 \u0570\u0561\u0574\u0561\u057A\u0561\u057F\u0561\u057D\u056D\u0561\u0576\u056B ${_issue.pattern} \u0571\u0587\u0561\u0579\u0561\u0583\u056B\u0576`;
        return `\u054D\u056D\u0561\u056C ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u054D\u056D\u0561\u056C \u0569\u056B\u057E\u2024 \u057A\u0565\u057F\u0584 \u0567 \u0562\u0561\u0566\u0574\u0561\u057A\u0561\u057F\u056B\u056F \u056C\u056B\u0576\u056B ${issue3.divisor}-\u056B`;
      case "unrecognized_keys":
        return `\u0549\u0573\u0561\u0576\u0561\u0579\u057E\u0561\u056E \u0562\u0561\u0576\u0561\u056C\u056B${issue3.keys.length > 1 ? "\u0576\u0565\u0580" : ""}. ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u054D\u056D\u0561\u056C \u0562\u0561\u0576\u0561\u056C\u056B ${withDefiniteArticle(issue3.origin)}-\u0578\u0582\u0574`;
      case "invalid_union":
        return "\u054D\u056D\u0561\u056C \u0574\u0578\u0582\u057F\u0584\u0561\u0563\u0580\u0578\u0582\u0574";
      case "invalid_element":
        return `\u054D\u056D\u0561\u056C \u0561\u0580\u056A\u0565\u0584 ${withDefiniteArticle(issue3.origin)}-\u0578\u0582\u0574`;
      default:
        return `\u054D\u056D\u0561\u056C \u0574\u0578\u0582\u057F\u0584\u0561\u0563\u0580\u0578\u0582\u0574`;
    }
  };
};
function hy_default() {
  return {
    localeError: error20()
  };
}

// node_modules/zod/v4/locales/id.js
var error21 = () => {
  const Sizable = {
    string: { unit: "karakter", verb: "memiliki" },
    file: { unit: "byte", verb: "memiliki" },
    array: { unit: "item", verb: "memiliki" },
    set: { unit: "item", verb: "memiliki" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "alamat email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "tanggal dan waktu format ISO",
    date: "tanggal format ISO",
    time: "jam format ISO",
    duration: "durasi format ISO",
    ipv4: "alamat IPv4",
    ipv6: "alamat IPv6",
    cidrv4: "rentang alamat IPv4",
    cidrv6: "rentang alamat IPv6",
    base64: "string dengan enkode base64",
    base64url: "string dengan enkode base64url",
    json_string: "string JSON",
    e164: "angka E.164",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Input tidak valid: diharapkan instanceof ${issue3.expected}, diterima ${received}`;
        }
        return `Input tidak valid: diharapkan ${expected}, diterima ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Input tidak valid: diharapkan ${stringifyPrimitive(issue3.values[0])}`;
        return `Pilihan tidak valid: diharapkan salah satu dari ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Terlalu besar: diharapkan ${issue3.origin ?? "value"} memiliki ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elemen"}`;
        return `Terlalu besar: diharapkan ${issue3.origin ?? "value"} menjadi ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Terlalu kecil: diharapkan ${issue3.origin} memiliki ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Terlalu kecil: diharapkan ${issue3.origin} menjadi ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `String tidak valid: harus dimulai dengan "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `String tidak valid: harus berakhir dengan "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `String tidak valid: harus menyertakan "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `String tidak valid: harus sesuai pola ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} tidak valid`;
      }
      case "not_multiple_of":
        return `Angka tidak valid: harus kelipatan dari ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Kunci tidak dikenali ${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Kunci tidak valid di ${issue3.origin}`;
      case "invalid_union":
        return "Input tidak valid";
      case "invalid_element":
        return `Nilai tidak valid di ${issue3.origin}`;
      default:
        return `Input tidak valid`;
    }
  };
};
function id_default() {
  return {
    localeError: error21()
  };
}

// node_modules/zod/v4/locales/is.js
var error22 = () => {
  const Sizable = {
    string: { unit: "stafi", verb: "a\xF0 hafa" },
    file: { unit: "b\xE6ti", verb: "a\xF0 hafa" },
    array: { unit: "hluti", verb: "a\xF0 hafa" },
    set: { unit: "hluti", verb: "a\xF0 hafa" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "gildi",
    email: "netfang",
    url: "vefsl\xF3\xF0",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO dagsetning og t\xEDmi",
    date: "ISO dagsetning",
    time: "ISO t\xEDmi",
    duration: "ISO t\xEDmalengd",
    ipv4: "IPv4 address",
    ipv6: "IPv6 address",
    cidrv4: "IPv4 range",
    cidrv6: "IPv6 range",
    base64: "base64-encoded strengur",
    base64url: "base64url-encoded strengur",
    json_string: "JSON strengur",
    e164: "E.164 t\xF6lugildi",
    jwt: "JWT",
    template_literal: "gildi"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "n\xFAmer",
    array: "fylki"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Rangt gildi: \xDE\xFA sl\xF3st inn ${received} \xFEar sem \xE1 a\xF0 vera instanceof ${issue3.expected}`;
        }
        return `Rangt gildi: \xDE\xFA sl\xF3st inn ${received} \xFEar sem \xE1 a\xF0 vera ${expected}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Rangt gildi: gert r\xE1\xF0 fyrir ${stringifyPrimitive(issue3.values[0])}`;
        return `\xD3gilt val: m\xE1 vera eitt af eftirfarandi ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Of st\xF3rt: gert er r\xE1\xF0 fyrir a\xF0 ${issue3.origin ?? "gildi"} hafi ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "hluti"}`;
        return `Of st\xF3rt: gert er r\xE1\xF0 fyrir a\xF0 ${issue3.origin ?? "gildi"} s\xE9 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Of l\xEDti\xF0: gert er r\xE1\xF0 fyrir a\xF0 ${issue3.origin} hafi ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Of l\xEDti\xF0: gert er r\xE1\xF0 fyrir a\xF0 ${issue3.origin} s\xE9 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\xD3gildur strengur: ver\xF0ur a\xF0 byrja \xE1 "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\xD3gildur strengur: ver\xF0ur a\xF0 enda \xE1 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\xD3gildur strengur: ver\xF0ur a\xF0 innihalda "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\xD3gildur strengur: ver\xF0ur a\xF0 fylgja mynstri ${_issue.pattern}`;
        return `Rangt ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `R\xF6ng tala: ver\xF0ur a\xF0 vera margfeldi af ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\xD3\xFEekkt ${issue3.keys.length > 1 ? "ir lyklar" : "ur lykill"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Rangur lykill \xED ${issue3.origin}`;
      case "invalid_union":
        return "Rangt gildi";
      case "invalid_element":
        return `Rangt gildi \xED ${issue3.origin}`;
      default:
        return `Rangt gildi`;
    }
  };
};
function is_default() {
  return {
    localeError: error22()
  };
}

// node_modules/zod/v4/locales/it.js
var error23 = () => {
  const Sizable = {
    string: { unit: "caratteri", verb: "avere" },
    file: { unit: "byte", verb: "avere" },
    array: { unit: "elementi", verb: "avere" },
    set: { unit: "elementi", verb: "avere" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "indirizzo email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "data e ora ISO",
    date: "data ISO",
    time: "ora ISO",
    duration: "durata ISO",
    ipv4: "indirizzo IPv4",
    ipv6: "indirizzo IPv6",
    cidrv4: "intervallo IPv4",
    cidrv6: "intervallo IPv6",
    base64: "stringa codificata in base64",
    base64url: "URL codificata in base64",
    json_string: "stringa JSON",
    e164: "numero E.164",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "numero",
    array: "vettore"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Input non valido: atteso instanceof ${issue3.expected}, ricevuto ${received}`;
        }
        return `Input non valido: atteso ${expected}, ricevuto ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Input non valido: atteso ${stringifyPrimitive(issue3.values[0])}`;
        return `Opzione non valida: atteso uno tra ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Troppo grande: ${issue3.origin ?? "valore"} deve avere ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementi"}`;
        return `Troppo grande: ${issue3.origin ?? "valore"} deve essere ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Troppo piccolo: ${issue3.origin} deve avere ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Troppo piccolo: ${issue3.origin} deve essere ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Stringa non valida: deve iniziare con "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Stringa non valida: deve terminare con "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Stringa non valida: deve includere "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Stringa non valida: deve corrispondere al pattern ${_issue.pattern}`;
        return `Input non valido: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Numero non valido: deve essere un multiplo di ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Chiav${issue3.keys.length > 1 ? "i" : "e"} non riconosciut${issue3.keys.length > 1 ? "e" : "a"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Chiave non valida in ${issue3.origin}`;
      case "invalid_union":
        return "Input non valido";
      case "invalid_element":
        return `Valore non valido in ${issue3.origin}`;
      default:
        return `Input non valido`;
    }
  };
};
function it_default() {
  return {
    localeError: error23()
  };
}

// node_modules/zod/v4/locales/ja.js
var error24 = () => {
  const Sizable = {
    string: { unit: "\u6587\u5B57", verb: "\u3067\u3042\u308B" },
    file: { unit: "\u30D0\u30A4\u30C8", verb: "\u3067\u3042\u308B" },
    array: { unit: "\u8981\u7D20", verb: "\u3067\u3042\u308B" },
    set: { unit: "\u8981\u7D20", verb: "\u3067\u3042\u308B" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u5165\u529B\u5024",
    email: "\u30E1\u30FC\u30EB\u30A2\u30C9\u30EC\u30B9",
    url: "URL",
    emoji: "\u7D75\u6587\u5B57",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO\u65E5\u6642",
    date: "ISO\u65E5\u4ED8",
    time: "ISO\u6642\u523B",
    duration: "ISO\u671F\u9593",
    ipv4: "IPv4\u30A2\u30C9\u30EC\u30B9",
    ipv6: "IPv6\u30A2\u30C9\u30EC\u30B9",
    cidrv4: "IPv4\u7BC4\u56F2",
    cidrv6: "IPv6\u7BC4\u56F2",
    base64: "base64\u30A8\u30F3\u30B3\u30FC\u30C9\u6587\u5B57\u5217",
    base64url: "base64url\u30A8\u30F3\u30B3\u30FC\u30C9\u6587\u5B57\u5217",
    json_string: "JSON\u6587\u5B57\u5217",
    e164: "E.164\u756A\u53F7",
    jwt: "JWT",
    template_literal: "\u5165\u529B\u5024"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u6570\u5024",
    array: "\u914D\u5217"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u7121\u52B9\u306A\u5165\u529B: instanceof ${issue3.expected}\u304C\u671F\u5F85\u3055\u308C\u307E\u3057\u305F\u304C\u3001${received}\u304C\u5165\u529B\u3055\u308C\u307E\u3057\u305F`;
        }
        return `\u7121\u52B9\u306A\u5165\u529B: ${expected}\u304C\u671F\u5F85\u3055\u308C\u307E\u3057\u305F\u304C\u3001${received}\u304C\u5165\u529B\u3055\u308C\u307E\u3057\u305F`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u7121\u52B9\u306A\u5165\u529B: ${stringifyPrimitive(issue3.values[0])}\u304C\u671F\u5F85\u3055\u308C\u307E\u3057\u305F`;
        return `\u7121\u52B9\u306A\u9078\u629E: ${joinValues(issue3.values, "\u3001")}\u306E\u3044\u305A\u308C\u304B\u3067\u3042\u308B\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
      case "too_big": {
        const adj = issue3.inclusive ? "\u4EE5\u4E0B\u3067\u3042\u308B" : "\u3088\u308A\u5C0F\u3055\u3044";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u5927\u304D\u3059\u304E\u308B\u5024: ${issue3.origin ?? "\u5024"}\u306F${issue3.maximum.toString()}${sizing.unit ?? "\u8981\u7D20"}${adj}\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        return `\u5927\u304D\u3059\u304E\u308B\u5024: ${issue3.origin ?? "\u5024"}\u306F${issue3.maximum.toString()}${adj}\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? "\u4EE5\u4E0A\u3067\u3042\u308B" : "\u3088\u308A\u5927\u304D\u3044";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u5C0F\u3055\u3059\u304E\u308B\u5024: ${issue3.origin}\u306F${issue3.minimum.toString()}${sizing.unit}${adj}\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        return `\u5C0F\u3055\u3059\u304E\u308B\u5024: ${issue3.origin}\u306F${issue3.minimum.toString()}${adj}\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u7121\u52B9\u306A\u6587\u5B57\u5217: "${_issue.prefix}"\u3067\u59CB\u307E\u308B\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        if (_issue.format === "ends_with")
          return `\u7121\u52B9\u306A\u6587\u5B57\u5217: "${_issue.suffix}"\u3067\u7D42\u308F\u308B\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        if (_issue.format === "includes")
          return `\u7121\u52B9\u306A\u6587\u5B57\u5217: "${_issue.includes}"\u3092\u542B\u3080\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        if (_issue.format === "regex")
          return `\u7121\u52B9\u306A\u6587\u5B57\u5217: \u30D1\u30BF\u30FC\u30F3${_issue.pattern}\u306B\u4E00\u81F4\u3059\u308B\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
        return `\u7121\u52B9\u306A${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u7121\u52B9\u306A\u6570\u5024: ${issue3.divisor}\u306E\u500D\u6570\u3067\u3042\u308B\u5FC5\u8981\u304C\u3042\u308A\u307E\u3059`;
      case "unrecognized_keys":
        return `\u8A8D\u8B58\u3055\u308C\u3066\u3044\u306A\u3044\u30AD\u30FC${issue3.keys.length > 1 ? "\u7FA4" : ""}: ${joinValues(issue3.keys, "\u3001")}`;
      case "invalid_key":
        return `${issue3.origin}\u5185\u306E\u7121\u52B9\u306A\u30AD\u30FC`;
      case "invalid_union":
        return "\u7121\u52B9\u306A\u5165\u529B";
      case "invalid_element":
        return `${issue3.origin}\u5185\u306E\u7121\u52B9\u306A\u5024`;
      default:
        return `\u7121\u52B9\u306A\u5165\u529B`;
    }
  };
};
function ja_default() {
  return {
    localeError: error24()
  };
}

// node_modules/zod/v4/locales/ka.js
var error25 = () => {
  const Sizable = {
    string: { unit: "\u10E1\u10D8\u10DB\u10D1\u10DD\u10DA\u10DD", verb: "\u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D8\u10EA\u10D0\u10D5\u10D3\u10D4\u10E1" },
    file: { unit: "\u10D1\u10D0\u10D8\u10E2\u10D8", verb: "\u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D8\u10EA\u10D0\u10D5\u10D3\u10D4\u10E1" },
    array: { unit: "\u10D4\u10DA\u10D4\u10DB\u10D4\u10DC\u10E2\u10D8", verb: "\u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D8\u10EA\u10D0\u10D5\u10D3\u10D4\u10E1" },
    set: { unit: "\u10D4\u10DA\u10D4\u10DB\u10D4\u10DC\u10E2\u10D8", verb: "\u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D8\u10EA\u10D0\u10D5\u10D3\u10D4\u10E1" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0",
    email: "\u10D4\u10DA-\u10E4\u10DD\u10E1\u10E2\u10D8\u10E1 \u10DB\u10D8\u10E1\u10D0\u10DB\u10D0\u10E0\u10D7\u10D8",
    url: "URL",
    emoji: "\u10D4\u10DB\u10DD\u10EF\u10D8",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u10D7\u10D0\u10E0\u10D8\u10E6\u10D8-\u10D3\u10E0\u10DD",
    date: "\u10D7\u10D0\u10E0\u10D8\u10E6\u10D8",
    time: "\u10D3\u10E0\u10DD",
    duration: "\u10EE\u10D0\u10DC\u10D2\u10E0\u10EB\u10DA\u10D8\u10D5\u10DD\u10D1\u10D0",
    ipv4: "IPv4 \u10DB\u10D8\u10E1\u10D0\u10DB\u10D0\u10E0\u10D7\u10D8",
    ipv6: "IPv6 \u10DB\u10D8\u10E1\u10D0\u10DB\u10D0\u10E0\u10D7\u10D8",
    cidrv4: "IPv4 \u10D3\u10D8\u10D0\u10DE\u10D0\u10D6\u10DD\u10DC\u10D8",
    cidrv6: "IPv6 \u10D3\u10D8\u10D0\u10DE\u10D0\u10D6\u10DD\u10DC\u10D8",
    base64: "base64-\u10D9\u10DD\u10D3\u10D8\u10E0\u10D4\u10D1\u10E3\u10DA\u10D8 \u10D5\u10D4\u10DA\u10D8",
    base64url: "base64url-\u10D9\u10DD\u10D3\u10D8\u10E0\u10D4\u10D1\u10E3\u10DA\u10D8 \u10D5\u10D4\u10DA\u10D8",
    json_string: "JSON \u10D5\u10D4\u10DA\u10D8",
    e164: "E.164 \u10DC\u10DD\u10DB\u10D4\u10E0\u10D8",
    jwt: "JWT",
    template_literal: "\u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u10E0\u10D8\u10EA\u10EE\u10D5\u10D8",
    string: "\u10D5\u10D4\u10DA\u10D8",
    boolean: "\u10D1\u10E3\u10DA\u10D4\u10D0\u10DC\u10D8",
    function: "\u10E4\u10E3\u10DC\u10E5\u10EA\u10D8\u10D0",
    array: "\u10DB\u10D0\u10E1\u10D8\u10D5\u10D8"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 instanceof ${issue3.expected}, \u10DB\u10D8\u10E6\u10D4\u10D1\u10E3\u10DA\u10D8 ${received}`;
        }
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${expected}, \u10DB\u10D8\u10E6\u10D4\u10D1\u10E3\u10DA\u10D8 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${stringifyPrimitive(issue3.values[0])}`;
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D5\u10D0\u10E0\u10D8\u10D0\u10DC\u10E2\u10D8: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8\u10D0 \u10D4\u10E0\u10D7-\u10D4\u10E0\u10D7\u10D8 ${joinValues(issue3.values, "|")}-\u10D3\u10D0\u10DC`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u10D6\u10D4\u10D3\u10DB\u10D4\u10E2\u10D0\u10D3 \u10D3\u10D8\u10D3\u10D8: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${issue3.origin ?? "\u10DB\u10DC\u10D8\u10E8\u10D5\u10DC\u10D4\u10DA\u10DD\u10D1\u10D0"} ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit}`;
        return `\u10D6\u10D4\u10D3\u10DB\u10D4\u10E2\u10D0\u10D3 \u10D3\u10D8\u10D3\u10D8: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${issue3.origin ?? "\u10DB\u10DC\u10D8\u10E8\u10D5\u10DC\u10D4\u10DA\u10DD\u10D1\u10D0"} \u10D8\u10E7\u10DD\u10E1 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u10D6\u10D4\u10D3\u10DB\u10D4\u10E2\u10D0\u10D3 \u10DE\u10D0\u10E2\u10D0\u10E0\u10D0: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u10D6\u10D4\u10D3\u10DB\u10D4\u10E2\u10D0\u10D3 \u10DE\u10D0\u10E2\u10D0\u10E0\u10D0: \u10DB\u10DD\u10E1\u10D0\u10DA\u10DD\u10D3\u10DC\u10D4\u10DA\u10D8 ${issue3.origin} \u10D8\u10E7\u10DD\u10E1 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D5\u10D4\u10DA\u10D8: \u10E3\u10DC\u10D3\u10D0 \u10D8\u10EC\u10E7\u10D4\u10D1\u10DD\u10D3\u10D4\u10E1 "${_issue.prefix}"-\u10D8\u10D7`;
        }
        if (_issue.format === "ends_with")
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D5\u10D4\u10DA\u10D8: \u10E3\u10DC\u10D3\u10D0 \u10DB\u10D7\u10D0\u10D5\u10E0\u10D3\u10D4\u10D1\u10DD\u10D3\u10D4\u10E1 "${_issue.suffix}"-\u10D8\u10D7`;
        if (_issue.format === "includes")
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D5\u10D4\u10DA\u10D8: \u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D8\u10EA\u10D0\u10D5\u10D3\u10D4\u10E1 "${_issue.includes}"-\u10E1`;
        if (_issue.format === "regex")
          return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D5\u10D4\u10DA\u10D8: \u10E3\u10DC\u10D3\u10D0 \u10E8\u10D4\u10D4\u10E1\u10D0\u10D1\u10D0\u10DB\u10D4\u10D1\u10DD\u10D3\u10D4\u10E1 \u10E8\u10D0\u10D1\u10DA\u10DD\u10DC\u10E1 ${_issue.pattern}`;
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E0\u10D8\u10EA\u10EE\u10D5\u10D8: \u10E3\u10DC\u10D3\u10D0 \u10D8\u10E7\u10DD\u10E1 ${issue3.divisor}-\u10D8\u10E1 \u10EF\u10D4\u10E0\u10D0\u10D3\u10D8`;
      case "unrecognized_keys":
        return `\u10E3\u10EA\u10DC\u10DD\u10D1\u10D8 \u10D2\u10D0\u10E1\u10D0\u10E6\u10D4\u10D1${issue3.keys.length > 1 ? "\u10D4\u10D1\u10D8" : "\u10D8"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10D2\u10D0\u10E1\u10D0\u10E6\u10D4\u10D1\u10D8 ${issue3.origin}-\u10E8\u10D8`;
      case "invalid_union":
        return "\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0";
      case "invalid_element":
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10DB\u10DC\u10D8\u10E8\u10D5\u10DC\u10D4\u10DA\u10DD\u10D1\u10D0 ${issue3.origin}-\u10E8\u10D8`;
      default:
        return `\u10D0\u10E0\u10D0\u10E1\u10EC\u10DD\u10E0\u10D8 \u10E8\u10D4\u10E7\u10D5\u10D0\u10DC\u10D0`;
    }
  };
};
function ka_default() {
  return {
    localeError: error25()
  };
}

// node_modules/zod/v4/locales/km.js
var error26 = () => {
  const Sizable = {
    string: { unit: "\u178F\u17BD\u17A2\u1780\u17D2\u179F\u179A", verb: "\u1782\u17BD\u179A\u1798\u17B6\u1793" },
    file: { unit: "\u1794\u17C3", verb: "\u1782\u17BD\u179A\u1798\u17B6\u1793" },
    array: { unit: "\u1792\u17B6\u178F\u17BB", verb: "\u1782\u17BD\u179A\u1798\u17B6\u1793" },
    set: { unit: "\u1792\u17B6\u178F\u17BB", verb: "\u1782\u17BD\u179A\u1798\u17B6\u1793" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1794\u1789\u17D2\u1785\u17BC\u179B",
    email: "\u17A2\u17B6\u179F\u1799\u178A\u17D2\u178B\u17B6\u1793\u17A2\u17CA\u17B8\u1798\u17C2\u179B",
    url: "URL",
    emoji: "\u179F\u1789\u17D2\u1789\u17B6\u17A2\u17B6\u179A\u1798\u17D2\u1798\u178E\u17CD",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u1780\u17B6\u179B\u1794\u179A\u17B7\u1785\u17D2\u1786\u17C1\u1791 \u1793\u17B7\u1784\u1798\u17C9\u17C4\u1784 ISO",
    date: "\u1780\u17B6\u179B\u1794\u179A\u17B7\u1785\u17D2\u1786\u17C1\u1791 ISO",
    time: "\u1798\u17C9\u17C4\u1784 ISO",
    duration: "\u179A\u1799\u17C8\u1796\u17C1\u179B ISO",
    ipv4: "\u17A2\u17B6\u179F\u1799\u178A\u17D2\u178B\u17B6\u1793 IPv4",
    ipv6: "\u17A2\u17B6\u179F\u1799\u178A\u17D2\u178B\u17B6\u1793 IPv6",
    cidrv4: "\u178A\u17C2\u1793\u17A2\u17B6\u179F\u1799\u178A\u17D2\u178B\u17B6\u1793 IPv4",
    cidrv6: "\u178A\u17C2\u1793\u17A2\u17B6\u179F\u1799\u178A\u17D2\u178B\u17B6\u1793 IPv6",
    base64: "\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u17A2\u17CA\u17B7\u1780\u17BC\u178A base64",
    base64url: "\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u17A2\u17CA\u17B7\u1780\u17BC\u178A base64url",
    json_string: "\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A JSON",
    e164: "\u179B\u17C1\u1781 E.164",
    jwt: "JWT",
    template_literal: "\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1794\u1789\u17D2\u1785\u17BC\u179B"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u179B\u17C1\u1781",
    array: "\u17A2\u17B6\u179A\u17C1 (Array)",
    null: "\u1782\u17D2\u1798\u17B6\u1793\u178F\u1798\u17D2\u179B\u17C3 (null)"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1794\u1789\u17D2\u1785\u17BC\u179B\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A instanceof ${issue3.expected} \u1794\u17C9\u17BB\u1793\u17D2\u178F\u17C2\u1791\u1791\u17BD\u179B\u1794\u17B6\u1793 ${received}`;
        }
        return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1794\u1789\u17D2\u1785\u17BC\u179B\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${expected} \u1794\u17C9\u17BB\u1793\u17D2\u178F\u17C2\u1791\u1791\u17BD\u179B\u1794\u17B6\u1793 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1794\u1789\u17D2\u1785\u17BC\u179B\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${stringifyPrimitive(issue3.values[0])}`;
        return `\u1787\u1798\u17D2\u179A\u17BE\u179F\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1787\u17B6\u1798\u17BD\u1799\u1780\u17D2\u1793\u17BB\u1784\u1785\u17C6\u178E\u17C4\u1798 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u1792\u17C6\u1796\u17C1\u1780\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${issue3.origin ?? "\u178F\u1798\u17D2\u179B\u17C3"} ${adj} ${issue3.maximum.toString()} ${sizing.unit ?? "\u1792\u17B6\u178F\u17BB"}`;
        return `\u1792\u17C6\u1796\u17C1\u1780\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${issue3.origin ?? "\u178F\u1798\u17D2\u179B\u17C3"} ${adj} ${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u178F\u17BC\u1785\u1796\u17C1\u1780\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${issue3.origin} ${adj} ${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u178F\u17BC\u1785\u1796\u17C1\u1780\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1780\u17B6\u179A ${issue3.origin} ${adj} ${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1785\u17B6\u1794\u17CB\u1795\u17D2\u178F\u17BE\u1798\u178A\u17C4\u1799 "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1794\u1789\u17D2\u1785\u1794\u17CB\u178A\u17C4\u1799 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u1798\u17B6\u1793 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u1781\u17D2\u179F\u17C2\u17A2\u1780\u17D2\u179F\u179A\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u178F\u17C2\u1795\u17D2\u1782\u17BC\u1795\u17D2\u1782\u1784\u1793\u17B9\u1784\u1791\u1798\u17D2\u179A\u1784\u17CB\u178A\u17C2\u179B\u1794\u17B6\u1793\u1780\u17C6\u178E\u178F\u17CB ${_issue.pattern}`;
        return `\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u179B\u17C1\u1781\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u17D6 \u178F\u17D2\u179A\u17BC\u179C\u178F\u17C2\u1787\u17B6\u1796\u17A0\u17BB\u1782\u17BB\u178E\u1793\u17C3 ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u179A\u1780\u1783\u17BE\u1789\u179F\u17C4\u1798\u17B7\u1793\u179F\u17D2\u1782\u17B6\u179B\u17CB\u17D6 ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u179F\u17C4\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u1793\u17C5\u1780\u17D2\u1793\u17BB\u1784 ${issue3.origin}`;
      case "invalid_union":
        return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C`;
      case "invalid_element":
        return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C\u1793\u17C5\u1780\u17D2\u1793\u17BB\u1784 ${issue3.origin}`;
      default:
        return `\u1791\u17B7\u1793\u17D2\u1793\u1793\u17D0\u1799\u1798\u17B7\u1793\u178F\u17D2\u179A\u17B9\u1798\u178F\u17D2\u179A\u17BC\u179C`;
    }
  };
};
function km_default() {
  return {
    localeError: error26()
  };
}

// node_modules/zod/v4/locales/kh.js
function kh_default() {
  return km_default();
}

// node_modules/zod/v4/locales/ko.js
var error27 = () => {
  const Sizable = {
    string: { unit: "\uBB38\uC790", verb: "to have" },
    file: { unit: "\uBC14\uC774\uD2B8", verb: "to have" },
    array: { unit: "\uAC1C", verb: "to have" },
    set: { unit: "\uAC1C", verb: "to have" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\uC785\uB825",
    email: "\uC774\uBA54\uC77C \uC8FC\uC18C",
    url: "URL",
    emoji: "\uC774\uBAA8\uC9C0",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \uB0A0\uC9DC\uC2DC\uAC04",
    date: "ISO \uB0A0\uC9DC",
    time: "ISO \uC2DC\uAC04",
    duration: "ISO \uAE30\uAC04",
    ipv4: "IPv4 \uC8FC\uC18C",
    ipv6: "IPv6 \uC8FC\uC18C",
    cidrv4: "IPv4 \uBC94\uC704",
    cidrv6: "IPv6 \uBC94\uC704",
    base64: "base64 \uC778\uCF54\uB529 \uBB38\uC790\uC5F4",
    base64url: "base64url \uC778\uCF54\uB529 \uBB38\uC790\uC5F4",
    json_string: "JSON \uBB38\uC790\uC5F4",
    e164: "E.164 \uBC88\uD638",
    jwt: "JWT",
    template_literal: "\uC785\uB825"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\uC798\uBABB\uB41C \uC785\uB825: \uC608\uC0C1 \uD0C0\uC785\uC740 instanceof ${issue3.expected}, \uBC1B\uC740 \uD0C0\uC785\uC740 ${received}\uC785\uB2C8\uB2E4`;
        }
        return `\uC798\uBABB\uB41C \uC785\uB825: \uC608\uC0C1 \uD0C0\uC785\uC740 ${expected}, \uBC1B\uC740 \uD0C0\uC785\uC740 ${received}\uC785\uB2C8\uB2E4`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\uC798\uBABB\uB41C \uC785\uB825: \uAC12\uC740 ${stringifyPrimitive(issue3.values[0])} \uC774\uC5B4\uC57C \uD569\uB2C8\uB2E4`;
        return `\uC798\uBABB\uB41C \uC635\uC158: ${joinValues(issue3.values, "\uB610\uB294 ")} \uC911 \uD558\uB098\uC5EC\uC57C \uD569\uB2C8\uB2E4`;
      case "too_big": {
        const adj = issue3.inclusive ? "\uC774\uD558" : "\uBBF8\uB9CC";
        const suffix = adj === "\uBBF8\uB9CC" ? "\uC774\uC5B4\uC57C \uD569\uB2C8\uB2E4" : "\uC5EC\uC57C \uD569\uB2C8\uB2E4";
        const sizing = getSizing(issue3.origin);
        const unit = sizing?.unit ?? "\uC694\uC18C";
        if (sizing)
          return `${issue3.origin ?? "\uAC12"}\uC774 \uB108\uBB34 \uD07D\uB2C8\uB2E4: ${issue3.maximum.toString()}${unit} ${adj}${suffix}`;
        return `${issue3.origin ?? "\uAC12"}\uC774 \uB108\uBB34 \uD07D\uB2C8\uB2E4: ${issue3.maximum.toString()} ${adj}${suffix}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? "\uC774\uC0C1" : "\uCD08\uACFC";
        const suffix = adj === "\uC774\uC0C1" ? "\uC774\uC5B4\uC57C \uD569\uB2C8\uB2E4" : "\uC5EC\uC57C \uD569\uB2C8\uB2E4";
        const sizing = getSizing(issue3.origin);
        const unit = sizing?.unit ?? "\uC694\uC18C";
        if (sizing) {
          return `${issue3.origin ?? "\uAC12"}\uC774 \uB108\uBB34 \uC791\uC2B5\uB2C8\uB2E4: ${issue3.minimum.toString()}${unit} ${adj}${suffix}`;
        }
        return `${issue3.origin ?? "\uAC12"}\uC774 \uB108\uBB34 \uC791\uC2B5\uB2C8\uB2E4: ${issue3.minimum.toString()} ${adj}${suffix}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\uC798\uBABB\uB41C \uBB38\uC790\uC5F4: "${_issue.prefix}"(\uC73C)\uB85C \uC2DC\uC791\uD574\uC57C \uD569\uB2C8\uB2E4`;
        }
        if (_issue.format === "ends_with")
          return `\uC798\uBABB\uB41C \uBB38\uC790\uC5F4: "${_issue.suffix}"(\uC73C)\uB85C \uB05D\uB098\uC57C \uD569\uB2C8\uB2E4`;
        if (_issue.format === "includes")
          return `\uC798\uBABB\uB41C \uBB38\uC790\uC5F4: "${_issue.includes}"\uC744(\uB97C) \uD3EC\uD568\uD574\uC57C \uD569\uB2C8\uB2E4`;
        if (_issue.format === "regex")
          return `\uC798\uBABB\uB41C \uBB38\uC790\uC5F4: \uC815\uADDC\uC2DD ${_issue.pattern} \uD328\uD134\uACFC \uC77C\uCE58\uD574\uC57C \uD569\uB2C8\uB2E4`;
        return `\uC798\uBABB\uB41C ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\uC798\uBABB\uB41C \uC22B\uC790: ${issue3.divisor}\uC758 \uBC30\uC218\uC5EC\uC57C \uD569\uB2C8\uB2E4`;
      case "unrecognized_keys":
        return `\uC778\uC2DD\uD560 \uC218 \uC5C6\uB294 \uD0A4: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\uC798\uBABB\uB41C \uD0A4: ${issue3.origin}`;
      case "invalid_union":
        return `\uC798\uBABB\uB41C \uC785\uB825`;
      case "invalid_element":
        return `\uC798\uBABB\uB41C \uAC12: ${issue3.origin}`;
      default:
        return `\uC798\uBABB\uB41C \uC785\uB825`;
    }
  };
};
function ko_default() {
  return {
    localeError: error27()
  };
}

// node_modules/zod/v4/locales/lt.js
var capitalizeFirstCharacter = (text) => {
  return text.charAt(0).toUpperCase() + text.slice(1);
};
function getUnitTypeFromNumber(number4) {
  const abs = Math.abs(number4);
  const last = abs % 10;
  const last2 = abs % 100;
  if (last2 >= 11 && last2 <= 19 || last === 0)
    return "many";
  if (last === 1)
    return "one";
  return "few";
}
var error28 = () => {
  const Sizable = {
    string: {
      unit: {
        one: "simbolis",
        few: "simboliai",
        many: "simboli\u0173"
      },
      verb: {
        smaller: {
          inclusive: "turi b\u016Bti ne ilgesn\u0117 kaip",
          notInclusive: "turi b\u016Bti trumpesn\u0117 kaip"
        },
        bigger: {
          inclusive: "turi b\u016Bti ne trumpesn\u0117 kaip",
          notInclusive: "turi b\u016Bti ilgesn\u0117 kaip"
        }
      }
    },
    file: {
      unit: {
        one: "baitas",
        few: "baitai",
        many: "bait\u0173"
      },
      verb: {
        smaller: {
          inclusive: "turi b\u016Bti ne didesnis kaip",
          notInclusive: "turi b\u016Bti ma\u017Eesnis kaip"
        },
        bigger: {
          inclusive: "turi b\u016Bti ne ma\u017Eesnis kaip",
          notInclusive: "turi b\u016Bti didesnis kaip"
        }
      }
    },
    array: {
      unit: {
        one: "element\u0105",
        few: "elementus",
        many: "element\u0173"
      },
      verb: {
        smaller: {
          inclusive: "turi tur\u0117ti ne daugiau kaip",
          notInclusive: "turi tur\u0117ti ma\u017Eiau kaip"
        },
        bigger: {
          inclusive: "turi tur\u0117ti ne ma\u017Eiau kaip",
          notInclusive: "turi tur\u0117ti daugiau kaip"
        }
      }
    },
    set: {
      unit: {
        one: "element\u0105",
        few: "elementus",
        many: "element\u0173"
      },
      verb: {
        smaller: {
          inclusive: "turi tur\u0117ti ne daugiau kaip",
          notInclusive: "turi tur\u0117ti ma\u017Eiau kaip"
        },
        bigger: {
          inclusive: "turi tur\u0117ti ne ma\u017Eiau kaip",
          notInclusive: "turi tur\u0117ti daugiau kaip"
        }
      }
    }
  };
  function getSizing(origin, unitType, inclusive, targetShouldBe) {
    const result = Sizable[origin] ?? null;
    if (result === null)
      return result;
    return {
      unit: result.unit[unitType],
      verb: result.verb[targetShouldBe][inclusive ? "inclusive" : "notInclusive"]
    };
  }
  const FormatDictionary = {
    regex: "\u012Fvestis",
    email: "el. pa\u0161to adresas",
    url: "URL",
    emoji: "jaustukas",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO data ir laikas",
    date: "ISO data",
    time: "ISO laikas",
    duration: "ISO trukm\u0117",
    ipv4: "IPv4 adresas",
    ipv6: "IPv6 adresas",
    cidrv4: "IPv4 tinklo prefiksas (CIDR)",
    cidrv6: "IPv6 tinklo prefiksas (CIDR)",
    base64: "base64 u\u017Ekoduota eilut\u0117",
    base64url: "base64url u\u017Ekoduota eilut\u0117",
    json_string: "JSON eilut\u0117",
    e164: "E.164 numeris",
    jwt: "JWT",
    template_literal: "\u012Fvestis"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "skai\u010Dius",
    bigint: "sveikasis skai\u010Dius",
    string: "eilut\u0117",
    boolean: "login\u0117 reik\u0161m\u0117",
    undefined: "neapibr\u0117\u017Eta reik\u0161m\u0117",
    function: "funkcija",
    symbol: "simbolis",
    array: "masyvas",
    object: "objektas",
    null: "nulin\u0117 reik\u0161m\u0117"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Gautas tipas ${received}, o tik\u0117tasi - instanceof ${issue3.expected}`;
        }
        return `Gautas tipas ${received}, o tik\u0117tasi - ${expected}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Privalo b\u016Bti ${stringifyPrimitive(issue3.values[0])}`;
        return `Privalo b\u016Bti vienas i\u0161 ${joinValues(issue3.values, "|")} pasirinkim\u0173`;
      case "too_big": {
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        const sizing = getSizing(issue3.origin, getUnitTypeFromNumber(Number(issue3.maximum)), issue3.inclusive ?? false, "smaller");
        if (sizing?.verb)
          return `${capitalizeFirstCharacter(origin ?? issue3.origin ?? "reik\u0161m\u0117")} ${sizing.verb} ${issue3.maximum.toString()} ${sizing.unit ?? "element\u0173"}`;
        const adj = issue3.inclusive ? "ne didesnis kaip" : "ma\u017Eesnis kaip";
        return `${capitalizeFirstCharacter(origin ?? issue3.origin ?? "reik\u0161m\u0117")} turi b\u016Bti ${adj} ${issue3.maximum.toString()} ${sizing?.unit}`;
      }
      case "too_small": {
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        const sizing = getSizing(issue3.origin, getUnitTypeFromNumber(Number(issue3.minimum)), issue3.inclusive ?? false, "bigger");
        if (sizing?.verb)
          return `${capitalizeFirstCharacter(origin ?? issue3.origin ?? "reik\u0161m\u0117")} ${sizing.verb} ${issue3.minimum.toString()} ${sizing.unit ?? "element\u0173"}`;
        const adj = issue3.inclusive ? "ne ma\u017Eesnis kaip" : "didesnis kaip";
        return `${capitalizeFirstCharacter(origin ?? issue3.origin ?? "reik\u0161m\u0117")} turi b\u016Bti ${adj} ${issue3.minimum.toString()} ${sizing?.unit}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Eilut\u0117 privalo prasid\u0117ti "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Eilut\u0117 privalo pasibaigti "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Eilut\u0117 privalo \u012Ftraukti "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Eilut\u0117 privalo atitikti ${_issue.pattern}`;
        return `Neteisingas ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Skai\u010Dius privalo b\u016Bti ${issue3.divisor} kartotinis.`;
      case "unrecognized_keys":
        return `Neatpa\u017Eint${issue3.keys.length > 1 ? "i" : "as"} rakt${issue3.keys.length > 1 ? "ai" : "as"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return "Rastas klaidingas raktas";
      case "invalid_union":
        return "Klaidinga \u012Fvestis";
      case "invalid_element": {
        const origin = TypeDictionary[issue3.origin] ?? issue3.origin;
        return `${capitalizeFirstCharacter(origin ?? issue3.origin ?? "reik\u0161m\u0117")} turi klaiding\u0105 \u012Fvest\u012F`;
      }
      default:
        return "Klaidinga \u012Fvestis";
    }
  };
};
function lt_default() {
  return {
    localeError: error28()
  };
}

// node_modules/zod/v4/locales/mk.js
var error29 = () => {
  const Sizable = {
    string: { unit: "\u0437\u043D\u0430\u0446\u0438", verb: "\u0434\u0430 \u0438\u043C\u0430\u0430\u0442" },
    file: { unit: "\u0431\u0430\u0458\u0442\u0438", verb: "\u0434\u0430 \u0438\u043C\u0430\u0430\u0442" },
    array: { unit: "\u0441\u0442\u0430\u0432\u043A\u0438", verb: "\u0434\u0430 \u0438\u043C\u0430\u0430\u0442" },
    set: { unit: "\u0441\u0442\u0430\u0432\u043A\u0438", verb: "\u0434\u0430 \u0438\u043C\u0430\u0430\u0442" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0432\u043D\u0435\u0441",
    email: "\u0430\u0434\u0440\u0435\u0441\u0430 \u043D\u0430 \u0435-\u043F\u043E\u0448\u0442\u0430",
    url: "URL",
    emoji: "\u0435\u043C\u043E\u045F\u0438",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0434\u0430\u0442\u0443\u043C \u0438 \u0432\u0440\u0435\u043C\u0435",
    date: "ISO \u0434\u0430\u0442\u0443\u043C",
    time: "ISO \u0432\u0440\u0435\u043C\u0435",
    duration: "ISO \u0432\u0440\u0435\u043C\u0435\u0442\u0440\u0430\u0435\u045A\u0435",
    ipv4: "IPv4 \u0430\u0434\u0440\u0435\u0441\u0430",
    ipv6: "IPv6 \u0430\u0434\u0440\u0435\u0441\u0430",
    cidrv4: "IPv4 \u043E\u043F\u0441\u0435\u0433",
    cidrv6: "IPv6 \u043E\u043F\u0441\u0435\u0433",
    base64: "base64-\u0435\u043D\u043A\u043E\u0434\u0438\u0440\u0430\u043D\u0430 \u043D\u0438\u0437\u0430",
    base64url: "base64url-\u0435\u043D\u043A\u043E\u0434\u0438\u0440\u0430\u043D\u0430 \u043D\u0438\u0437\u0430",
    json_string: "JSON \u043D\u0438\u0437\u0430",
    e164: "E.164 \u0431\u0440\u043E\u0458",
    jwt: "JWT",
    template_literal: "\u0432\u043D\u0435\u0441"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0431\u0440\u043E\u0458",
    array: "\u043D\u0438\u0437\u0430"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0413\u0440\u0435\u0448\u0435\u043D \u0432\u043D\u0435\u0441: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 instanceof ${issue3.expected}, \u043F\u0440\u0438\u043C\u0435\u043D\u043E ${received}`;
        }
        return `\u0413\u0440\u0435\u0448\u0435\u043D \u0432\u043D\u0435\u0441: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 ${expected}, \u043F\u0440\u0438\u043C\u0435\u043D\u043E ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Invalid input: expected ${stringifyPrimitive(issue3.values[0])}`;
        return `\u0413\u0440\u0435\u0448\u0430\u043D\u0430 \u043E\u043F\u0446\u0438\u0458\u0430: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 \u0435\u0434\u043D\u0430 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u041F\u0440\u0435\u043C\u043D\u043E\u0433\u0443 \u0433\u043E\u043B\u0435\u043C: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 ${issue3.origin ?? "\u0432\u0440\u0435\u0434\u043D\u043E\u0441\u0442\u0430"} \u0434\u0430 \u0438\u043C\u0430 ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0438"}`;
        return `\u041F\u0440\u0435\u043C\u043D\u043E\u0433\u0443 \u0433\u043E\u043B\u0435\u043C: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 ${issue3.origin ?? "\u0432\u0440\u0435\u0434\u043D\u043E\u0441\u0442\u0430"} \u0434\u0430 \u0431\u0438\u0434\u0435 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u041F\u0440\u0435\u043C\u043D\u043E\u0433\u0443 \u043C\u0430\u043B: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 ${issue3.origin} \u0434\u0430 \u0438\u043C\u0430 ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u041F\u0440\u0435\u043C\u043D\u043E\u0433\u0443 \u043C\u0430\u043B: \u0441\u0435 \u043E\u0447\u0435\u043A\u0443\u0432\u0430 ${issue3.origin} \u0434\u0430 \u0431\u0438\u0434\u0435 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u041D\u0435\u0432\u0430\u0436\u0435\u0447\u043A\u0430 \u043D\u0438\u0437\u0430: \u043C\u043E\u0440\u0430 \u0434\u0430 \u0437\u0430\u043F\u043E\u0447\u043D\u0443\u0432\u0430 \u0441\u043E "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u041D\u0435\u0432\u0430\u0436\u0435\u0447\u043A\u0430 \u043D\u0438\u0437\u0430: \u043C\u043E\u0440\u0430 \u0434\u0430 \u0437\u0430\u0432\u0440\u0448\u0443\u0432\u0430 \u0441\u043E "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u041D\u0435\u0432\u0430\u0436\u0435\u0447\u043A\u0430 \u043D\u0438\u0437\u0430: \u043C\u043E\u0440\u0430 \u0434\u0430 \u0432\u043A\u043B\u0443\u0447\u0443\u0432\u0430 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u041D\u0435\u0432\u0430\u0436\u0435\u0447\u043A\u0430 \u043D\u0438\u0437\u0430: \u043C\u043E\u0440\u0430 \u0434\u0430 \u043E\u0434\u0433\u043E\u0430\u0440\u0430 \u043D\u0430 \u043F\u0430\u0442\u0435\u0440\u043D\u043E\u0442 ${_issue.pattern}`;
        return `Invalid ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u0413\u0440\u0435\u0448\u0435\u043D \u0431\u0440\u043E\u0458: \u043C\u043E\u0440\u0430 \u0434\u0430 \u0431\u0438\u0434\u0435 \u0434\u0435\u043B\u0438\u0432 \u0441\u043E ${issue3.divisor}`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "\u041D\u0435\u043F\u0440\u0435\u043F\u043E\u0437\u043D\u0430\u0435\u043D\u0438 \u043A\u043B\u0443\u0447\u0435\u0432\u0438" : "\u041D\u0435\u043F\u0440\u0435\u043F\u043E\u0437\u043D\u0430\u0435\u043D \u043A\u043B\u0443\u0447"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u0413\u0440\u0435\u0448\u0435\u043D \u043A\u043B\u0443\u0447 \u0432\u043E ${issue3.origin}`;
      case "invalid_union":
        return "\u0413\u0440\u0435\u0448\u0435\u043D \u0432\u043D\u0435\u0441";
      case "invalid_element":
        return `\u0413\u0440\u0435\u0448\u043D\u0430 \u0432\u0440\u0435\u0434\u043D\u043E\u0441\u0442 \u0432\u043E ${issue3.origin}`;
      default:
        return `\u0413\u0440\u0435\u0448\u0435\u043D \u0432\u043D\u0435\u0441`;
    }
  };
};
function mk_default() {
  return {
    localeError: error29()
  };
}

// node_modules/zod/v4/locales/ms.js
var error30 = () => {
  const Sizable = {
    string: { unit: "aksara", verb: "mempunyai" },
    file: { unit: "bait", verb: "mempunyai" },
    array: { unit: "elemen", verb: "mempunyai" },
    set: { unit: "elemen", verb: "mempunyai" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "alamat e-mel",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "tarikh masa ISO",
    date: "tarikh ISO",
    time: "masa ISO",
    duration: "tempoh ISO",
    ipv4: "alamat IPv4",
    ipv6: "alamat IPv6",
    cidrv4: "julat IPv4",
    cidrv6: "julat IPv6",
    base64: "string dikodkan base64",
    base64url: "string dikodkan base64url",
    json_string: "string JSON",
    e164: "nombor E.164",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "nombor"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Input tidak sah: dijangka instanceof ${issue3.expected}, diterima ${received}`;
        }
        return `Input tidak sah: dijangka ${expected}, diterima ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Input tidak sah: dijangka ${stringifyPrimitive(issue3.values[0])}`;
        return `Pilihan tidak sah: dijangka salah satu daripada ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Terlalu besar: dijangka ${issue3.origin ?? "nilai"} ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elemen"}`;
        return `Terlalu besar: dijangka ${issue3.origin ?? "nilai"} adalah ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Terlalu kecil: dijangka ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Terlalu kecil: dijangka ${issue3.origin} adalah ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `String tidak sah: mesti bermula dengan "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `String tidak sah: mesti berakhir dengan "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `String tidak sah: mesti mengandungi "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `String tidak sah: mesti sepadan dengan corak ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} tidak sah`;
      }
      case "not_multiple_of":
        return `Nombor tidak sah: perlu gandaan ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Kunci tidak dikenali: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Kunci tidak sah dalam ${issue3.origin}`;
      case "invalid_union":
        return "Input tidak sah";
      case "invalid_element":
        return `Nilai tidak sah dalam ${issue3.origin}`;
      default:
        return `Input tidak sah`;
    }
  };
};
function ms_default() {
  return {
    localeError: error30()
  };
}

// node_modules/zod/v4/locales/nl.js
var error31 = () => {
  const Sizable = {
    string: { unit: "tekens", verb: "heeft" },
    file: { unit: "bytes", verb: "heeft" },
    array: { unit: "elementen", verb: "heeft" },
    set: { unit: "elementen", verb: "heeft" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "invoer",
    email: "emailadres",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO datum en tijd",
    date: "ISO datum",
    time: "ISO tijd",
    duration: "ISO duur",
    ipv4: "IPv4-adres",
    ipv6: "IPv6-adres",
    cidrv4: "IPv4-bereik",
    cidrv6: "IPv6-bereik",
    base64: "base64-gecodeerde tekst",
    base64url: "base64 URL-gecodeerde tekst",
    json_string: "JSON string",
    e164: "E.164-nummer",
    jwt: "JWT",
    template_literal: "invoer"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "getal"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ongeldige invoer: verwacht instanceof ${issue3.expected}, ontving ${received}`;
        }
        return `Ongeldige invoer: verwacht ${expected}, ontving ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ongeldige invoer: verwacht ${stringifyPrimitive(issue3.values[0])}`;
        return `Ongeldige optie: verwacht \xE9\xE9n van ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        const longName = issue3.origin === "date" ? "laat" : issue3.origin === "string" ? "lang" : "groot";
        if (sizing)
          return `Te ${longName}: verwacht dat ${issue3.origin ?? "waarde"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementen"} ${sizing.verb}`;
        return `Te ${longName}: verwacht dat ${issue3.origin ?? "waarde"} ${adj}${issue3.maximum.toString()} is`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        const shortName = issue3.origin === "date" ? "vroeg" : issue3.origin === "string" ? "kort" : "klein";
        if (sizing) {
          return `Te ${shortName}: verwacht dat ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit} ${sizing.verb}`;
        }
        return `Te ${shortName}: verwacht dat ${issue3.origin} ${adj}${issue3.minimum.toString()} is`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Ongeldige tekst: moet met "${_issue.prefix}" beginnen`;
        }
        if (_issue.format === "ends_with")
          return `Ongeldige tekst: moet op "${_issue.suffix}" eindigen`;
        if (_issue.format === "includes")
          return `Ongeldige tekst: moet "${_issue.includes}" bevatten`;
        if (_issue.format === "regex")
          return `Ongeldige tekst: moet overeenkomen met patroon ${_issue.pattern}`;
        return `Ongeldig: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ongeldig getal: moet een veelvoud van ${issue3.divisor} zijn`;
      case "unrecognized_keys":
        return `Onbekende key${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Ongeldige key in ${issue3.origin}`;
      case "invalid_union":
        return "Ongeldige invoer";
      case "invalid_element":
        return `Ongeldige waarde in ${issue3.origin}`;
      default:
        return `Ongeldige invoer`;
    }
  };
};
function nl_default() {
  return {
    localeError: error31()
  };
}

// node_modules/zod/v4/locales/no.js
var error32 = () => {
  const Sizable = {
    string: { unit: "tegn", verb: "\xE5 ha" },
    file: { unit: "bytes", verb: "\xE5 ha" },
    array: { unit: "elementer", verb: "\xE5 inneholde" },
    set: { unit: "elementer", verb: "\xE5 inneholde" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "input",
    email: "e-postadresse",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO dato- og klokkeslett",
    date: "ISO-dato",
    time: "ISO-klokkeslett",
    duration: "ISO-varighet",
    ipv4: "IPv4-omr\xE5de",
    ipv6: "IPv6-omr\xE5de",
    cidrv4: "IPv4-spekter",
    cidrv6: "IPv6-spekter",
    base64: "base64-enkodet streng",
    base64url: "base64url-enkodet streng",
    json_string: "JSON-streng",
    e164: "E.164-nummer",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "tall",
    array: "liste"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ugyldig input: forventet instanceof ${issue3.expected}, fikk ${received}`;
        }
        return `Ugyldig input: forventet ${expected}, fikk ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ugyldig verdi: forventet ${stringifyPrimitive(issue3.values[0])}`;
        return `Ugyldig valg: forventet en av ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `For stor(t): forventet ${issue3.origin ?? "value"} til \xE5 ha ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementer"}`;
        return `For stor(t): forventet ${issue3.origin ?? "value"} til \xE5 ha ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `For lite(n): forventet ${issue3.origin} til \xE5 ha ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `For lite(n): forventet ${issue3.origin} til \xE5 ha ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Ugyldig streng: m\xE5 starte med "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Ugyldig streng: m\xE5 ende med "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Ugyldig streng: m\xE5 inneholde "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Ugyldig streng: m\xE5 matche m\xF8nsteret ${_issue.pattern}`;
        return `Ugyldig ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ugyldig tall: m\xE5 v\xE6re et multiplum av ${issue3.divisor}`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "Ukjente n\xF8kler" : "Ukjent n\xF8kkel"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Ugyldig n\xF8kkel i ${issue3.origin}`;
      case "invalid_union":
        return "Ugyldig input";
      case "invalid_element":
        return `Ugyldig verdi i ${issue3.origin}`;
      default:
        return `Ugyldig input`;
    }
  };
};
function no_default() {
  return {
    localeError: error32()
  };
}

// node_modules/zod/v4/locales/ota.js
var error33 = () => {
  const Sizable = {
    string: { unit: "harf", verb: "olmal\u0131d\u0131r" },
    file: { unit: "bayt", verb: "olmal\u0131d\u0131r" },
    array: { unit: "unsur", verb: "olmal\u0131d\u0131r" },
    set: { unit: "unsur", verb: "olmal\u0131d\u0131r" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "giren",
    email: "epostag\xE2h",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO heng\xE2m\u0131",
    date: "ISO tarihi",
    time: "ISO zaman\u0131",
    duration: "ISO m\xFCddeti",
    ipv4: "IPv4 ni\u015F\xE2n\u0131",
    ipv6: "IPv6 ni\u015F\xE2n\u0131",
    cidrv4: "IPv4 menzili",
    cidrv6: "IPv6 menzili",
    base64: "base64-\u015Fifreli metin",
    base64url: "base64url-\u015Fifreli metin",
    json_string: "JSON metin",
    e164: "E.164 say\u0131s\u0131",
    jwt: "JWT",
    template_literal: "giren"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "numara",
    array: "saf",
    null: "gayb"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `F\xE2sit giren: umulan instanceof ${issue3.expected}, al\u0131nan ${received}`;
        }
        return `F\xE2sit giren: umulan ${expected}, al\u0131nan ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `F\xE2sit giren: umulan ${stringifyPrimitive(issue3.values[0])}`;
        return `F\xE2sit tercih: m\xFBteberler ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Fazla b\xFCy\xFCk: ${issue3.origin ?? "value"}, ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elements"} sahip olmal\u0131yd\u0131.`;
        return `Fazla b\xFCy\xFCk: ${issue3.origin ?? "value"}, ${adj}${issue3.maximum.toString()} olmal\u0131yd\u0131.`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Fazla k\xFC\xE7\xFCk: ${issue3.origin}, ${adj}${issue3.minimum.toString()} ${sizing.unit} sahip olmal\u0131yd\u0131.`;
        }
        return `Fazla k\xFC\xE7\xFCk: ${issue3.origin}, ${adj}${issue3.minimum.toString()} olmal\u0131yd\u0131.`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `F\xE2sit metin: "${_issue.prefix}" ile ba\u015Flamal\u0131.`;
        if (_issue.format === "ends_with")
          return `F\xE2sit metin: "${_issue.suffix}" ile bitmeli.`;
        if (_issue.format === "includes")
          return `F\xE2sit metin: "${_issue.includes}" ihtiv\xE2 etmeli.`;
        if (_issue.format === "regex")
          return `F\xE2sit metin: ${_issue.pattern} nak\u015F\u0131na uymal\u0131.`;
        return `F\xE2sit ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `F\xE2sit say\u0131: ${issue3.divisor} kat\u0131 olmal\u0131yd\u0131.`;
      case "unrecognized_keys":
        return `Tan\u0131nmayan anahtar ${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} i\xE7in tan\u0131nmayan anahtar var.`;
      case "invalid_union":
        return "Giren tan\u0131namad\u0131.";
      case "invalid_element":
        return `${issue3.origin} i\xE7in tan\u0131nmayan k\u0131ymet var.`;
      default:
        return `K\u0131ymet tan\u0131namad\u0131.`;
    }
  };
};
function ota_default() {
  return {
    localeError: error33()
  };
}

// node_modules/zod/v4/locales/ps.js
var error34 = () => {
  const Sizable = {
    string: { unit: "\u062A\u0648\u06A9\u064A", verb: "\u0648\u0644\u0631\u064A" },
    file: { unit: "\u0628\u0627\u06CC\u067C\u0633", verb: "\u0648\u0644\u0631\u064A" },
    array: { unit: "\u062A\u0648\u06A9\u064A", verb: "\u0648\u0644\u0631\u064A" },
    set: { unit: "\u062A\u0648\u06A9\u064A", verb: "\u0648\u0644\u0631\u064A" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0648\u0631\u0648\u062F\u064A",
    email: "\u0628\u0631\u06CC\u069A\u0646\u0627\u0644\u06CC\u06A9",
    url: "\u06CC\u0648 \u0622\u0631 \u0627\u0644",
    emoji: "\u0627\u06CC\u0645\u0648\u062C\u064A",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u0646\u06CC\u067C\u0647 \u0627\u0648 \u0648\u062E\u062A",
    date: "\u0646\u06D0\u067C\u0647",
    time: "\u0648\u062E\u062A",
    duration: "\u0645\u0648\u062F\u0647",
    ipv4: "\u062F IPv4 \u067E\u062A\u0647",
    ipv6: "\u062F IPv6 \u067E\u062A\u0647",
    cidrv4: "\u062F IPv4 \u0633\u0627\u062D\u0647",
    cidrv6: "\u062F IPv6 \u0633\u0627\u062D\u0647",
    base64: "base64-encoded \u0645\u062A\u0646",
    base64url: "base64url-encoded \u0645\u062A\u0646",
    json_string: "JSON \u0645\u062A\u0646",
    e164: "\u062F E.164 \u0634\u0645\u06D0\u0631\u0647",
    jwt: "JWT",
    template_literal: "\u0648\u0631\u0648\u062F\u064A"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0639\u062F\u062F",
    array: "\u0627\u0631\u06D0"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0646\u0627\u0633\u0645 \u0648\u0631\u0648\u062F\u064A: \u0628\u0627\u06CC\u062F instanceof ${issue3.expected} \u0648\u0627\u06CC, \u0645\u06AB\u0631 ${received} \u062A\u0631\u0644\u0627\u0633\u0647 \u0634\u0648`;
        }
        return `\u0646\u0627\u0633\u0645 \u0648\u0631\u0648\u062F\u064A: \u0628\u0627\u06CC\u062F ${expected} \u0648\u0627\u06CC, \u0645\u06AB\u0631 ${received} \u062A\u0631\u0644\u0627\u0633\u0647 \u0634\u0648`;
      }
      case "invalid_value":
        if (issue3.values.length === 1) {
          return `\u0646\u0627\u0633\u0645 \u0648\u0631\u0648\u062F\u064A: \u0628\u0627\u06CC\u062F ${stringifyPrimitive(issue3.values[0])} \u0648\u0627\u06CC`;
        }
        return `\u0646\u0627\u0633\u0645 \u0627\u0646\u062A\u062E\u0627\u0628: \u0628\u0627\u06CC\u062F \u06CC\u0648 \u0644\u0647 ${joinValues(issue3.values, "|")} \u0685\u062E\u0647 \u0648\u0627\u06CC`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0689\u06CC\u0631 \u0644\u0648\u06CC: ${issue3.origin ?? "\u0627\u0631\u0632\u069A\u062A"} \u0628\u0627\u06CC\u062F ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0639\u0646\u0635\u0631\u0648\u0646\u0647"} \u0648\u0644\u0631\u064A`;
        }
        return `\u0689\u06CC\u0631 \u0644\u0648\u06CC: ${issue3.origin ?? "\u0627\u0631\u0632\u069A\u062A"} \u0628\u0627\u06CC\u062F ${adj}${issue3.maximum.toString()} \u0648\u064A`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0689\u06CC\u0631 \u06A9\u0648\u0686\u0646\u06CC: ${issue3.origin} \u0628\u0627\u06CC\u062F ${adj}${issue3.minimum.toString()} ${sizing.unit} \u0648\u0644\u0631\u064A`;
        }
        return `\u0689\u06CC\u0631 \u06A9\u0648\u0686\u0646\u06CC: ${issue3.origin} \u0628\u0627\u06CC\u062F ${adj}${issue3.minimum.toString()} \u0648\u064A`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u0646\u0627\u0633\u0645 \u0645\u062A\u0646: \u0628\u0627\u06CC\u062F \u062F "${_issue.prefix}" \u0633\u0631\u0647 \u067E\u06CC\u0644 \u0634\u064A`;
        }
        if (_issue.format === "ends_with") {
          return `\u0646\u0627\u0633\u0645 \u0645\u062A\u0646: \u0628\u0627\u06CC\u062F \u062F "${_issue.suffix}" \u0633\u0631\u0647 \u067E\u0627\u06CC \u062A\u0647 \u0648\u0631\u0633\u064A\u0696\u064A`;
        }
        if (_issue.format === "includes") {
          return `\u0646\u0627\u0633\u0645 \u0645\u062A\u0646: \u0628\u0627\u06CC\u062F "${_issue.includes}" \u0648\u0644\u0631\u064A`;
        }
        if (_issue.format === "regex") {
          return `\u0646\u0627\u0633\u0645 \u0645\u062A\u0646: \u0628\u0627\u06CC\u062F \u062F ${_issue.pattern} \u0633\u0631\u0647 \u0645\u0637\u0627\u0628\u0642\u062A \u0648\u0644\u0631\u064A`;
        }
        return `${FormatDictionary[_issue.format] ?? issue3.format} \u0646\u0627\u0633\u0645 \u062F\u06CC`;
      }
      case "not_multiple_of":
        return `\u0646\u0627\u0633\u0645 \u0639\u062F\u062F: \u0628\u0627\u06CC\u062F \u062F ${issue3.divisor} \u0645\u0636\u0631\u0628 \u0648\u064A`;
      case "unrecognized_keys":
        return `\u0646\u0627\u0633\u0645 ${issue3.keys.length > 1 ? "\u06A9\u0644\u06CC\u0689\u0648\u0646\u0647" : "\u06A9\u0644\u06CC\u0689"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u0646\u0627\u0633\u0645 \u06A9\u0644\u06CC\u0689 \u067E\u0647 ${issue3.origin} \u06A9\u06D0`;
      case "invalid_union":
        return `\u0646\u0627\u0633\u0645\u0647 \u0648\u0631\u0648\u062F\u064A`;
      case "invalid_element":
        return `\u0646\u0627\u0633\u0645 \u0639\u0646\u0635\u0631 \u067E\u0647 ${issue3.origin} \u06A9\u06D0`;
      default:
        return `\u0646\u0627\u0633\u0645\u0647 \u0648\u0631\u0648\u062F\u064A`;
    }
  };
};
function ps_default() {
  return {
    localeError: error34()
  };
}

// node_modules/zod/v4/locales/pl.js
var error35 = () => {
  const Sizable = {
    string: { unit: "znak\xF3w", verb: "mie\u0107" },
    file: { unit: "bajt\xF3w", verb: "mie\u0107" },
    array: { unit: "element\xF3w", verb: "mie\u0107" },
    set: { unit: "element\xF3w", verb: "mie\u0107" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "wyra\u017Cenie",
    email: "adres email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "data i godzina w formacie ISO",
    date: "data w formacie ISO",
    time: "godzina w formacie ISO",
    duration: "czas trwania ISO",
    ipv4: "adres IPv4",
    ipv6: "adres IPv6",
    cidrv4: "zakres IPv4",
    cidrv6: "zakres IPv6",
    base64: "ci\u0105g znak\xF3w zakodowany w formacie base64",
    base64url: "ci\u0105g znak\xF3w zakodowany w formacie base64url",
    json_string: "ci\u0105g znak\xF3w w formacie JSON",
    e164: "liczba E.164",
    jwt: "JWT",
    template_literal: "wej\u015Bcie"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "liczba",
    array: "tablica"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Nieprawid\u0142owe dane wej\u015Bciowe: oczekiwano instanceof ${issue3.expected}, otrzymano ${received}`;
        }
        return `Nieprawid\u0142owe dane wej\u015Bciowe: oczekiwano ${expected}, otrzymano ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Nieprawid\u0142owe dane wej\u015Bciowe: oczekiwano ${stringifyPrimitive(issue3.values[0])}`;
        return `Nieprawid\u0142owa opcja: oczekiwano jednej z warto\u015Bci ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Za du\u017Ca warto\u015B\u0107: oczekiwano, \u017Ce ${issue3.origin ?? "warto\u015B\u0107"} b\u0119dzie mie\u0107 ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "element\xF3w"}`;
        }
        return `Zbyt du\u017C(y/a/e): oczekiwano, \u017Ce ${issue3.origin ?? "warto\u015B\u0107"} b\u0119dzie wynosi\u0107 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Za ma\u0142a warto\u015B\u0107: oczekiwano, \u017Ce ${issue3.origin ?? "warto\u015B\u0107"} b\u0119dzie mie\u0107 ${adj}${issue3.minimum.toString()} ${sizing.unit ?? "element\xF3w"}`;
        }
        return `Zbyt ma\u0142(y/a/e): oczekiwano, \u017Ce ${issue3.origin ?? "warto\u015B\u0107"} b\u0119dzie wynosi\u0107 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Nieprawid\u0142owy ci\u0105g znak\xF3w: musi zaczyna\u0107 si\u0119 od "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Nieprawid\u0142owy ci\u0105g znak\xF3w: musi ko\u0144czy\u0107 si\u0119 na "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Nieprawid\u0142owy ci\u0105g znak\xF3w: musi zawiera\u0107 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Nieprawid\u0142owy ci\u0105g znak\xF3w: musi odpowiada\u0107 wzorcowi ${_issue.pattern}`;
        return `Nieprawid\u0142ow(y/a/e) ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Nieprawid\u0142owa liczba: musi by\u0107 wielokrotno\u015Bci\u0105 ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Nierozpoznane klucze${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Nieprawid\u0142owy klucz w ${issue3.origin}`;
      case "invalid_union":
        return "Nieprawid\u0142owe dane wej\u015Bciowe";
      case "invalid_element":
        return `Nieprawid\u0142owa warto\u015B\u0107 w ${issue3.origin}`;
      default:
        return `Nieprawid\u0142owe dane wej\u015Bciowe`;
    }
  };
};
function pl_default() {
  return {
    localeError: error35()
  };
}

// node_modules/zod/v4/locales/pt.js
var error36 = () => {
  const Sizable = {
    string: { unit: "caracteres", verb: "ter" },
    file: { unit: "bytes", verb: "ter" },
    array: { unit: "itens", verb: "ter" },
    set: { unit: "itens", verb: "ter" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "padr\xE3o",
    email: "endere\xE7o de e-mail",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "data e hora ISO",
    date: "data ISO",
    time: "hora ISO",
    duration: "dura\xE7\xE3o ISO",
    ipv4: "endere\xE7o IPv4",
    ipv6: "endere\xE7o IPv6",
    cidrv4: "faixa de IPv4",
    cidrv6: "faixa de IPv6",
    base64: "texto codificado em base64",
    base64url: "URL codificada em base64",
    json_string: "texto JSON",
    e164: "n\xFAmero E.164",
    jwt: "JWT",
    template_literal: "entrada"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "n\xFAmero",
    null: "nulo"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Tipo inv\xE1lido: esperado instanceof ${issue3.expected}, recebido ${received}`;
        }
        return `Tipo inv\xE1lido: esperado ${expected}, recebido ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Entrada inv\xE1lida: esperado ${stringifyPrimitive(issue3.values[0])}`;
        return `Op\xE7\xE3o inv\xE1lida: esperada uma das ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Muito grande: esperado que ${issue3.origin ?? "valor"} tivesse ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementos"}`;
        return `Muito grande: esperado que ${issue3.origin ?? "valor"} fosse ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Muito pequeno: esperado que ${issue3.origin} tivesse ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Muito pequeno: esperado que ${issue3.origin} fosse ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Texto inv\xE1lido: deve come\xE7ar com "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Texto inv\xE1lido: deve terminar com "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Texto inv\xE1lido: deve incluir "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Texto inv\xE1lido: deve corresponder ao padr\xE3o ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} inv\xE1lido`;
      }
      case "not_multiple_of":
        return `N\xFAmero inv\xE1lido: deve ser m\xFAltiplo de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Chave${issue3.keys.length > 1 ? "s" : ""} desconhecida${issue3.keys.length > 1 ? "s" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Chave inv\xE1lida em ${issue3.origin}`;
      case "invalid_union":
        return "Entrada inv\xE1lida";
      case "invalid_element":
        return `Valor inv\xE1lido em ${issue3.origin}`;
      default:
        return `Campo inv\xE1lido`;
    }
  };
};
function pt_default() {
  return {
    localeError: error36()
  };
}

// node_modules/zod/v4/locales/ro.js
var error37 = () => {
  const Sizable = {
    string: { unit: "caractere", verb: "s\u0103 aib\u0103" },
    file: { unit: "octe\u021Bi", verb: "s\u0103 aib\u0103" },
    array: { unit: "elemente", verb: "s\u0103 aib\u0103" },
    set: { unit: "elemente", verb: "s\u0103 aib\u0103" },
    map: { unit: "intr\u0103ri", verb: "s\u0103 aib\u0103" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "intrare",
    email: "adres\u0103 de email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "dat\u0103 \u0219i or\u0103 ISO",
    date: "dat\u0103 ISO",
    time: "or\u0103 ISO",
    duration: "durat\u0103 ISO",
    ipv4: "adres\u0103 IPv4",
    ipv6: "adres\u0103 IPv6",
    mac: "adres\u0103 MAC",
    cidrv4: "interval IPv4",
    cidrv6: "interval IPv6",
    base64: "\u0219ir codat base64",
    base64url: "\u0219ir codat base64url",
    json_string: "\u0219ir JSON",
    e164: "num\u0103r E.164",
    jwt: "JWT",
    template_literal: "intrare"
  };
  const TypeDictionary = {
    nan: "NaN",
    string: "\u0219ir",
    number: "num\u0103r",
    boolean: "boolean",
    function: "func\u021Bie",
    array: "matrice",
    object: "obiect",
    undefined: "nedefinit",
    symbol: "simbol",
    bigint: "num\u0103r mare",
    void: "void",
    never: "never",
    map: "hart\u0103",
    set: "set"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        return `Intrare invalid\u0103: a\u0219teptat ${expected}, primit ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Intrare invalid\u0103: a\u0219teptat ${stringifyPrimitive(issue3.values[0])}`;
        return `Op\u021Biune invalid\u0103: a\u0219teptat una dintre ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Prea mare: a\u0219teptat ca ${issue3.origin ?? "valoarea"} ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elemente"}`;
        return `Prea mare: a\u0219teptat ca ${issue3.origin ?? "valoarea"} s\u0103 fie ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Prea mic: a\u0219teptat ca ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Prea mic: a\u0219teptat ca ${issue3.origin} s\u0103 fie ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u0218ir invalid: trebuie s\u0103 \xEEnceap\u0103 cu "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u0218ir invalid: trebuie s\u0103 se termine cu "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u0218ir invalid: trebuie s\u0103 includ\u0103 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u0218ir invalid: trebuie s\u0103 se potriveasc\u0103 cu modelul ${_issue.pattern}`;
        return `Format invalid: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Num\u0103r invalid: trebuie s\u0103 fie multiplu de ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Chei nerecunoscute: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Cheie invalid\u0103 \xEEn ${issue3.origin}`;
      case "invalid_union":
        return "Intrare invalid\u0103";
      case "invalid_element":
        return `Valoare invalid\u0103 \xEEn ${issue3.origin}`;
      default:
        return `Intrare invalid\u0103`;
    }
  };
};
function ro_default() {
  return {
    localeError: error37()
  };
}

// node_modules/zod/v4/locales/ru.js
function getRussianPlural(count, one, few, many) {
  const absCount = Math.abs(count);
  const lastDigit = absCount % 10;
  const lastTwoDigits = absCount % 100;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
    return many;
  }
  if (lastDigit === 1) {
    return one;
  }
  if (lastDigit >= 2 && lastDigit <= 4) {
    return few;
  }
  return many;
}
var error38 = () => {
  const Sizable = {
    string: {
      unit: {
        one: "\u0441\u0438\u043C\u0432\u043E\u043B",
        few: "\u0441\u0438\u043C\u0432\u043E\u043B\u0430",
        many: "\u0441\u0438\u043C\u0432\u043E\u043B\u043E\u0432"
      },
      verb: "\u0438\u043C\u0435\u0442\u044C"
    },
    file: {
      unit: {
        one: "\u0431\u0430\u0439\u0442",
        few: "\u0431\u0430\u0439\u0442\u0430",
        many: "\u0431\u0430\u0439\u0442"
      },
      verb: "\u0438\u043C\u0435\u0442\u044C"
    },
    array: {
      unit: {
        one: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442",
        few: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u0430",
        many: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u043E\u0432"
      },
      verb: "\u0438\u043C\u0435\u0442\u044C"
    },
    set: {
      unit: {
        one: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442",
        few: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u0430",
        many: "\u044D\u043B\u0435\u043C\u0435\u043D\u0442\u043E\u0432"
      },
      verb: "\u0438\u043C\u0435\u0442\u044C"
    }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0432\u0432\u043E\u0434",
    email: "email \u0430\u0434\u0440\u0435\u0441",
    url: "URL",
    emoji: "\u044D\u043C\u043E\u0434\u0437\u0438",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0434\u0430\u0442\u0430 \u0438 \u0432\u0440\u0435\u043C\u044F",
    date: "ISO \u0434\u0430\u0442\u0430",
    time: "ISO \u0432\u0440\u0435\u043C\u044F",
    duration: "ISO \u0434\u043B\u0438\u0442\u0435\u043B\u044C\u043D\u043E\u0441\u0442\u044C",
    ipv4: "IPv4 \u0430\u0434\u0440\u0435\u0441",
    ipv6: "IPv6 \u0430\u0434\u0440\u0435\u0441",
    cidrv4: "IPv4 \u0434\u0438\u0430\u043F\u0430\u0437\u043E\u043D",
    cidrv6: "IPv6 \u0434\u0438\u0430\u043F\u0430\u0437\u043E\u043D",
    base64: "\u0441\u0442\u0440\u043E\u043A\u0430 \u0432 \u0444\u043E\u0440\u043C\u0430\u0442\u0435 base64",
    base64url: "\u0441\u0442\u0440\u043E\u043A\u0430 \u0432 \u0444\u043E\u0440\u043C\u0430\u0442\u0435 base64url",
    json_string: "JSON \u0441\u0442\u0440\u043E\u043A\u0430",
    e164: "\u043D\u043E\u043C\u0435\u0440 E.164",
    jwt: "JWT",
    template_literal: "\u0432\u0432\u043E\u0434"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0447\u0438\u0441\u043B\u043E",
    array: "\u043C\u0430\u0441\u0441\u0438\u0432"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 \u0432\u0432\u043E\u0434: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C instanceof ${issue3.expected}, \u043F\u043E\u043B\u0443\u0447\u0435\u043D\u043E ${received}`;
        }
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 \u0432\u0432\u043E\u0434: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C ${expected}, \u043F\u043E\u043B\u0443\u0447\u0435\u043D\u043E ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 \u0432\u0432\u043E\u0434: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C ${stringifyPrimitive(issue3.values[0])}`;
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 \u0432\u0430\u0440\u0438\u0430\u043D\u0442: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u043E\u0434\u043D\u043E \u0438\u0437 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const maxValue = Number(issue3.maximum);
          const unit = getRussianPlural(maxValue, sizing.unit.one, sizing.unit.few, sizing.unit.many);
          return `\u0421\u043B\u0438\u0448\u043A\u043E\u043C \u0431\u043E\u043B\u044C\u0448\u043E\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C, \u0447\u0442\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435"} \u0431\u0443\u0434\u0435\u0442 \u0438\u043C\u0435\u0442\u044C ${adj}${issue3.maximum.toString()} ${unit}`;
        }
        return `\u0421\u043B\u0438\u0448\u043A\u043E\u043C \u0431\u043E\u043B\u044C\u0448\u043E\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C, \u0447\u0442\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435"} \u0431\u0443\u0434\u0435\u0442 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          const minValue = Number(issue3.minimum);
          const unit = getRussianPlural(minValue, sizing.unit.one, sizing.unit.few, sizing.unit.many);
          return `\u0421\u043B\u0438\u0448\u043A\u043E\u043C \u043C\u0430\u043B\u0435\u043D\u044C\u043A\u043E\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C, \u0447\u0442\u043E ${issue3.origin} \u0431\u0443\u0434\u0435\u0442 \u0438\u043C\u0435\u0442\u044C ${adj}${issue3.minimum.toString()} ${unit}`;
        }
        return `\u0421\u043B\u0438\u0448\u043A\u043E\u043C \u043C\u0430\u043B\u0435\u043D\u044C\u043A\u043E\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435: \u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C, \u0447\u0442\u043E ${issue3.origin} \u0431\u0443\u0434\u0435\u0442 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u0430\u044F \u0441\u0442\u0440\u043E\u043A\u0430: \u0434\u043E\u043B\u0436\u043D\u0430 \u043D\u0430\u0447\u0438\u043D\u0430\u0442\u044C\u0441\u044F \u0441 "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u0430\u044F \u0441\u0442\u0440\u043E\u043A\u0430: \u0434\u043E\u043B\u0436\u043D\u0430 \u0437\u0430\u043A\u0430\u043D\u0447\u0438\u0432\u0430\u0442\u044C\u0441\u044F \u043D\u0430 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u0430\u044F \u0441\u0442\u0440\u043E\u043A\u0430: \u0434\u043E\u043B\u0436\u043D\u0430 \u0441\u043E\u0434\u0435\u0440\u0436\u0430\u0442\u044C "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u041D\u0435\u0432\u0435\u0440\u043D\u0430\u044F \u0441\u0442\u0440\u043E\u043A\u0430: \u0434\u043E\u043B\u0436\u043D\u0430 \u0441\u043E\u043E\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u043E\u0432\u0430\u0442\u044C \u0448\u0430\u0431\u043B\u043E\u043D\u0443 ${_issue.pattern}`;
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u043E\u0435 \u0447\u0438\u0441\u043B\u043E: \u0434\u043E\u043B\u0436\u043D\u043E \u0431\u044B\u0442\u044C \u043A\u0440\u0430\u0442\u043D\u044B\u043C ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u041D\u0435\u0440\u0430\u0441\u043F\u043E\u0437\u043D\u0430\u043D\u043D${issue3.keys.length > 1 ? "\u044B\u0435" : "\u044B\u0439"} \u043A\u043B\u044E\u0447${issue3.keys.length > 1 ? "\u0438" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0439 \u043A\u043B\u044E\u0447 \u0432 ${issue3.origin}`;
      case "invalid_union":
        return "\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0435 \u0432\u0445\u043E\u0434\u043D\u044B\u0435 \u0434\u0430\u043D\u043D\u044B\u0435";
      case "invalid_element":
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u043E\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435 \u0432 ${issue3.origin}`;
      default:
        return `\u041D\u0435\u0432\u0435\u0440\u043D\u044B\u0435 \u0432\u0445\u043E\u0434\u043D\u044B\u0435 \u0434\u0430\u043D\u043D\u044B\u0435`;
    }
  };
};
function ru_default() {
  return {
    localeError: error38()
  };
}

// node_modules/zod/v4/locales/sl.js
var error39 = () => {
  const Sizable = {
    string: { unit: "znakov", verb: "imeti" },
    file: { unit: "bajtov", verb: "imeti" },
    array: { unit: "elementov", verb: "imeti" },
    set: { unit: "elementov", verb: "imeti" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "vnos",
    email: "e-po\u0161tni naslov",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO datum in \u010Das",
    date: "ISO datum",
    time: "ISO \u010Das",
    duration: "ISO trajanje",
    ipv4: "IPv4 naslov",
    ipv6: "IPv6 naslov",
    cidrv4: "obseg IPv4",
    cidrv6: "obseg IPv6",
    base64: "base64 kodiran niz",
    base64url: "base64url kodiran niz",
    json_string: "JSON niz",
    e164: "E.164 \u0161tevilka",
    jwt: "JWT",
    template_literal: "vnos"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0161tevilo",
    array: "tabela"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Neveljaven vnos: pri\u010Dakovano instanceof ${issue3.expected}, prejeto ${received}`;
        }
        return `Neveljaven vnos: pri\u010Dakovano ${expected}, prejeto ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Neveljaven vnos: pri\u010Dakovano ${stringifyPrimitive(issue3.values[0])}`;
        return `Neveljavna mo\u017Enost: pri\u010Dakovano eno izmed ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Preveliko: pri\u010Dakovano, da bo ${issue3.origin ?? "vrednost"} imelo ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "elementov"}`;
        return `Preveliko: pri\u010Dakovano, da bo ${issue3.origin ?? "vrednost"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Premajhno: pri\u010Dakovano, da bo ${issue3.origin} imelo ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Premajhno: pri\u010Dakovano, da bo ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Neveljaven niz: mora se za\u010Deti z "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Neveljaven niz: mora se kon\u010Dati z "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Neveljaven niz: mora vsebovati "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Neveljaven niz: mora ustrezati vzorcu ${_issue.pattern}`;
        return `Neveljaven ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Neveljavno \u0161tevilo: mora biti ve\u010Dkratnik ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Neprepoznan${issue3.keys.length > 1 ? "i klju\u010Di" : " klju\u010D"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Neveljaven klju\u010D v ${issue3.origin}`;
      case "invalid_union":
        return "Neveljaven vnos";
      case "invalid_element":
        return `Neveljavna vrednost v ${issue3.origin}`;
      default:
        return "Neveljaven vnos";
    }
  };
};
function sl_default() {
  return {
    localeError: error39()
  };
}

// node_modules/zod/v4/locales/sv.js
var error40 = () => {
  const Sizable = {
    string: { unit: "tecken", verb: "att ha" },
    file: { unit: "bytes", verb: "att ha" },
    array: { unit: "objekt", verb: "att inneh\xE5lla" },
    set: { unit: "objekt", verb: "att inneh\xE5lla" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "regulj\xE4rt uttryck",
    email: "e-postadress",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO-datum och tid",
    date: "ISO-datum",
    time: "ISO-tid",
    duration: "ISO-varaktighet",
    ipv4: "IPv4-intervall",
    ipv6: "IPv6-intervall",
    cidrv4: "IPv4-spektrum",
    cidrv6: "IPv6-spektrum",
    base64: "base64-kodad str\xE4ng",
    base64url: "base64url-kodad str\xE4ng",
    json_string: "JSON-str\xE4ng",
    e164: "E.164-nummer",
    jwt: "JWT",
    template_literal: "mall-literal"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "antal",
    array: "lista"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ogiltig inmatning: f\xF6rv\xE4ntat instanceof ${issue3.expected}, fick ${received}`;
        }
        return `Ogiltig inmatning: f\xF6rv\xE4ntat ${expected}, fick ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ogiltig inmatning: f\xF6rv\xE4ntat ${stringifyPrimitive(issue3.values[0])}`;
        return `Ogiltigt val: f\xF6rv\xE4ntade en av ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `F\xF6r stor(t): f\xF6rv\xE4ntade ${issue3.origin ?? "v\xE4rdet"} att ha ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "element"}`;
        }
        return `F\xF6r stor(t): f\xF6rv\xE4ntat ${issue3.origin ?? "v\xE4rdet"} att ha ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `F\xF6r lite(t): f\xF6rv\xE4ntade ${issue3.origin ?? "v\xE4rdet"} att ha ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `F\xF6r lite(t): f\xF6rv\xE4ntade ${issue3.origin ?? "v\xE4rdet"} att ha ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `Ogiltig str\xE4ng: m\xE5ste b\xF6rja med "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `Ogiltig str\xE4ng: m\xE5ste sluta med "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Ogiltig str\xE4ng: m\xE5ste inneh\xE5lla "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Ogiltig str\xE4ng: m\xE5ste matcha m\xF6nstret "${_issue.pattern}"`;
        return `Ogiltig(t) ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ogiltigt tal: m\xE5ste vara en multipel av ${issue3.divisor}`;
      case "unrecognized_keys":
        return `${issue3.keys.length > 1 ? "Ok\xE4nda nycklar" : "Ok\xE4nd nyckel"}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Ogiltig nyckel i ${issue3.origin ?? "v\xE4rdet"}`;
      case "invalid_union":
        return "Ogiltig input";
      case "invalid_element":
        return `Ogiltigt v\xE4rde i ${issue3.origin ?? "v\xE4rdet"}`;
      default:
        return `Ogiltig input`;
    }
  };
};
function sv_default() {
  return {
    localeError: error40()
  };
}

// node_modules/zod/v4/locales/ta.js
var error41 = () => {
  const Sizable = {
    string: { unit: "\u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BCD\u0B95\u0BB3\u0BCD", verb: "\u0B95\u0BCA\u0BA3\u0BCD\u0B9F\u0BBF\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD" },
    file: { unit: "\u0BAA\u0BC8\u0B9F\u0BCD\u0B9F\u0BC1\u0B95\u0BB3\u0BCD", verb: "\u0B95\u0BCA\u0BA3\u0BCD\u0B9F\u0BBF\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD" },
    array: { unit: "\u0B89\u0BB1\u0BC1\u0BAA\u0BCD\u0BAA\u0BC1\u0B95\u0BB3\u0BCD", verb: "\u0B95\u0BCA\u0BA3\u0BCD\u0B9F\u0BBF\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD" },
    set: { unit: "\u0B89\u0BB1\u0BC1\u0BAA\u0BCD\u0BAA\u0BC1\u0B95\u0BB3\u0BCD", verb: "\u0B95\u0BCA\u0BA3\u0BCD\u0B9F\u0BBF\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1",
    email: "\u0BAE\u0BBF\u0BA9\u0BCD\u0BA9\u0B9E\u0BCD\u0B9A\u0BB2\u0BCD \u0BAE\u0BC1\u0B95\u0BB5\u0BB0\u0BBF",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u0BA4\u0BC7\u0BA4\u0BBF \u0BA8\u0BC7\u0BB0\u0BAE\u0BCD",
    date: "ISO \u0BA4\u0BC7\u0BA4\u0BBF",
    time: "ISO \u0BA8\u0BC7\u0BB0\u0BAE\u0BCD",
    duration: "ISO \u0B95\u0BBE\u0BB2 \u0B85\u0BB3\u0BB5\u0BC1",
    ipv4: "IPv4 \u0BAE\u0BC1\u0B95\u0BB5\u0BB0\u0BBF",
    ipv6: "IPv6 \u0BAE\u0BC1\u0B95\u0BB5\u0BB0\u0BBF",
    cidrv4: "IPv4 \u0BB5\u0BB0\u0BAE\u0BCD\u0BAA\u0BC1",
    cidrv6: "IPv6 \u0BB5\u0BB0\u0BAE\u0BCD\u0BAA\u0BC1",
    base64: "base64-encoded \u0B9A\u0BB0\u0BAE\u0BCD",
    base64url: "base64url-encoded \u0B9A\u0BB0\u0BAE\u0BCD",
    json_string: "JSON \u0B9A\u0BB0\u0BAE\u0BCD",
    e164: "E.164 \u0B8E\u0BA3\u0BCD",
    jwt: "JWT",
    template_literal: "input"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0B8E\u0BA3\u0BCD",
    array: "\u0B85\u0BA3\u0BBF",
    null: "\u0BB5\u0BC6\u0BB1\u0BC1\u0BAE\u0BC8"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 instanceof ${issue3.expected}, \u0BAA\u0BC6\u0BB1\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${received}`;
        }
        return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${expected}, \u0BAA\u0BC6\u0BB1\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${stringifyPrimitive(issue3.values[0])}`;
        return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0BB5\u0BBF\u0BB0\u0BC1\u0BAA\u0BCD\u0BAA\u0BAE\u0BCD: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${joinValues(issue3.values, "|")} \u0B87\u0BB2\u0BCD \u0B92\u0BA9\u0BCD\u0BB1\u0BC1`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0BAE\u0BBF\u0B95 \u0BAA\u0BC6\u0BB0\u0BBF\u0BAF\u0BA4\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${issue3.origin ?? "\u0BAE\u0BA4\u0BBF\u0BAA\u0BCD\u0BAA\u0BC1"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0B89\u0BB1\u0BC1\u0BAA\u0BCD\u0BAA\u0BC1\u0B95\u0BB3\u0BCD"} \u0B86\u0B95 \u0B87\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        }
        return `\u0BAE\u0BBF\u0B95 \u0BAA\u0BC6\u0BB0\u0BBF\u0BAF\u0BA4\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${issue3.origin ?? "\u0BAE\u0BA4\u0BBF\u0BAA\u0BCD\u0BAA\u0BC1"} ${adj}${issue3.maximum.toString()} \u0B86\u0B95 \u0B87\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0BAE\u0BBF\u0B95\u0B9A\u0BCD \u0B9A\u0BBF\u0BB1\u0BBF\u0BAF\u0BA4\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit} \u0B86\u0B95 \u0B87\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        }
        return `\u0BAE\u0BBF\u0B95\u0B9A\u0BCD \u0B9A\u0BBF\u0BB1\u0BBF\u0BAF\u0BA4\u0BC1: \u0B8E\u0BA4\u0BBF\u0BB0\u0BCD\u0BAA\u0BBE\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1 ${issue3.origin} ${adj}${issue3.minimum.toString()} \u0B86\u0B95 \u0B87\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B9A\u0BB0\u0BAE\u0BCD: "${_issue.prefix}" \u0B87\u0BB2\u0BCD \u0BA4\u0BCA\u0B9F\u0B99\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        if (_issue.format === "ends_with")
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B9A\u0BB0\u0BAE\u0BCD: "${_issue.suffix}" \u0B87\u0BB2\u0BCD \u0BAE\u0BC1\u0B9F\u0BBF\u0BB5\u0B9F\u0BC8\u0BAF \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        if (_issue.format === "includes")
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B9A\u0BB0\u0BAE\u0BCD: "${_issue.includes}" \u0B90 \u0B89\u0BB3\u0BCD\u0BB3\u0B9F\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        if (_issue.format === "regex")
          return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B9A\u0BB0\u0BAE\u0BCD: ${_issue.pattern} \u0BAE\u0BC1\u0BB1\u0BC8\u0BAA\u0BBE\u0B9F\u0BCD\u0B9F\u0BC1\u0B9F\u0BA9\u0BCD \u0BAA\u0BCA\u0BB0\u0BC1\u0BA8\u0BCD\u0BA4 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
        return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B8E\u0BA3\u0BCD: ${issue3.divisor} \u0B87\u0BA9\u0BCD \u0BAA\u0BB2\u0BAE\u0BBE\u0B95 \u0B87\u0BB0\u0BC1\u0B95\u0BCD\u0B95 \u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BC1\u0BAE\u0BCD`;
      case "unrecognized_keys":
        return `\u0B85\u0B9F\u0BC8\u0BAF\u0BBE\u0BB3\u0BAE\u0BCD \u0BA4\u0BC6\u0BB0\u0BBF\u0BAF\u0BBE\u0BA4 \u0BB5\u0BBF\u0B9A\u0BC8${issue3.keys.length > 1 ? "\u0B95\u0BB3\u0BCD" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} \u0B87\u0BB2\u0BCD \u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0BB5\u0BBF\u0B9A\u0BC8`;
      case "invalid_union":
        return "\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1";
      case "invalid_element":
        return `${issue3.origin} \u0B87\u0BB2\u0BCD \u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0BAE\u0BA4\u0BBF\u0BAA\u0BCD\u0BAA\u0BC1`;
      default:
        return `\u0BA4\u0BB5\u0BB1\u0BBE\u0BA9 \u0B89\u0BB3\u0BCD\u0BB3\u0BC0\u0B9F\u0BC1`;
    }
  };
};
function ta_default() {
  return {
    localeError: error41()
  };
}

// node_modules/zod/v4/locales/th.js
var error42 = () => {
  const Sizable = {
    string: { unit: "\u0E15\u0E31\u0E27\u0E2D\u0E31\u0E01\u0E29\u0E23", verb: "\u0E04\u0E27\u0E23\u0E21\u0E35" },
    file: { unit: "\u0E44\u0E1A\u0E15\u0E4C", verb: "\u0E04\u0E27\u0E23\u0E21\u0E35" },
    array: { unit: "\u0E23\u0E32\u0E22\u0E01\u0E32\u0E23", verb: "\u0E04\u0E27\u0E23\u0E21\u0E35" },
    set: { unit: "\u0E23\u0E32\u0E22\u0E01\u0E32\u0E23", verb: "\u0E04\u0E27\u0E23\u0E21\u0E35" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E17\u0E35\u0E48\u0E1B\u0E49\u0E2D\u0E19",
    email: "\u0E17\u0E35\u0E48\u0E2D\u0E22\u0E39\u0E48\u0E2D\u0E35\u0E40\u0E21\u0E25",
    url: "URL",
    emoji: "\u0E2D\u0E34\u0E42\u0E21\u0E08\u0E34",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u0E27\u0E31\u0E19\u0E17\u0E35\u0E48\u0E40\u0E27\u0E25\u0E32\u0E41\u0E1A\u0E1A ISO",
    date: "\u0E27\u0E31\u0E19\u0E17\u0E35\u0E48\u0E41\u0E1A\u0E1A ISO",
    time: "\u0E40\u0E27\u0E25\u0E32\u0E41\u0E1A\u0E1A ISO",
    duration: "\u0E0A\u0E48\u0E27\u0E07\u0E40\u0E27\u0E25\u0E32\u0E41\u0E1A\u0E1A ISO",
    ipv4: "\u0E17\u0E35\u0E48\u0E2D\u0E22\u0E39\u0E48 IPv4",
    ipv6: "\u0E17\u0E35\u0E48\u0E2D\u0E22\u0E39\u0E48 IPv6",
    cidrv4: "\u0E0A\u0E48\u0E27\u0E07 IP \u0E41\u0E1A\u0E1A IPv4",
    cidrv6: "\u0E0A\u0E48\u0E27\u0E07 IP \u0E41\u0E1A\u0E1A IPv6",
    base64: "\u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E41\u0E1A\u0E1A Base64",
    base64url: "\u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E41\u0E1A\u0E1A Base64 \u0E2A\u0E33\u0E2B\u0E23\u0E31\u0E1A URL",
    json_string: "\u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E41\u0E1A\u0E1A JSON",
    e164: "\u0E40\u0E1A\u0E2D\u0E23\u0E4C\u0E42\u0E17\u0E23\u0E28\u0E31\u0E1E\u0E17\u0E4C\u0E23\u0E30\u0E2B\u0E27\u0E48\u0E32\u0E07\u0E1B\u0E23\u0E30\u0E40\u0E17\u0E28 (E.164)",
    jwt: "\u0E42\u0E17\u0E40\u0E04\u0E19 JWT",
    template_literal: "\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E17\u0E35\u0E48\u0E1B\u0E49\u0E2D\u0E19"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0E15\u0E31\u0E27\u0E40\u0E25\u0E02",
    array: "\u0E2D\u0E32\u0E23\u0E4C\u0E40\u0E23\u0E22\u0E4C (Array)",
    null: "\u0E44\u0E21\u0E48\u0E21\u0E35\u0E04\u0E48\u0E32 (null)"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0E1B\u0E23\u0E30\u0E40\u0E20\u0E17\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E04\u0E27\u0E23\u0E40\u0E1B\u0E47\u0E19 instanceof ${issue3.expected} \u0E41\u0E15\u0E48\u0E44\u0E14\u0E49\u0E23\u0E31\u0E1A ${received}`;
        }
        return `\u0E1B\u0E23\u0E30\u0E40\u0E20\u0E17\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E04\u0E27\u0E23\u0E40\u0E1B\u0E47\u0E19 ${expected} \u0E41\u0E15\u0E48\u0E44\u0E14\u0E49\u0E23\u0E31\u0E1A ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u0E04\u0E48\u0E32\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E04\u0E27\u0E23\u0E40\u0E1B\u0E47\u0E19 ${stringifyPrimitive(issue3.values[0])}`;
        return `\u0E15\u0E31\u0E27\u0E40\u0E25\u0E37\u0E2D\u0E01\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E04\u0E27\u0E23\u0E40\u0E1B\u0E47\u0E19\u0E2B\u0E19\u0E36\u0E48\u0E07\u0E43\u0E19 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "\u0E44\u0E21\u0E48\u0E40\u0E01\u0E34\u0E19" : "\u0E19\u0E49\u0E2D\u0E22\u0E01\u0E27\u0E48\u0E32";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u0E40\u0E01\u0E34\u0E19\u0E01\u0E33\u0E2B\u0E19\u0E14: ${issue3.origin ?? "\u0E04\u0E48\u0E32"} \u0E04\u0E27\u0E23\u0E21\u0E35${adj} ${issue3.maximum.toString()} ${sizing.unit ?? "\u0E23\u0E32\u0E22\u0E01\u0E32\u0E23"}`;
        return `\u0E40\u0E01\u0E34\u0E19\u0E01\u0E33\u0E2B\u0E19\u0E14: ${issue3.origin ?? "\u0E04\u0E48\u0E32"} \u0E04\u0E27\u0E23\u0E21\u0E35${adj} ${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? "\u0E2D\u0E22\u0E48\u0E32\u0E07\u0E19\u0E49\u0E2D\u0E22" : "\u0E21\u0E32\u0E01\u0E01\u0E27\u0E48\u0E32";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0E19\u0E49\u0E2D\u0E22\u0E01\u0E27\u0E48\u0E32\u0E01\u0E33\u0E2B\u0E19\u0E14: ${issue3.origin} \u0E04\u0E27\u0E23\u0E21\u0E35${adj} ${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u0E19\u0E49\u0E2D\u0E22\u0E01\u0E27\u0E48\u0E32\u0E01\u0E33\u0E2B\u0E19\u0E14: ${issue3.origin} \u0E04\u0E27\u0E23\u0E21\u0E35${adj} ${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E15\u0E49\u0E2D\u0E07\u0E02\u0E36\u0E49\u0E19\u0E15\u0E49\u0E19\u0E14\u0E49\u0E27\u0E22 "${_issue.prefix}"`;
        }
        if (_issue.format === "ends_with")
          return `\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E15\u0E49\u0E2D\u0E07\u0E25\u0E07\u0E17\u0E49\u0E32\u0E22\u0E14\u0E49\u0E27\u0E22 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21\u0E15\u0E49\u0E2D\u0E07\u0E21\u0E35 "${_issue.includes}" \u0E2D\u0E22\u0E39\u0E48\u0E43\u0E19\u0E02\u0E49\u0E2D\u0E04\u0E27\u0E32\u0E21`;
        if (_issue.format === "regex")
          return `\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E15\u0E49\u0E2D\u0E07\u0E15\u0E23\u0E07\u0E01\u0E31\u0E1A\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E17\u0E35\u0E48\u0E01\u0E33\u0E2B\u0E19\u0E14 ${_issue.pattern}`;
        return `\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u0E15\u0E31\u0E27\u0E40\u0E25\u0E02\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E15\u0E49\u0E2D\u0E07\u0E40\u0E1B\u0E47\u0E19\u0E08\u0E33\u0E19\u0E27\u0E19\u0E17\u0E35\u0E48\u0E2B\u0E32\u0E23\u0E14\u0E49\u0E27\u0E22 ${issue3.divisor} \u0E44\u0E14\u0E49\u0E25\u0E07\u0E15\u0E31\u0E27`;
      case "unrecognized_keys":
        return `\u0E1E\u0E1A\u0E04\u0E35\u0E22\u0E4C\u0E17\u0E35\u0E48\u0E44\u0E21\u0E48\u0E23\u0E39\u0E49\u0E08\u0E31\u0E01: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u0E04\u0E35\u0E22\u0E4C\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07\u0E43\u0E19 ${issue3.origin}`;
      case "invalid_union":
        return "\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07: \u0E44\u0E21\u0E48\u0E15\u0E23\u0E07\u0E01\u0E31\u0E1A\u0E23\u0E39\u0E1B\u0E41\u0E1A\u0E1A\u0E22\u0E39\u0E40\u0E19\u0E35\u0E22\u0E19\u0E17\u0E35\u0E48\u0E01\u0E33\u0E2B\u0E19\u0E14\u0E44\u0E27\u0E49";
      case "invalid_element":
        return `\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07\u0E43\u0E19 ${issue3.origin}`;
      default:
        return `\u0E02\u0E49\u0E2D\u0E21\u0E39\u0E25\u0E44\u0E21\u0E48\u0E16\u0E39\u0E01\u0E15\u0E49\u0E2D\u0E07`;
    }
  };
};
function th_default() {
  return {
    localeError: error42()
  };
}

// node_modules/zod/v4/locales/tr.js
var error43 = () => {
  const Sizable = {
    string: { unit: "karakter", verb: "olmal\u0131" },
    file: { unit: "bayt", verb: "olmal\u0131" },
    array: { unit: "\xF6\u011Fe", verb: "olmal\u0131" },
    set: { unit: "\xF6\u011Fe", verb: "olmal\u0131" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "girdi",
    email: "e-posta adresi",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO tarih ve saat",
    date: "ISO tarih",
    time: "ISO saat",
    duration: "ISO s\xFCre",
    ipv4: "IPv4 adresi",
    ipv6: "IPv6 adresi",
    cidrv4: "IPv4 aral\u0131\u011F\u0131",
    cidrv6: "IPv6 aral\u0131\u011F\u0131",
    base64: "base64 ile \u015Fifrelenmi\u015F metin",
    base64url: "base64url ile \u015Fifrelenmi\u015F metin",
    json_string: "JSON dizesi",
    e164: "E.164 say\u0131s\u0131",
    jwt: "JWT",
    template_literal: "\u015Eablon dizesi"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Ge\xE7ersiz de\u011Fer: beklenen instanceof ${issue3.expected}, al\u0131nan ${received}`;
        }
        return `Ge\xE7ersiz de\u011Fer: beklenen ${expected}, al\u0131nan ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Ge\xE7ersiz de\u011Fer: beklenen ${stringifyPrimitive(issue3.values[0])}`;
        return `Ge\xE7ersiz se\xE7enek: a\u015Fa\u011F\u0131dakilerden biri olmal\u0131: ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\xC7ok b\xFCy\xFCk: beklenen ${issue3.origin ?? "de\u011Fer"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\xF6\u011Fe"}`;
        return `\xC7ok b\xFCy\xFCk: beklenen ${issue3.origin ?? "de\u011Fer"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\xC7ok k\xFC\xE7\xFCk: beklenen ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        return `\xC7ok k\xFC\xE7\xFCk: beklenen ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Ge\xE7ersiz metin: "${_issue.prefix}" ile ba\u015Flamal\u0131`;
        if (_issue.format === "ends_with")
          return `Ge\xE7ersiz metin: "${_issue.suffix}" ile bitmeli`;
        if (_issue.format === "includes")
          return `Ge\xE7ersiz metin: "${_issue.includes}" i\xE7ermeli`;
        if (_issue.format === "regex")
          return `Ge\xE7ersiz metin: ${_issue.pattern} desenine uymal\u0131`;
        return `Ge\xE7ersiz ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Ge\xE7ersiz say\u0131: ${issue3.divisor} ile tam b\xF6l\xFCnebilmeli`;
      case "unrecognized_keys":
        return `Tan\u0131nmayan anahtar${issue3.keys.length > 1 ? "lar" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} i\xE7inde ge\xE7ersiz anahtar`;
      case "invalid_union":
        return "Ge\xE7ersiz de\u011Fer";
      case "invalid_element":
        return `${issue3.origin} i\xE7inde ge\xE7ersiz de\u011Fer`;
      default:
        return `Ge\xE7ersiz de\u011Fer`;
    }
  };
};
function tr_default() {
  return {
    localeError: error43()
  };
}

// node_modules/zod/v4/locales/uk.js
var error44 = () => {
  const Sizable = {
    string: { unit: "\u0441\u0438\u043C\u0432\u043E\u043B\u0456\u0432", verb: "\u043C\u0430\u0442\u0438\u043C\u0435" },
    file: { unit: "\u0431\u0430\u0439\u0442\u0456\u0432", verb: "\u043C\u0430\u0442\u0438\u043C\u0435" },
    array: { unit: "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0456\u0432", verb: "\u043C\u0430\u0442\u0438\u043C\u0435" },
    set: { unit: "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0456\u0432", verb: "\u043C\u0430\u0442\u0438\u043C\u0435" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456",
    email: "\u0430\u0434\u0440\u0435\u0441\u0430 \u0435\u043B\u0435\u043A\u0442\u0440\u043E\u043D\u043D\u043E\u0457 \u043F\u043E\u0448\u0442\u0438",
    url: "URL",
    emoji: "\u0435\u043C\u043E\u0434\u0437\u0456",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\u0434\u0430\u0442\u0430 \u0442\u0430 \u0447\u0430\u0441 ISO",
    date: "\u0434\u0430\u0442\u0430 ISO",
    time: "\u0447\u0430\u0441 ISO",
    duration: "\u0442\u0440\u0438\u0432\u0430\u043B\u0456\u0441\u0442\u044C ISO",
    ipv4: "\u0430\u0434\u0440\u0435\u0441\u0430 IPv4",
    ipv6: "\u0430\u0434\u0440\u0435\u0441\u0430 IPv6",
    cidrv4: "\u0434\u0456\u0430\u043F\u0430\u0437\u043E\u043D IPv4",
    cidrv6: "\u0434\u0456\u0430\u043F\u0430\u0437\u043E\u043D IPv6",
    base64: "\u0440\u044F\u0434\u043E\u043A \u0443 \u043A\u043E\u0434\u0443\u0432\u0430\u043D\u043D\u0456 base64",
    base64url: "\u0440\u044F\u0434\u043E\u043A \u0443 \u043A\u043E\u0434\u0443\u0432\u0430\u043D\u043D\u0456 base64url",
    json_string: "\u0440\u044F\u0434\u043E\u043A JSON",
    e164: "\u043D\u043E\u043C\u0435\u0440 E.164",
    jwt: "JWT",
    template_literal: "\u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0447\u0438\u0441\u043B\u043E",
    array: "\u043C\u0430\u0441\u0438\u0432"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0456 \u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F instanceof ${issue3.expected}, \u043E\u0442\u0440\u0438\u043C\u0430\u043D\u043E ${received}`;
        }
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0456 \u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F ${expected}, \u043E\u0442\u0440\u0438\u043C\u0430\u043D\u043E ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0456 \u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F ${stringifyPrimitive(issue3.values[0])}`;
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0430 \u043E\u043F\u0446\u0456\u044F: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F \u043E\u0434\u043D\u0435 \u0437 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u0417\u0430\u043D\u0430\u0434\u0442\u043E \u0432\u0435\u043B\u0438\u043A\u0435: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F, \u0449\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u0435\u043D\u043D\u044F"} ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0435\u043B\u0435\u043C\u0435\u043D\u0442\u0456\u0432"}`;
        return `\u0417\u0430\u043D\u0430\u0434\u0442\u043E \u0432\u0435\u043B\u0438\u043A\u0435: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F, \u0449\u043E ${issue3.origin ?? "\u0437\u043D\u0430\u0447\u0435\u043D\u043D\u044F"} \u0431\u0443\u0434\u0435 ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0417\u0430\u043D\u0430\u0434\u0442\u043E \u043C\u0430\u043B\u0435: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F, \u0449\u043E ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u0417\u0430\u043D\u0430\u0434\u0442\u043E \u043C\u0430\u043B\u0435: \u043E\u0447\u0456\u043A\u0443\u0454\u0442\u044C\u0441\u044F, \u0449\u043E ${issue3.origin} \u0431\u0443\u0434\u0435 ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 \u0440\u044F\u0434\u043E\u043A: \u043F\u043E\u0432\u0438\u043D\u0435\u043D \u043F\u043E\u0447\u0438\u043D\u0430\u0442\u0438\u0441\u044F \u0437 "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 \u0440\u044F\u0434\u043E\u043A: \u043F\u043E\u0432\u0438\u043D\u0435\u043D \u0437\u0430\u043A\u0456\u043D\u0447\u0443\u0432\u0430\u0442\u0438\u0441\u044F \u043D\u0430 "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 \u0440\u044F\u0434\u043E\u043A: \u043F\u043E\u0432\u0438\u043D\u0435\u043D \u043C\u0456\u0441\u0442\u0438\u0442\u0438 "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 \u0440\u044F\u0434\u043E\u043A: \u043F\u043E\u0432\u0438\u043D\u0435\u043D \u0432\u0456\u0434\u043F\u043E\u0432\u0456\u0434\u0430\u0442\u0438 \u0448\u0430\u0431\u043B\u043E\u043D\u0443 ${_issue.pattern}`;
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0435 \u0447\u0438\u0441\u043B\u043E: \u043F\u043E\u0432\u0438\u043D\u043D\u043E \u0431\u0443\u0442\u0438 \u043A\u0440\u0430\u0442\u043D\u0438\u043C ${issue3.divisor}`;
      case "unrecognized_keys":
        return `\u041D\u0435\u0440\u043E\u0437\u043F\u0456\u0437\u043D\u0430\u043D\u0438\u0439 \u043A\u043B\u044E\u0447${issue3.keys.length > 1 ? "\u0456" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0438\u0439 \u043A\u043B\u044E\u0447 \u0443 ${issue3.origin}`;
      case "invalid_union":
        return "\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0456 \u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456";
      case "invalid_element":
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u043D\u044F \u0443 ${issue3.origin}`;
      default:
        return `\u041D\u0435\u043F\u0440\u0430\u0432\u0438\u043B\u044C\u043D\u0456 \u0432\u0445\u0456\u0434\u043D\u0456 \u0434\u0430\u043D\u0456`;
    }
  };
};
function uk_default() {
  return {
    localeError: error44()
  };
}

// node_modules/zod/v4/locales/ua.js
function ua_default() {
  return uk_default();
}

// node_modules/zod/v4/locales/ur.js
var error45 = () => {
  const Sizable = {
    string: { unit: "\u062D\u0631\u0648\u0641", verb: "\u06C1\u0648\u0646\u0627" },
    file: { unit: "\u0628\u0627\u0626\u0679\u0633", verb: "\u06C1\u0648\u0646\u0627" },
    array: { unit: "\u0622\u0626\u0679\u0645\u0632", verb: "\u06C1\u0648\u0646\u0627" },
    set: { unit: "\u0622\u0626\u0679\u0645\u0632", verb: "\u06C1\u0648\u0646\u0627" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0627\u0646 \u067E\u0679",
    email: "\u0627\u06CC \u0645\u06CC\u0644 \u0627\u06CC\u0688\u0631\u06CC\u0633",
    url: "\u06CC\u0648 \u0622\u0631 \u0627\u06CC\u0644",
    emoji: "\u0627\u06CC\u0645\u0648\u062C\u06CC",
    uuid: "\u06CC\u0648 \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC",
    uuidv4: "\u06CC\u0648 \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC \u0648\u06CC 4",
    uuidv6: "\u06CC\u0648 \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC \u0648\u06CC 6",
    nanoid: "\u0646\u06CC\u0646\u0648 \u0622\u0626\u06CC \u0688\u06CC",
    guid: "\u062C\u06CC \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC",
    cuid: "\u0633\u06CC \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC",
    cuid2: "\u0633\u06CC \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC 2",
    ulid: "\u06CC\u0648 \u0627\u06CC\u0644 \u0622\u0626\u06CC \u0688\u06CC",
    xid: "\u0627\u06CC\u06A9\u0633 \u0622\u0626\u06CC \u0688\u06CC",
    ksuid: "\u06A9\u06D2 \u0627\u06CC\u0633 \u06CC\u0648 \u0622\u0626\u06CC \u0688\u06CC",
    datetime: "\u0622\u0626\u06CC \u0627\u06CC\u0633 \u0627\u0648 \u0688\u06CC\u0679 \u0679\u0627\u0626\u0645",
    date: "\u0622\u0626\u06CC \u0627\u06CC\u0633 \u0627\u0648 \u062A\u0627\u0631\u06CC\u062E",
    time: "\u0622\u0626\u06CC \u0627\u06CC\u0633 \u0627\u0648 \u0648\u0642\u062A",
    duration: "\u0622\u0626\u06CC \u0627\u06CC\u0633 \u0627\u0648 \u0645\u062F\u062A",
    ipv4: "\u0622\u0626\u06CC \u067E\u06CC \u0648\u06CC 4 \u0627\u06CC\u0688\u0631\u06CC\u0633",
    ipv6: "\u0622\u0626\u06CC \u067E\u06CC \u0648\u06CC 6 \u0627\u06CC\u0688\u0631\u06CC\u0633",
    cidrv4: "\u0622\u0626\u06CC \u067E\u06CC \u0648\u06CC 4 \u0631\u06CC\u0646\u062C",
    cidrv6: "\u0622\u0626\u06CC \u067E\u06CC \u0648\u06CC 6 \u0631\u06CC\u0646\u062C",
    base64: "\u0628\u06CC\u0633 64 \u0627\u0646 \u06A9\u0648\u0688\u0688 \u0633\u0679\u0631\u0646\u06AF",
    base64url: "\u0628\u06CC\u0633 64 \u06CC\u0648 \u0622\u0631 \u0627\u06CC\u0644 \u0627\u0646 \u06A9\u0648\u0688\u0688 \u0633\u0679\u0631\u0646\u06AF",
    json_string: "\u062C\u06D2 \u0627\u06CC\u0633 \u0627\u0648 \u0627\u06CC\u0646 \u0633\u0679\u0631\u0646\u06AF",
    e164: "\u0627\u06CC 164 \u0646\u0645\u0628\u0631",
    jwt: "\u062C\u06D2 \u0688\u0628\u0644\u06CC\u0648 \u0679\u06CC",
    template_literal: "\u0627\u0646 \u067E\u0679"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u0646\u0645\u0628\u0631",
    array: "\u0622\u0631\u06D2",
    null: "\u0646\u0644"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u063A\u0644\u0637 \u0627\u0646 \u067E\u0679: instanceof ${issue3.expected} \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627\u060C ${received} \u0645\u0648\u0635\u0648\u0644 \u06C1\u0648\u0627`;
        }
        return `\u063A\u0644\u0637 \u0627\u0646 \u067E\u0679: ${expected} \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627\u060C ${received} \u0645\u0648\u0635\u0648\u0644 \u06C1\u0648\u0627`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u063A\u0644\u0637 \u0627\u0646 \u067E\u0679: ${stringifyPrimitive(issue3.values[0])} \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627`;
        return `\u063A\u0644\u0637 \u0622\u067E\u0634\u0646: ${joinValues(issue3.values, "|")} \u0645\u06CC\u06BA \u0633\u06D2 \u0627\u06CC\u06A9 \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u0628\u06C1\u062A \u0628\u0691\u0627: ${issue3.origin ?? "\u0648\u06CC\u0644\u06CC\u0648"} \u06A9\u06D2 ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u0639\u0646\u0627\u0635\u0631"} \u06C1\u0648\u0646\u06D2 \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u06D2`;
        return `\u0628\u06C1\u062A \u0628\u0691\u0627: ${issue3.origin ?? "\u0648\u06CC\u0644\u06CC\u0648"} \u06A9\u0627 ${adj}${issue3.maximum.toString()} \u06C1\u0648\u0646\u0627 \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u0628\u06C1\u062A \u0686\u06BE\u0648\u0679\u0627: ${issue3.origin} \u06A9\u06D2 ${adj}${issue3.minimum.toString()} ${sizing.unit} \u06C1\u0648\u0646\u06D2 \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u06D2`;
        }
        return `\u0628\u06C1\u062A \u0686\u06BE\u0648\u0679\u0627: ${issue3.origin} \u06A9\u0627 ${adj}${issue3.minimum.toString()} \u06C1\u0648\u0646\u0627 \u0645\u062A\u0648\u0642\u0639 \u062A\u06BE\u0627`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u063A\u0644\u0637 \u0633\u0679\u0631\u0646\u06AF: "${_issue.prefix}" \u0633\u06D2 \u0634\u0631\u0648\u0639 \u06C1\u0648\u0646\u0627 \u0686\u0627\u06C1\u06CC\u06D2`;
        }
        if (_issue.format === "ends_with")
          return `\u063A\u0644\u0637 \u0633\u0679\u0631\u0646\u06AF: "${_issue.suffix}" \u067E\u0631 \u062E\u062A\u0645 \u06C1\u0648\u0646\u0627 \u0686\u0627\u06C1\u06CC\u06D2`;
        if (_issue.format === "includes")
          return `\u063A\u0644\u0637 \u0633\u0679\u0631\u0646\u06AF: "${_issue.includes}" \u0634\u0627\u0645\u0644 \u06C1\u0648\u0646\u0627 \u0686\u0627\u06C1\u06CC\u06D2`;
        if (_issue.format === "regex")
          return `\u063A\u0644\u0637 \u0633\u0679\u0631\u0646\u06AF: \u067E\u06CC\u0679\u0631\u0646 ${_issue.pattern} \u0633\u06D2 \u0645\u06CC\u0686 \u06C1\u0648\u0646\u0627 \u0686\u0627\u06C1\u06CC\u06D2`;
        return `\u063A\u0644\u0637 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u063A\u0644\u0637 \u0646\u0645\u0628\u0631: ${issue3.divisor} \u06A9\u0627 \u0645\u0636\u0627\u0639\u0641 \u06C1\u0648\u0646\u0627 \u0686\u0627\u06C1\u06CC\u06D2`;
      case "unrecognized_keys":
        return `\u063A\u06CC\u0631 \u062A\u0633\u0644\u06CC\u0645 \u0634\u062F\u06C1 \u06A9\u06CC${issue3.keys.length > 1 ? "\u0632" : ""}: ${joinValues(issue3.keys, "\u060C ")}`;
      case "invalid_key":
        return `${issue3.origin} \u0645\u06CC\u06BA \u063A\u0644\u0637 \u06A9\u06CC`;
      case "invalid_union":
        return "\u063A\u0644\u0637 \u0627\u0646 \u067E\u0679";
      case "invalid_element":
        return `${issue3.origin} \u0645\u06CC\u06BA \u063A\u0644\u0637 \u0648\u06CC\u0644\u06CC\u0648`;
      default:
        return `\u063A\u0644\u0637 \u0627\u0646 \u067E\u0679`;
    }
  };
};
function ur_default() {
  return {
    localeError: error45()
  };
}

// node_modules/zod/v4/locales/uz.js
var error46 = () => {
  const Sizable = {
    string: { unit: "belgi", verb: "bo\u2018lishi kerak" },
    file: { unit: "bayt", verb: "bo\u2018lishi kerak" },
    array: { unit: "element", verb: "bo\u2018lishi kerak" },
    set: { unit: "element", verb: "bo\u2018lishi kerak" },
    map: { unit: "yozuv", verb: "bo\u2018lishi kerak" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "kirish",
    email: "elektron pochta manzili",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO sana va vaqti",
    date: "ISO sana",
    time: "ISO vaqt",
    duration: "ISO davomiylik",
    ipv4: "IPv4 manzil",
    ipv6: "IPv6 manzil",
    mac: "MAC manzil",
    cidrv4: "IPv4 diapazon",
    cidrv6: "IPv6 diapazon",
    base64: "base64 kodlangan satr",
    base64url: "base64url kodlangan satr",
    json_string: "JSON satr",
    e164: "E.164 raqam",
    jwt: "JWT",
    template_literal: "kirish"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "raqam",
    array: "massiv"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `Noto\u2018g\u2018ri kirish: kutilgan instanceof ${issue3.expected}, qabul qilingan ${received}`;
        }
        return `Noto\u2018g\u2018ri kirish: kutilgan ${expected}, qabul qilingan ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `Noto\u2018g\u2018ri kirish: kutilgan ${stringifyPrimitive(issue3.values[0])}`;
        return `Noto\u2018g\u2018ri variant: quyidagilardan biri kutilgan ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Juda katta: kutilgan ${issue3.origin ?? "qiymat"} ${adj}${issue3.maximum.toString()} ${sizing.unit} ${sizing.verb}`;
        return `Juda katta: kutilgan ${issue3.origin ?? "qiymat"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Juda kichik: kutilgan ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit} ${sizing.verb}`;
        }
        return `Juda kichik: kutilgan ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Noto\u2018g\u2018ri satr: "${_issue.prefix}" bilan boshlanishi kerak`;
        if (_issue.format === "ends_with")
          return `Noto\u2018g\u2018ri satr: "${_issue.suffix}" bilan tugashi kerak`;
        if (_issue.format === "includes")
          return `Noto\u2018g\u2018ri satr: "${_issue.includes}" ni o\u2018z ichiga olishi kerak`;
        if (_issue.format === "regex")
          return `Noto\u2018g\u2018ri satr: ${_issue.pattern} shabloniga mos kelishi kerak`;
        return `Noto\u2018g\u2018ri ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `Noto\u2018g\u2018ri raqam: ${issue3.divisor} ning karralisi bo\u2018lishi kerak`;
      case "unrecognized_keys":
        return `Noma\u2019lum kalit${issue3.keys.length > 1 ? "lar" : ""}: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} dagi kalit noto\u2018g\u2018ri`;
      case "invalid_union":
        return "Noto\u2018g\u2018ri kirish";
      case "invalid_element":
        return `${issue3.origin} da noto\u2018g\u2018ri qiymat`;
      default:
        return `Noto\u2018g\u2018ri kirish`;
    }
  };
};
function uz_default() {
  return {
    localeError: error46()
  };
}

// node_modules/zod/v4/locales/vi.js
var error47 = () => {
  const Sizable = {
    string: { unit: "k\xFD t\u1EF1", verb: "c\xF3" },
    file: { unit: "byte", verb: "c\xF3" },
    array: { unit: "ph\u1EA7n t\u1EED", verb: "c\xF3" },
    set: { unit: "ph\u1EA7n t\u1EED", verb: "c\xF3" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u0111\u1EA7u v\xE0o",
    email: "\u0111\u1ECBa ch\u1EC9 email",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ng\xE0y gi\u1EDD ISO",
    date: "ng\xE0y ISO",
    time: "gi\u1EDD ISO",
    duration: "kho\u1EA3ng th\u1EDDi gian ISO",
    ipv4: "\u0111\u1ECBa ch\u1EC9 IPv4",
    ipv6: "\u0111\u1ECBa ch\u1EC9 IPv6",
    cidrv4: "d\u1EA3i IPv4",
    cidrv6: "d\u1EA3i IPv6",
    base64: "chu\u1ED7i m\xE3 h\xF3a base64",
    base64url: "chu\u1ED7i m\xE3 h\xF3a base64url",
    json_string: "chu\u1ED7i JSON",
    e164: "s\u1ED1 E.164",
    jwt: "JWT",
    template_literal: "\u0111\u1EA7u v\xE0o"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "s\u1ED1",
    array: "m\u1EA3ng"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u0110\u1EA7u v\xE0o kh\xF4ng h\u1EE3p l\u1EC7: mong \u0111\u1EE3i instanceof ${issue3.expected}, nh\u1EADn \u0111\u01B0\u1EE3c ${received}`;
        }
        return `\u0110\u1EA7u v\xE0o kh\xF4ng h\u1EE3p l\u1EC7: mong \u0111\u1EE3i ${expected}, nh\u1EADn \u0111\u01B0\u1EE3c ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u0110\u1EA7u v\xE0o kh\xF4ng h\u1EE3p l\u1EC7: mong \u0111\u1EE3i ${stringifyPrimitive(issue3.values[0])}`;
        return `T\xF9y ch\u1ECDn kh\xF4ng h\u1EE3p l\u1EC7: mong \u0111\u1EE3i m\u1ED9t trong c\xE1c gi\xE1 tr\u1ECB ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `Qu\xE1 l\u1EDBn: mong \u0111\u1EE3i ${issue3.origin ?? "gi\xE1 tr\u1ECB"} ${sizing.verb} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "ph\u1EA7n t\u1EED"}`;
        return `Qu\xE1 l\u1EDBn: mong \u0111\u1EE3i ${issue3.origin ?? "gi\xE1 tr\u1ECB"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `Qu\xE1 nh\u1ECF: mong \u0111\u1EE3i ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `Qu\xE1 nh\u1ECF: mong \u0111\u1EE3i ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `Chu\u1ED7i kh\xF4ng h\u1EE3p l\u1EC7: ph\u1EA3i b\u1EAFt \u0111\u1EA7u b\u1EB1ng "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `Chu\u1ED7i kh\xF4ng h\u1EE3p l\u1EC7: ph\u1EA3i k\u1EBFt th\xFAc b\u1EB1ng "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `Chu\u1ED7i kh\xF4ng h\u1EE3p l\u1EC7: ph\u1EA3i bao g\u1ED3m "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `Chu\u1ED7i kh\xF4ng h\u1EE3p l\u1EC7: ph\u1EA3i kh\u1EDBp v\u1EDBi m\u1EABu ${_issue.pattern}`;
        return `${FormatDictionary[_issue.format] ?? issue3.format} kh\xF4ng h\u1EE3p l\u1EC7`;
      }
      case "not_multiple_of":
        return `S\u1ED1 kh\xF4ng h\u1EE3p l\u1EC7: ph\u1EA3i l\xE0 b\u1ED9i s\u1ED1 c\u1EE7a ${issue3.divisor}`;
      case "unrecognized_keys":
        return `Kh\xF3a kh\xF4ng \u0111\u01B0\u1EE3c nh\u1EADn d\u1EA1ng: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `Kh\xF3a kh\xF4ng h\u1EE3p l\u1EC7 trong ${issue3.origin}`;
      case "invalid_union":
        return "\u0110\u1EA7u v\xE0o kh\xF4ng h\u1EE3p l\u1EC7";
      case "invalid_element":
        return `Gi\xE1 tr\u1ECB kh\xF4ng h\u1EE3p l\u1EC7 trong ${issue3.origin}`;
      default:
        return `\u0110\u1EA7u v\xE0o kh\xF4ng h\u1EE3p l\u1EC7`;
    }
  };
};
function vi_default() {
  return {
    localeError: error47()
  };
}

// node_modules/zod/v4/locales/zh-CN.js
var error48 = () => {
  const Sizable = {
    string: { unit: "\u5B57\u7B26", verb: "\u5305\u542B" },
    file: { unit: "\u5B57\u8282", verb: "\u5305\u542B" },
    array: { unit: "\u9879", verb: "\u5305\u542B" },
    set: { unit: "\u9879", verb: "\u5305\u542B" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u8F93\u5165",
    email: "\u7535\u5B50\u90AE\u4EF6",
    url: "URL",
    emoji: "\u8868\u60C5\u7B26\u53F7",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO\u65E5\u671F\u65F6\u95F4",
    date: "ISO\u65E5\u671F",
    time: "ISO\u65F6\u95F4",
    duration: "ISO\u65F6\u957F",
    ipv4: "IPv4\u5730\u5740",
    ipv6: "IPv6\u5730\u5740",
    cidrv4: "IPv4\u7F51\u6BB5",
    cidrv6: "IPv6\u7F51\u6BB5",
    base64: "base64\u7F16\u7801\u5B57\u7B26\u4E32",
    base64url: "base64url\u7F16\u7801\u5B57\u7B26\u4E32",
    json_string: "JSON\u5B57\u7B26\u4E32",
    e164: "E.164\u53F7\u7801",
    jwt: "JWT",
    template_literal: "\u8F93\u5165"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "\u6570\u5B57",
    array: "\u6570\u7EC4",
    null: "\u7A7A\u503C(null)"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u65E0\u6548\u8F93\u5165\uFF1A\u671F\u671B instanceof ${issue3.expected}\uFF0C\u5B9E\u9645\u63A5\u6536 ${received}`;
        }
        return `\u65E0\u6548\u8F93\u5165\uFF1A\u671F\u671B ${expected}\uFF0C\u5B9E\u9645\u63A5\u6536 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u65E0\u6548\u8F93\u5165\uFF1A\u671F\u671B ${stringifyPrimitive(issue3.values[0])}`;
        return `\u65E0\u6548\u9009\u9879\uFF1A\u671F\u671B\u4EE5\u4E0B\u4E4B\u4E00 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u6570\u503C\u8FC7\u5927\uFF1A\u671F\u671B ${issue3.origin ?? "\u503C"} ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u4E2A\u5143\u7D20"}`;
        return `\u6570\u503C\u8FC7\u5927\uFF1A\u671F\u671B ${issue3.origin ?? "\u503C"} ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u6570\u503C\u8FC7\u5C0F\uFF1A\u671F\u671B ${issue3.origin} ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u6570\u503C\u8FC7\u5C0F\uFF1A\u671F\u671B ${issue3.origin} ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u65E0\u6548\u5B57\u7B26\u4E32\uFF1A\u5FC5\u987B\u4EE5 "${_issue.prefix}" \u5F00\u5934`;
        if (_issue.format === "ends_with")
          return `\u65E0\u6548\u5B57\u7B26\u4E32\uFF1A\u5FC5\u987B\u4EE5 "${_issue.suffix}" \u7ED3\u5C3E`;
        if (_issue.format === "includes")
          return `\u65E0\u6548\u5B57\u7B26\u4E32\uFF1A\u5FC5\u987B\u5305\u542B "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u65E0\u6548\u5B57\u7B26\u4E32\uFF1A\u5FC5\u987B\u6EE1\u8DB3\u6B63\u5219\u8868\u8FBE\u5F0F ${_issue.pattern}`;
        return `\u65E0\u6548${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u65E0\u6548\u6570\u5B57\uFF1A\u5FC5\u987B\u662F ${issue3.divisor} \u7684\u500D\u6570`;
      case "unrecognized_keys":
        return `\u51FA\u73B0\u672A\u77E5\u7684\u952E(key): ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `${issue3.origin} \u4E2D\u7684\u952E(key)\u65E0\u6548`;
      case "invalid_union":
        return "\u65E0\u6548\u8F93\u5165";
      case "invalid_element":
        return `${issue3.origin} \u4E2D\u5305\u542B\u65E0\u6548\u503C(value)`;
      default:
        return `\u65E0\u6548\u8F93\u5165`;
    }
  };
};
function zh_CN_default() {
  return {
    localeError: error48()
  };
}

// node_modules/zod/v4/locales/zh-TW.js
var error49 = () => {
  const Sizable = {
    string: { unit: "\u5B57\u5143", verb: "\u64C1\u6709" },
    file: { unit: "\u4F4D\u5143\u7D44", verb: "\u64C1\u6709" },
    array: { unit: "\u9805\u76EE", verb: "\u64C1\u6709" },
    set: { unit: "\u9805\u76EE", verb: "\u64C1\u6709" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u8F38\u5165",
    email: "\u90F5\u4EF6\u5730\u5740",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "ISO \u65E5\u671F\u6642\u9593",
    date: "ISO \u65E5\u671F",
    time: "ISO \u6642\u9593",
    duration: "ISO \u671F\u9593",
    ipv4: "IPv4 \u4F4D\u5740",
    ipv6: "IPv6 \u4F4D\u5740",
    cidrv4: "IPv4 \u7BC4\u570D",
    cidrv6: "IPv6 \u7BC4\u570D",
    base64: "base64 \u7DE8\u78BC\u5B57\u4E32",
    base64url: "base64url \u7DE8\u78BC\u5B57\u4E32",
    json_string: "JSON \u5B57\u4E32",
    e164: "E.164 \u6578\u503C",
    jwt: "JWT",
    template_literal: "\u8F38\u5165"
  };
  const TypeDictionary = {
    nan: "NaN"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\u7121\u6548\u7684\u8F38\u5165\u503C\uFF1A\u9810\u671F\u70BA instanceof ${issue3.expected}\uFF0C\u4F46\u6536\u5230 ${received}`;
        }
        return `\u7121\u6548\u7684\u8F38\u5165\u503C\uFF1A\u9810\u671F\u70BA ${expected}\uFF0C\u4F46\u6536\u5230 ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\u7121\u6548\u7684\u8F38\u5165\u503C\uFF1A\u9810\u671F\u70BA ${stringifyPrimitive(issue3.values[0])}`;
        return `\u7121\u6548\u7684\u9078\u9805\uFF1A\u9810\u671F\u70BA\u4EE5\u4E0B\u5176\u4E2D\u4E4B\u4E00 ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `\u6578\u503C\u904E\u5927\uFF1A\u9810\u671F ${issue3.origin ?? "\u503C"} \u61C9\u70BA ${adj}${issue3.maximum.toString()} ${sizing.unit ?? "\u500B\u5143\u7D20"}`;
        return `\u6578\u503C\u904E\u5927\uFF1A\u9810\u671F ${issue3.origin ?? "\u503C"} \u61C9\u70BA ${adj}${issue3.maximum.toString()}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing) {
          return `\u6578\u503C\u904E\u5C0F\uFF1A\u9810\u671F ${issue3.origin} \u61C9\u70BA ${adj}${issue3.minimum.toString()} ${sizing.unit}`;
        }
        return `\u6578\u503C\u904E\u5C0F\uFF1A\u9810\u671F ${issue3.origin} \u61C9\u70BA ${adj}${issue3.minimum.toString()}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with") {
          return `\u7121\u6548\u7684\u5B57\u4E32\uFF1A\u5FC5\u9808\u4EE5 "${_issue.prefix}" \u958B\u982D`;
        }
        if (_issue.format === "ends_with")
          return `\u7121\u6548\u7684\u5B57\u4E32\uFF1A\u5FC5\u9808\u4EE5 "${_issue.suffix}" \u7D50\u5C3E`;
        if (_issue.format === "includes")
          return `\u7121\u6548\u7684\u5B57\u4E32\uFF1A\u5FC5\u9808\u5305\u542B "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u7121\u6548\u7684\u5B57\u4E32\uFF1A\u5FC5\u9808\u7B26\u5408\u683C\u5F0F ${_issue.pattern}`;
        return `\u7121\u6548\u7684 ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `\u7121\u6548\u7684\u6578\u5B57\uFF1A\u5FC5\u9808\u70BA ${issue3.divisor} \u7684\u500D\u6578`;
      case "unrecognized_keys":
        return `\u7121\u6CD5\u8B58\u5225\u7684\u9375\u503C${issue3.keys.length > 1 ? "\u5011" : ""}\uFF1A${joinValues(issue3.keys, "\u3001")}`;
      case "invalid_key":
        return `${issue3.origin} \u4E2D\u6709\u7121\u6548\u7684\u9375\u503C`;
      case "invalid_union":
        return "\u7121\u6548\u7684\u8F38\u5165\u503C";
      case "invalid_element":
        return `${issue3.origin} \u4E2D\u6709\u7121\u6548\u7684\u503C`;
      default:
        return `\u7121\u6548\u7684\u8F38\u5165\u503C`;
    }
  };
};
function zh_TW_default() {
  return {
    localeError: error49()
  };
}

// node_modules/zod/v4/locales/yo.js
var error50 = () => {
  const Sizable = {
    string: { unit: "\xE0mi", verb: "n\xED" },
    file: { unit: "bytes", verb: "n\xED" },
    array: { unit: "nkan", verb: "n\xED" },
    set: { unit: "nkan", verb: "n\xED" }
  };
  function getSizing(origin) {
    return Sizable[origin] ?? null;
  }
  const FormatDictionary = {
    regex: "\u1EB9\u0300r\u1ECD \xECb\xE1w\u1ECDl\xE9",
    email: "\xE0d\xEDr\u1EB9\u0301s\xEC \xECm\u1EB9\u0301l\xEC",
    url: "URL",
    emoji: "emoji",
    uuid: "UUID",
    uuidv4: "UUIDv4",
    uuidv6: "UUIDv6",
    nanoid: "nanoid",
    guid: "GUID",
    cuid: "cuid",
    cuid2: "cuid2",
    ulid: "ULID",
    xid: "XID",
    ksuid: "KSUID",
    datetime: "\xE0k\xF3k\xF2 ISO",
    date: "\u1ECDj\u1ECD\u0301 ISO",
    time: "\xE0k\xF3k\xF2 ISO",
    duration: "\xE0k\xF3k\xF2 t\xF3 p\xE9 ISO",
    ipv4: "\xE0d\xEDr\u1EB9\u0301s\xEC IPv4",
    ipv6: "\xE0d\xEDr\u1EB9\u0301s\xEC IPv6",
    cidrv4: "\xE0gb\xE8gb\xE8 IPv4",
    cidrv6: "\xE0gb\xE8gb\xE8 IPv6",
    base64: "\u1ECD\u0300r\u1ECD\u0300 t\xED a k\u1ECD\u0301 n\xED base64",
    base64url: "\u1ECD\u0300r\u1ECD\u0300 base64url",
    json_string: "\u1ECD\u0300r\u1ECD\u0300 JSON",
    e164: "n\u1ECD\u0301mb\xE0 E.164",
    jwt: "JWT",
    template_literal: "\u1EB9\u0300r\u1ECD \xECb\xE1w\u1ECDl\xE9"
  };
  const TypeDictionary = {
    nan: "NaN",
    number: "n\u1ECD\u0301mb\xE0",
    array: "akop\u1ECD"
  };
  return (issue3) => {
    switch (issue3.code) {
      case "invalid_type": {
        const expected = TypeDictionary[issue3.expected] ?? issue3.expected;
        const receivedType = parsedType(issue3.input);
        const received = TypeDictionary[receivedType] ?? receivedType;
        if (/^[A-Z]/.test(issue3.expected)) {
          return `\xCCb\xE1w\u1ECDl\xE9 a\u1E63\xEC\u1E63e: a n\xED l\xE1ti fi instanceof ${issue3.expected}, \xE0m\u1ECD\u0300 a r\xED ${received}`;
        }
        return `\xCCb\xE1w\u1ECDl\xE9 a\u1E63\xEC\u1E63e: a n\xED l\xE1ti fi ${expected}, \xE0m\u1ECD\u0300 a r\xED ${received}`;
      }
      case "invalid_value":
        if (issue3.values.length === 1)
          return `\xCCb\xE1w\u1ECDl\xE9 a\u1E63\xEC\u1E63e: a n\xED l\xE1ti fi ${stringifyPrimitive(issue3.values[0])}`;
        return `\xC0\u1E63\xE0y\xE0n a\u1E63\xEC\u1E63e: yan \u1ECD\u0300kan l\xE1ra ${joinValues(issue3.values, "|")}`;
      case "too_big": {
        const adj = issue3.inclusive ? "<=" : "<";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `T\xF3 p\u1ECD\u0300 j\xF9: a n\xED l\xE1ti j\u1EB9\u0301 p\xE9 ${issue3.origin ?? "iye"} ${sizing.verb} ${adj}${issue3.maximum} ${sizing.unit}`;
        return `T\xF3 p\u1ECD\u0300 j\xF9: a n\xED l\xE1ti j\u1EB9\u0301 ${adj}${issue3.maximum}`;
      }
      case "too_small": {
        const adj = issue3.inclusive ? ">=" : ">";
        const sizing = getSizing(issue3.origin);
        if (sizing)
          return `K\xE9r\xE9 ju: a n\xED l\xE1ti j\u1EB9\u0301 p\xE9 ${issue3.origin} ${sizing.verb} ${adj}${issue3.minimum} ${sizing.unit}`;
        return `K\xE9r\xE9 ju: a n\xED l\xE1ti j\u1EB9\u0301 ${adj}${issue3.minimum}`;
      }
      case "invalid_format": {
        const _issue = issue3;
        if (_issue.format === "starts_with")
          return `\u1ECC\u0300r\u1ECD\u0300 a\u1E63\xEC\u1E63e: gb\u1ECD\u0301d\u1ECD\u0300 b\u1EB9\u0300r\u1EB9\u0300 p\u1EB9\u0300l\xFA "${_issue.prefix}"`;
        if (_issue.format === "ends_with")
          return `\u1ECC\u0300r\u1ECD\u0300 a\u1E63\xEC\u1E63e: gb\u1ECD\u0301d\u1ECD\u0300 par\xED p\u1EB9\u0300l\xFA "${_issue.suffix}"`;
        if (_issue.format === "includes")
          return `\u1ECC\u0300r\u1ECD\u0300 a\u1E63\xEC\u1E63e: gb\u1ECD\u0301d\u1ECD\u0300 n\xED "${_issue.includes}"`;
        if (_issue.format === "regex")
          return `\u1ECC\u0300r\u1ECD\u0300 a\u1E63\xEC\u1E63e: gb\u1ECD\u0301d\u1ECD\u0300 b\xE1 \xE0p\u1EB9\u1EB9r\u1EB9 mu ${_issue.pattern}`;
        return `A\u1E63\xEC\u1E63e: ${FormatDictionary[_issue.format] ?? issue3.format}`;
      }
      case "not_multiple_of":
        return `N\u1ECD\u0301mb\xE0 a\u1E63\xEC\u1E63e: gb\u1ECD\u0301d\u1ECD\u0300 j\u1EB9\u0301 \xE8y\xE0 p\xEDp\xEDn ti ${issue3.divisor}`;
      case "unrecognized_keys":
        return `B\u1ECDt\xECn\xEC \xE0\xECm\u1ECD\u0300: ${joinValues(issue3.keys, ", ")}`;
      case "invalid_key":
        return `B\u1ECDt\xECn\xEC a\u1E63\xEC\u1E63e n\xEDn\xFA ${issue3.origin}`;
      case "invalid_union":
        return "\xCCb\xE1w\u1ECDl\xE9 a\u1E63\xEC\u1E63e";
      case "invalid_element":
        return `Iye a\u1E63\xEC\u1E63e n\xEDn\xFA ${issue3.origin}`;
      default:
        return "\xCCb\xE1w\u1ECDl\xE9 a\u1E63\xEC\u1E63e";
    }
  };
};
function yo_default() {
  return {
    localeError: error50()
  };
}

// node_modules/zod/v4/core/registries.js
var _a2;
var $output = /* @__PURE__ */ Symbol("ZodOutput");
var $input = /* @__PURE__ */ Symbol("ZodInput");
var $ZodRegistry = class {
  constructor() {
    this._map = /* @__PURE__ */ new WeakMap();
    this._idmap = /* @__PURE__ */ new Map();
  }
  add(schema, ..._meta) {
    const meta3 = _meta[0];
    this._map.set(schema, meta3);
    if (meta3 && typeof meta3 === "object" && "id" in meta3) {
      this._idmap.set(meta3.id, schema);
    }
    return this;
  }
  clear() {
    this._map = /* @__PURE__ */ new WeakMap();
    this._idmap = /* @__PURE__ */ new Map();
    return this;
  }
  remove(schema) {
    const meta3 = this._map.get(schema);
    if (meta3 && typeof meta3 === "object" && "id" in meta3) {
      this._idmap.delete(meta3.id);
    }
    this._map.delete(schema);
    return this;
  }
  get(schema) {
    const p = schema._zod.parent;
    if (p) {
      const pm = { ...this.get(p) ?? {} };
      delete pm.id;
      const f = { ...pm, ...this._map.get(schema) };
      return Object.keys(f).length ? f : void 0;
    }
    return this._map.get(schema);
  }
  has(schema) {
    return this._map.has(schema);
  }
};
function registry() {
  return new $ZodRegistry();
}
(_a2 = globalThis).__zod_globalRegistry ?? (_a2.__zod_globalRegistry = registry());
var globalRegistry = globalThis.__zod_globalRegistry;

// node_modules/zod/v4/core/api.js
// @__NO_SIDE_EFFECTS__
function _string(Class2, params) {
  return new Class2({
    type: "string",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _coercedString(Class2, params) {
  return new Class2({
    type: "string",
    coerce: true,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _email(Class2, params) {
  return new Class2({
    type: "string",
    format: "email",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _guid(Class2, params) {
  return new Class2({
    type: "string",
    format: "guid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uuid(Class2, params) {
  return new Class2({
    type: "string",
    format: "uuid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uuidv4(Class2, params) {
  return new Class2({
    type: "string",
    format: "uuid",
    check: "string_format",
    abort: false,
    version: "v4",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uuidv6(Class2, params) {
  return new Class2({
    type: "string",
    format: "uuid",
    check: "string_format",
    abort: false,
    version: "v6",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uuidv7(Class2, params) {
  return new Class2({
    type: "string",
    format: "uuid",
    check: "string_format",
    abort: false,
    version: "v7",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _url(Class2, params) {
  return new Class2({
    type: "string",
    format: "url",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _emoji2(Class2, params) {
  return new Class2({
    type: "string",
    format: "emoji",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _nanoid(Class2, params) {
  return new Class2({
    type: "string",
    format: "nanoid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _cuid(Class2, params) {
  return new Class2({
    type: "string",
    format: "cuid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _cuid2(Class2, params) {
  return new Class2({
    type: "string",
    format: "cuid2",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _ulid(Class2, params) {
  return new Class2({
    type: "string",
    format: "ulid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _xid(Class2, params) {
  return new Class2({
    type: "string",
    format: "xid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _ksuid(Class2, params) {
  return new Class2({
    type: "string",
    format: "ksuid",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _ipv4(Class2, params) {
  return new Class2({
    type: "string",
    format: "ipv4",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _ipv6(Class2, params) {
  return new Class2({
    type: "string",
    format: "ipv6",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _mac(Class2, params) {
  return new Class2({
    type: "string",
    format: "mac",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _cidrv4(Class2, params) {
  return new Class2({
    type: "string",
    format: "cidrv4",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _cidrv6(Class2, params) {
  return new Class2({
    type: "string",
    format: "cidrv6",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _base64(Class2, params) {
  return new Class2({
    type: "string",
    format: "base64",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _base64url(Class2, params) {
  return new Class2({
    type: "string",
    format: "base64url",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _e164(Class2, params) {
  return new Class2({
    type: "string",
    format: "e164",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _jwt(Class2, params) {
  return new Class2({
    type: "string",
    format: "jwt",
    check: "string_format",
    abort: false,
    ...normalizeParams(params)
  });
}
var TimePrecision = {
  Any: null,
  Minute: -1,
  Second: 0,
  Millisecond: 3,
  Microsecond: 6
};
// @__NO_SIDE_EFFECTS__
function _isoDateTime(Class2, params) {
  return new Class2({
    type: "string",
    format: "datetime",
    check: "string_format",
    offset: false,
    local: false,
    precision: null,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _isoDate(Class2, params) {
  return new Class2({
    type: "string",
    format: "date",
    check: "string_format",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _isoTime(Class2, params) {
  return new Class2({
    type: "string",
    format: "time",
    check: "string_format",
    precision: null,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _isoDuration(Class2, params) {
  return new Class2({
    type: "string",
    format: "duration",
    check: "string_format",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _number(Class2, params) {
  return new Class2({
    type: "number",
    checks: [],
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _coercedNumber(Class2, params) {
  return new Class2({
    type: "number",
    coerce: true,
    checks: [],
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _int(Class2, params) {
  return new Class2({
    type: "number",
    check: "number_format",
    abort: false,
    format: "safeint",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _float32(Class2, params) {
  return new Class2({
    type: "number",
    check: "number_format",
    abort: false,
    format: "float32",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _float64(Class2, params) {
  return new Class2({
    type: "number",
    check: "number_format",
    abort: false,
    format: "float64",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _int32(Class2, params) {
  return new Class2({
    type: "number",
    check: "number_format",
    abort: false,
    format: "int32",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uint32(Class2, params) {
  return new Class2({
    type: "number",
    check: "number_format",
    abort: false,
    format: "uint32",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _boolean(Class2, params) {
  return new Class2({
    type: "boolean",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _coercedBoolean(Class2, params) {
  return new Class2({
    type: "boolean",
    coerce: true,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _bigint(Class2, params) {
  return new Class2({
    type: "bigint",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _coercedBigint(Class2, params) {
  return new Class2({
    type: "bigint",
    coerce: true,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _int64(Class2, params) {
  return new Class2({
    type: "bigint",
    check: "bigint_format",
    abort: false,
    format: "int64",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uint64(Class2, params) {
  return new Class2({
    type: "bigint",
    check: "bigint_format",
    abort: false,
    format: "uint64",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _symbol(Class2, params) {
  return new Class2({
    type: "symbol",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _undefined2(Class2, params) {
  return new Class2({
    type: "undefined",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _null2(Class2, params) {
  return new Class2({
    type: "null",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _any(Class2) {
  return new Class2({
    type: "any"
  });
}
// @__NO_SIDE_EFFECTS__
function _unknown(Class2) {
  return new Class2({
    type: "unknown"
  });
}
// @__NO_SIDE_EFFECTS__
function _never(Class2, params) {
  return new Class2({
    type: "never",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _void(Class2, params) {
  return new Class2({
    type: "void",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _date(Class2, params) {
  return new Class2({
    type: "date",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _coercedDate(Class2, params) {
  return new Class2({
    type: "date",
    coerce: true,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _nan(Class2, params) {
  return new Class2({
    type: "nan",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _lt(value, params) {
  return new $ZodCheckLessThan({
    check: "less_than",
    ...normalizeParams(params),
    value,
    inclusive: false
  });
}
// @__NO_SIDE_EFFECTS__
function _lte(value, params) {
  return new $ZodCheckLessThan({
    check: "less_than",
    ...normalizeParams(params),
    value,
    inclusive: true
  });
}
// @__NO_SIDE_EFFECTS__
function _gt(value, params) {
  return new $ZodCheckGreaterThan({
    check: "greater_than",
    ...normalizeParams(params),
    value,
    inclusive: false
  });
}
// @__NO_SIDE_EFFECTS__
function _gte(value, params) {
  return new $ZodCheckGreaterThan({
    check: "greater_than",
    ...normalizeParams(params),
    value,
    inclusive: true
  });
}
// @__NO_SIDE_EFFECTS__
function _positive(params) {
  return /* @__PURE__ */ _gt(0, params);
}
// @__NO_SIDE_EFFECTS__
function _negative(params) {
  return /* @__PURE__ */ _lt(0, params);
}
// @__NO_SIDE_EFFECTS__
function _nonpositive(params) {
  return /* @__PURE__ */ _lte(0, params);
}
// @__NO_SIDE_EFFECTS__
function _nonnegative(params) {
  return /* @__PURE__ */ _gte(0, params);
}
// @__NO_SIDE_EFFECTS__
function _multipleOf(value, params) {
  return new $ZodCheckMultipleOf({
    check: "multiple_of",
    ...normalizeParams(params),
    value
  });
}
// @__NO_SIDE_EFFECTS__
function _maxSize(maximum, params) {
  return new $ZodCheckMaxSize({
    check: "max_size",
    ...normalizeParams(params),
    maximum
  });
}
// @__NO_SIDE_EFFECTS__
function _minSize(minimum, params) {
  return new $ZodCheckMinSize({
    check: "min_size",
    ...normalizeParams(params),
    minimum
  });
}
// @__NO_SIDE_EFFECTS__
function _size(size, params) {
  return new $ZodCheckSizeEquals({
    check: "size_equals",
    ...normalizeParams(params),
    size
  });
}
// @__NO_SIDE_EFFECTS__
function _maxLength(maximum, params) {
  const ch = new $ZodCheckMaxLength({
    check: "max_length",
    ...normalizeParams(params),
    maximum
  });
  return ch;
}
// @__NO_SIDE_EFFECTS__
function _minLength(minimum, params) {
  return new $ZodCheckMinLength({
    check: "min_length",
    ...normalizeParams(params),
    minimum
  });
}
// @__NO_SIDE_EFFECTS__
function _length(length, params) {
  return new $ZodCheckLengthEquals({
    check: "length_equals",
    ...normalizeParams(params),
    length
  });
}
// @__NO_SIDE_EFFECTS__
function _regex(pattern, params) {
  return new $ZodCheckRegex({
    check: "string_format",
    format: "regex",
    ...normalizeParams(params),
    pattern
  });
}
// @__NO_SIDE_EFFECTS__
function _lowercase(params) {
  return new $ZodCheckLowerCase({
    check: "string_format",
    format: "lowercase",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _uppercase(params) {
  return new $ZodCheckUpperCase({
    check: "string_format",
    format: "uppercase",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _includes(includes, params) {
  return new $ZodCheckIncludes({
    check: "string_format",
    format: "includes",
    ...normalizeParams(params),
    includes
  });
}
// @__NO_SIDE_EFFECTS__
function _startsWith(prefix, params) {
  return new $ZodCheckStartsWith({
    check: "string_format",
    format: "starts_with",
    ...normalizeParams(params),
    prefix
  });
}
// @__NO_SIDE_EFFECTS__
function _endsWith(suffix, params) {
  return new $ZodCheckEndsWith({
    check: "string_format",
    format: "ends_with",
    ...normalizeParams(params),
    suffix
  });
}
// @__NO_SIDE_EFFECTS__
function _property(property, schema, params) {
  return new $ZodCheckProperty({
    check: "property",
    property,
    schema,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _mime(types, params) {
  return new $ZodCheckMimeType({
    check: "mime_type",
    mime: types,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _overwrite(tx) {
  return new $ZodCheckOverwrite({
    check: "overwrite",
    tx
  });
}
// @__NO_SIDE_EFFECTS__
function _normalize(form) {
  return /* @__PURE__ */ _overwrite((input) => input.normalize(form));
}
// @__NO_SIDE_EFFECTS__
function _trim() {
  return /* @__PURE__ */ _overwrite((input) => input.trim());
}
// @__NO_SIDE_EFFECTS__
function _toLowerCase() {
  return /* @__PURE__ */ _overwrite((input) => input.toLowerCase());
}
// @__NO_SIDE_EFFECTS__
function _toUpperCase() {
  return /* @__PURE__ */ _overwrite((input) => input.toUpperCase());
}
// @__NO_SIDE_EFFECTS__
function _slugify() {
  return /* @__PURE__ */ _overwrite((input) => slugify(input));
}
// @__NO_SIDE_EFFECTS__
function _array(Class2, element, params) {
  return new Class2({
    type: "array",
    element,
    // get element() {
    //   return element;
    // },
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _union(Class2, options, params) {
  return new Class2({
    type: "union",
    options,
    ...normalizeParams(params)
  });
}
function _xor(Class2, options, params) {
  return new Class2({
    type: "union",
    options,
    inclusive: false,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _discriminatedUnion(Class2, discriminator, options, params) {
  return new Class2({
    type: "union",
    options,
    discriminator,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _intersection(Class2, left, right) {
  return new Class2({
    type: "intersection",
    left,
    right
  });
}
// @__NO_SIDE_EFFECTS__
function _tuple(Class2, items, _paramsOrRest, _params) {
  const hasRest = _paramsOrRest instanceof $ZodType;
  const params = hasRest ? _params : _paramsOrRest;
  const rest = hasRest ? _paramsOrRest : null;
  return new Class2({
    type: "tuple",
    items,
    rest,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _record(Class2, keyType, valueType, params) {
  return new Class2({
    type: "record",
    keyType,
    valueType,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _map(Class2, keyType, valueType, params) {
  return new Class2({
    type: "map",
    keyType,
    valueType,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _set(Class2, valueType, params) {
  return new Class2({
    type: "set",
    valueType,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _enum(Class2, values, params) {
  const entries = Array.isArray(values) ? Object.fromEntries(values.map((v) => [v, v])) : values;
  return new Class2({
    type: "enum",
    entries,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _nativeEnum(Class2, entries, params) {
  return new Class2({
    type: "enum",
    entries,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _literal(Class2, value, params) {
  return new Class2({
    type: "literal",
    values: Array.isArray(value) ? value : [value],
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _file(Class2, params) {
  return new Class2({
    type: "file",
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _transform(Class2, fn) {
  return new Class2({
    type: "transform",
    transform: fn
  });
}
// @__NO_SIDE_EFFECTS__
function _optional(Class2, innerType) {
  return new Class2({
    type: "optional",
    innerType
  });
}
// @__NO_SIDE_EFFECTS__
function _nullable(Class2, innerType) {
  return new Class2({
    type: "nullable",
    innerType
  });
}
// @__NO_SIDE_EFFECTS__
function _default(Class2, innerType, defaultValue) {
  return new Class2({
    type: "default",
    innerType,
    get defaultValue() {
      return typeof defaultValue === "function" ? defaultValue() : shallowClone(defaultValue);
    }
  });
}
// @__NO_SIDE_EFFECTS__
function _nonoptional(Class2, innerType, params) {
  return new Class2({
    type: "nonoptional",
    innerType,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _success(Class2, innerType) {
  return new Class2({
    type: "success",
    innerType
  });
}
// @__NO_SIDE_EFFECTS__
function _catch(Class2, innerType, catchValue) {
  return new Class2({
    type: "catch",
    innerType,
    catchValue: typeof catchValue === "function" ? catchValue : () => catchValue
  });
}
// @__NO_SIDE_EFFECTS__
function _pipe(Class2, in_, out) {
  return new Class2({
    type: "pipe",
    in: in_,
    out
  });
}
// @__NO_SIDE_EFFECTS__
function _readonly(Class2, innerType) {
  return new Class2({
    type: "readonly",
    innerType
  });
}
// @__NO_SIDE_EFFECTS__
function _templateLiteral(Class2, parts, params) {
  return new Class2({
    type: "template_literal",
    parts,
    ...normalizeParams(params)
  });
}
// @__NO_SIDE_EFFECTS__
function _lazy(Class2, getter) {
  return new Class2({
    type: "lazy",
    getter
  });
}
// @__NO_SIDE_EFFECTS__
function _promise(Class2, innerType) {
  return new Class2({
    type: "promise",
    innerType
  });
}
// @__NO_SIDE_EFFECTS__
function _custom(Class2, fn, _params) {
  const norm = normalizeParams(_params);
  norm.abort ?? (norm.abort = true);
  const schema = new Class2({
    type: "custom",
    check: "custom",
    fn,
    ...norm
  });
  return schema;
}
// @__NO_SIDE_EFFECTS__
function _refine(Class2, fn, _params) {
  const schema = new Class2({
    type: "custom",
    check: "custom",
    fn,
    ...normalizeParams(_params)
  });
  return schema;
}
// @__NO_SIDE_EFFECTS__
function _superRefine(fn, params) {
  const ch = /* @__PURE__ */ _check((payload) => {
    payload.addIssue = (issue3) => {
      if (typeof issue3 === "string") {
        payload.issues.push(issue(issue3, payload.value, ch._zod.def));
      } else {
        const _issue = issue3;
        if (_issue.fatal)
          _issue.continue = false;
        _issue.code ?? (_issue.code = "custom");
        _issue.input ?? (_issue.input = payload.value);
        _issue.inst ?? (_issue.inst = ch);
        _issue.continue ?? (_issue.continue = !ch._zod.def.abort);
        payload.issues.push(issue(_issue));
      }
    };
    return fn(payload.value, payload);
  }, params);
  return ch;
}
// @__NO_SIDE_EFFECTS__
function _check(fn, params) {
  const ch = new $ZodCheck({
    check: "custom",
    ...normalizeParams(params)
  });
  ch._zod.check = fn;
  return ch;
}
// @__NO_SIDE_EFFECTS__
function describe(description) {
  const ch = new $ZodCheck({ check: "describe" });
  ch._zod.onattach = [
    (inst) => {
      const existing = globalRegistry.get(inst) ?? {};
      globalRegistry.add(inst, { ...existing, description });
    }
  ];
  ch._zod.check = () => {
  };
  return ch;
}
// @__NO_SIDE_EFFECTS__
function meta(metadata) {
  const ch = new $ZodCheck({ check: "meta" });
  ch._zod.onattach = [
    (inst) => {
      const existing = globalRegistry.get(inst) ?? {};
      globalRegistry.add(inst, { ...existing, ...metadata });
    }
  ];
  ch._zod.check = () => {
  };
  return ch;
}
// @__NO_SIDE_EFFECTS__
function _stringbool(Classes, _params) {
  const params = normalizeParams(_params);
  let truthyArray = params.truthy ?? ["true", "1", "yes", "on", "y", "enabled"];
  let falsyArray = params.falsy ?? ["false", "0", "no", "off", "n", "disabled"];
  if (params.case !== "sensitive") {
    truthyArray = truthyArray.map((v) => typeof v === "string" ? v.toLowerCase() : v);
    falsyArray = falsyArray.map((v) => typeof v === "string" ? v.toLowerCase() : v);
  }
  const truthySet = new Set(truthyArray);
  const falsySet = new Set(falsyArray);
  const _Codec = Classes.Codec ?? $ZodCodec;
  const _Boolean = Classes.Boolean ?? $ZodBoolean;
  const _String = Classes.String ?? $ZodString;
  const stringSchema = new _String({ type: "string", error: params.error });
  const booleanSchema = new _Boolean({ type: "boolean", error: params.error });
  const codec2 = new _Codec({
    type: "pipe",
    in: stringSchema,
    out: booleanSchema,
    transform: ((input, payload) => {
      let data = input;
      if (params.case !== "sensitive")
        data = data.toLowerCase();
      if (truthySet.has(data)) {
        return true;
      } else if (falsySet.has(data)) {
        return false;
      } else {
        payload.issues.push({
          code: "invalid_value",
          expected: "stringbool",
          values: [...truthySet, ...falsySet],
          input: payload.value,
          inst: codec2,
          continue: false
        });
        return {};
      }
    }),
    reverseTransform: ((input, _payload) => {
      if (input === true) {
        return truthyArray[0] || "true";
      } else {
        return falsyArray[0] || "false";
      }
    }),
    error: params.error
  });
  return codec2;
}
// @__NO_SIDE_EFFECTS__
function _stringFormat(Class2, format, fnOrRegex, _params = {}) {
  const params = normalizeParams(_params);
  const def = {
    ...normalizeParams(_params),
    check: "string_format",
    type: "string",
    format,
    fn: typeof fnOrRegex === "function" ? fnOrRegex : (val) => fnOrRegex.test(val),
    ...params
  };
  if (fnOrRegex instanceof RegExp) {
    def.pattern = fnOrRegex;
  }
  const inst = new Class2(def);
  return inst;
}

// node_modules/zod/v4/core/to-json-schema.js
function initializeContext(params) {
  let target = params?.target ?? "draft-2020-12";
  if (target === "draft-4")
    target = "draft-04";
  if (target === "draft-7")
    target = "draft-07";
  return {
    processors: params.processors ?? {},
    metadataRegistry: params?.metadata ?? globalRegistry,
    target,
    unrepresentable: params?.unrepresentable ?? "throw",
    override: params?.override ?? (() => {
    }),
    io: params?.io ?? "output",
    counter: 0,
    seen: /* @__PURE__ */ new Map(),
    cycles: params?.cycles ?? "ref",
    reused: params?.reused ?? "inline",
    external: params?.external ?? void 0
  };
}
function process2(schema, ctx, _params = { path: [], schemaPath: [] }) {
  var _a3;
  const def = schema._zod.def;
  const seen = ctx.seen.get(schema);
  if (seen) {
    seen.count++;
    const isCycle = _params.schemaPath.includes(schema);
    if (isCycle) {
      seen.cycle = _params.path;
    }
    return seen.schema;
  }
  const result = { schema: {}, count: 1, cycle: void 0, path: _params.path };
  ctx.seen.set(schema, result);
  const overrideSchema = schema._zod.toJSONSchema?.();
  if (overrideSchema) {
    result.schema = overrideSchema;
  } else {
    const params = {
      ..._params,
      schemaPath: [..._params.schemaPath, schema],
      path: _params.path
    };
    if (schema._zod.processJSONSchema) {
      schema._zod.processJSONSchema(ctx, result.schema, params);
    } else {
      const _json = result.schema;
      const processor = ctx.processors[def.type];
      if (!processor) {
        throw new Error(`[toJSONSchema]: Non-representable type encountered: ${def.type}`);
      }
      processor(schema, ctx, _json, params);
    }
    const parent = schema._zod.parent;
    if (parent) {
      if (!result.ref)
        result.ref = parent;
      process2(parent, ctx, params);
      ctx.seen.get(parent).isParent = true;
    }
  }
  const meta3 = ctx.metadataRegistry.get(schema);
  if (meta3)
    Object.assign(result.schema, meta3);
  if (ctx.io === "input" && isTransforming(schema)) {
    delete result.schema.examples;
    delete result.schema.default;
  }
  if (ctx.io === "input" && "_prefault" in result.schema)
    (_a3 = result.schema).default ?? (_a3.default = result.schema._prefault);
  delete result.schema._prefault;
  const _result = ctx.seen.get(schema);
  return _result.schema;
}
function extractDefs(ctx, schema) {
  const root = ctx.seen.get(schema);
  if (!root)
    throw new Error("Unprocessed schema. This is a bug in Zod.");
  const idToSchema = /* @__PURE__ */ new Map();
  for (const entry of ctx.seen.entries()) {
    const id = ctx.metadataRegistry.get(entry[0])?.id;
    if (id) {
      const existing = idToSchema.get(id);
      if (existing && existing !== entry[0]) {
        throw new Error(`Duplicate schema id "${id}" detected during JSON Schema conversion. Two different schemas cannot share the same id when converted together.`);
      }
      idToSchema.set(id, entry[0]);
    }
  }
  const makeURI = (entry) => {
    const defsSegment = ctx.target === "draft-2020-12" ? "$defs" : "definitions";
    if (ctx.external) {
      const externalId = ctx.external.registry.get(entry[0])?.id;
      const uriGenerator = ctx.external.uri ?? ((id2) => id2);
      if (externalId) {
        return { ref: uriGenerator(externalId) };
      }
      const id = entry[1].defId ?? entry[1].schema.id ?? `schema${ctx.counter++}`;
      entry[1].defId = id;
      return { defId: id, ref: `${uriGenerator("__shared")}#/${defsSegment}/${id}` };
    }
    if (entry[1] === root) {
      return { ref: "#" };
    }
    const uriPrefix = `#`;
    const defUriPrefix = `${uriPrefix}/${defsSegment}/`;
    const defId = entry[1].schema.id ?? `__schema${ctx.counter++}`;
    return { defId, ref: defUriPrefix + defId };
  };
  const extractToDef = (entry) => {
    if (entry[1].schema.$ref) {
      return;
    }
    const seen = entry[1];
    const { ref, defId } = makeURI(entry);
    seen.def = { ...seen.schema };
    if (defId)
      seen.defId = defId;
    const schema2 = seen.schema;
    for (const key in schema2) {
      delete schema2[key];
    }
    schema2.$ref = ref;
  };
  if (ctx.cycles === "throw") {
    for (const entry of ctx.seen.entries()) {
      const seen = entry[1];
      if (seen.cycle) {
        throw new Error(`Cycle detected: #/${seen.cycle?.join("/")}/<root>

Set the \`cycles\` parameter to \`"ref"\` to resolve cyclical schemas with defs.`);
      }
    }
  }
  for (const entry of ctx.seen.entries()) {
    const seen = entry[1];
    if (schema === entry[0]) {
      extractToDef(entry);
      continue;
    }
    if (ctx.external) {
      const ext = ctx.external.registry.get(entry[0])?.id;
      if (schema !== entry[0] && ext) {
        extractToDef(entry);
        continue;
      }
    }
    const id = ctx.metadataRegistry.get(entry[0])?.id;
    if (id) {
      extractToDef(entry);
      continue;
    }
    if (seen.cycle) {
      extractToDef(entry);
      continue;
    }
    if (seen.count > 1) {
      if (ctx.reused === "ref") {
        extractToDef(entry);
        continue;
      }
    }
  }
}
function finalize(ctx, schema) {
  const root = ctx.seen.get(schema);
  if (!root)
    throw new Error("Unprocessed schema. This is a bug in Zod.");
  const flattenRef = (zodSchema) => {
    const seen = ctx.seen.get(zodSchema);
    if (seen.ref === null)
      return;
    const schema2 = seen.def ?? seen.schema;
    const _cached = { ...schema2 };
    const ref = seen.ref;
    seen.ref = null;
    if (ref) {
      flattenRef(ref);
      const refSeen = ctx.seen.get(ref);
      const refSchema = refSeen.schema;
      if (refSchema.$ref && (ctx.target === "draft-07" || ctx.target === "draft-04" || ctx.target === "openapi-3.0")) {
        schema2.allOf = schema2.allOf ?? [];
        schema2.allOf.push(refSchema);
      } else {
        Object.assign(schema2, refSchema);
      }
      Object.assign(schema2, _cached);
      const isParentRef = zodSchema._zod.parent === ref;
      if (isParentRef) {
        for (const key in schema2) {
          if (key === "$ref" || key === "allOf")
            continue;
          if (!(key in _cached)) {
            delete schema2[key];
          }
        }
      }
      if (refSchema.$ref && refSeen.def) {
        for (const key in schema2) {
          if (key === "$ref" || key === "allOf")
            continue;
          if (key in refSeen.def && JSON.stringify(schema2[key]) === JSON.stringify(refSeen.def[key])) {
            delete schema2[key];
          }
        }
      }
    }
    const parent = zodSchema._zod.parent;
    if (parent && parent !== ref) {
      flattenRef(parent);
      const parentSeen = ctx.seen.get(parent);
      if (parentSeen?.schema.$ref) {
        schema2.$ref = parentSeen.schema.$ref;
        if (parentSeen.def) {
          for (const key in schema2) {
            if (key === "$ref" || key === "allOf")
              continue;
            if (key in parentSeen.def && JSON.stringify(schema2[key]) === JSON.stringify(parentSeen.def[key])) {
              delete schema2[key];
            }
          }
        }
      }
    }
    ctx.override({
      zodSchema,
      jsonSchema: schema2,
      path: seen.path ?? []
    });
  };
  for (const entry of [...ctx.seen.entries()].reverse()) {
    flattenRef(entry[0]);
  }
  const result = {};
  if (ctx.target === "draft-2020-12") {
    result.$schema = "https://json-schema.org/draft/2020-12/schema";
  } else if (ctx.target === "draft-07") {
    result.$schema = "http://json-schema.org/draft-07/schema#";
  } else if (ctx.target === "draft-04") {
    result.$schema = "http://json-schema.org/draft-04/schema#";
  } else if (ctx.target === "openapi-3.0") {
  } else {
  }
  if (ctx.external?.uri) {
    const id = ctx.external.registry.get(schema)?.id;
    if (!id)
      throw new Error("Schema is missing an `id` property");
    result.$id = ctx.external.uri(id);
  }
  Object.assign(result, root.def ?? root.schema);
  const rootMetaId = ctx.metadataRegistry.get(schema)?.id;
  if (rootMetaId !== void 0 && result.id === rootMetaId)
    delete result.id;
  const defs = ctx.external?.defs ?? {};
  for (const entry of ctx.seen.entries()) {
    const seen = entry[1];
    if (seen.def && seen.defId) {
      if (seen.def.id === seen.defId)
        delete seen.def.id;
      defs[seen.defId] = seen.def;
    }
  }
  if (ctx.external) {
  } else {
    if (Object.keys(defs).length > 0) {
      if (ctx.target === "draft-2020-12") {
        result.$defs = defs;
      } else {
        result.definitions = defs;
      }
    }
  }
  try {
    const finalized = JSON.parse(JSON.stringify(result));
    Object.defineProperty(finalized, "~standard", {
      value: {
        ...schema["~standard"],
        jsonSchema: {
          input: createStandardJSONSchemaMethod(schema, "input", ctx.processors),
          output: createStandardJSONSchemaMethod(schema, "output", ctx.processors)
        }
      },
      enumerable: false,
      writable: false
    });
    return finalized;
  } catch (_err) {
    throw new Error("Error converting schema to JSON.");
  }
}
function isTransforming(_schema, _ctx) {
  const ctx = _ctx ?? { seen: /* @__PURE__ */ new Set() };
  if (ctx.seen.has(_schema))
    return false;
  ctx.seen.add(_schema);
  const def = _schema._zod.def;
  if (def.type === "transform")
    return true;
  if (def.type === "array")
    return isTransforming(def.element, ctx);
  if (def.type === "set")
    return isTransforming(def.valueType, ctx);
  if (def.type === "lazy")
    return isTransforming(def.getter(), ctx);
  if (def.type === "promise" || def.type === "optional" || def.type === "nonoptional" || def.type === "nullable" || def.type === "readonly" || def.type === "default" || def.type === "prefault") {
    return isTransforming(def.innerType, ctx);
  }
  if (def.type === "intersection") {
    return isTransforming(def.left, ctx) || isTransforming(def.right, ctx);
  }
  if (def.type === "record" || def.type === "map") {
    return isTransforming(def.keyType, ctx) || isTransforming(def.valueType, ctx);
  }
  if (def.type === "pipe") {
    if (_schema._zod.traits.has("$ZodCodec"))
      return true;
    return isTransforming(def.in, ctx) || isTransforming(def.out, ctx);
  }
  if (def.type === "object") {
    for (const key in def.shape) {
      if (isTransforming(def.shape[key], ctx))
        return true;
    }
    return false;
  }
  if (def.type === "union") {
    for (const option of def.options) {
      if (isTransforming(option, ctx))
        return true;
    }
    return false;
  }
  if (def.type === "tuple") {
    for (const item of def.items) {
      if (isTransforming(item, ctx))
        return true;
    }
    if (def.rest && isTransforming(def.rest, ctx))
      return true;
    return false;
  }
  return false;
}
var createToJSONSchemaMethod = (schema, processors = {}) => (params) => {
  const ctx = initializeContext({ ...params, processors });
  process2(schema, ctx);
  extractDefs(ctx, schema);
  return finalize(ctx, schema);
};
var createStandardJSONSchemaMethod = (schema, io, processors = {}) => (params) => {
  const { libraryOptions, target } = params ?? {};
  const ctx = initializeContext({ ...libraryOptions ?? {}, target, io, processors });
  process2(schema, ctx);
  extractDefs(ctx, schema);
  return finalize(ctx, schema);
};

// node_modules/zod/v4/core/json-schema-processors.js
var formatMap = {
  guid: "uuid",
  url: "uri",
  datetime: "date-time",
  json_string: "json-string",
  regex: ""
  // do not set
};
var stringProcessor = (schema, ctx, _json, _params) => {
  const json2 = _json;
  json2.type = "string";
  const { minimum, maximum, format, patterns, contentEncoding } = schema._zod.bag;
  if (typeof minimum === "number")
    json2.minLength = minimum;
  if (typeof maximum === "number")
    json2.maxLength = maximum;
  if (format) {
    json2.format = formatMap[format] ?? format;
    if (json2.format === "")
      delete json2.format;
    if (format === "time") {
      delete json2.format;
    }
  }
  if (contentEncoding)
    json2.contentEncoding = contentEncoding;
  if (patterns && patterns.size > 0) {
    const regexes = [...patterns];
    if (regexes.length === 1)
      json2.pattern = regexes[0].source;
    else if (regexes.length > 1) {
      json2.allOf = [
        ...regexes.map((regex) => ({
          ...ctx.target === "draft-07" || ctx.target === "draft-04" || ctx.target === "openapi-3.0" ? { type: "string" } : {},
          pattern: regex.source
        }))
      ];
    }
  }
};
var numberProcessor = (schema, ctx, _json, _params) => {
  const json2 = _json;
  const { minimum, maximum, format, multipleOf, exclusiveMaximum, exclusiveMinimum } = schema._zod.bag;
  if (typeof format === "string" && format.includes("int"))
    json2.type = "integer";
  else
    json2.type = "number";
  const exMin = typeof exclusiveMinimum === "number" && exclusiveMinimum >= (minimum ?? Number.NEGATIVE_INFINITY);
  const exMax = typeof exclusiveMaximum === "number" && exclusiveMaximum <= (maximum ?? Number.POSITIVE_INFINITY);
  const legacy = ctx.target === "draft-04" || ctx.target === "openapi-3.0";
  if (exMin) {
    if (legacy) {
      json2.minimum = exclusiveMinimum;
      json2.exclusiveMinimum = true;
    } else {
      json2.exclusiveMinimum = exclusiveMinimum;
    }
  } else if (typeof minimum === "number") {
    json2.minimum = minimum;
  }
  if (exMax) {
    if (legacy) {
      json2.maximum = exclusiveMaximum;
      json2.exclusiveMaximum = true;
    } else {
      json2.exclusiveMaximum = exclusiveMaximum;
    }
  } else if (typeof maximum === "number") {
    json2.maximum = maximum;
  }
  if (typeof multipleOf === "number")
    json2.multipleOf = multipleOf;
};
var booleanProcessor = (_schema, _ctx, json2, _params) => {
  json2.type = "boolean";
};
var bigintProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("BigInt cannot be represented in JSON Schema");
  }
};
var symbolProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Symbols cannot be represented in JSON Schema");
  }
};
var nullProcessor = (_schema, ctx, json2, _params) => {
  if (ctx.target === "openapi-3.0") {
    json2.type = "string";
    json2.nullable = true;
    json2.enum = [null];
  } else {
    json2.type = "null";
  }
};
var undefinedProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Undefined cannot be represented in JSON Schema");
  }
};
var voidProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Void cannot be represented in JSON Schema");
  }
};
var neverProcessor = (_schema, _ctx, json2, _params) => {
  json2.not = {};
};
var anyProcessor = (_schema, _ctx, _json, _params) => {
};
var unknownProcessor = (_schema, _ctx, _json, _params) => {
};
var dateProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Date cannot be represented in JSON Schema");
  }
};
var enumProcessor = (schema, _ctx, json2, _params) => {
  const def = schema._zod.def;
  const values = getEnumValues(def.entries);
  if (values.every((v) => typeof v === "number"))
    json2.type = "number";
  if (values.every((v) => typeof v === "string"))
    json2.type = "string";
  json2.enum = values;
};
var literalProcessor = (schema, ctx, json2, _params) => {
  const def = schema._zod.def;
  const vals = [];
  for (const val of def.values) {
    if (val === void 0) {
      if (ctx.unrepresentable === "throw") {
        throw new Error("Literal `undefined` cannot be represented in JSON Schema");
      } else {
      }
    } else if (typeof val === "bigint") {
      if (ctx.unrepresentable === "throw") {
        throw new Error("BigInt literals cannot be represented in JSON Schema");
      } else {
        vals.push(Number(val));
      }
    } else {
      vals.push(val);
    }
  }
  if (vals.length === 0) {
  } else if (vals.length === 1) {
    const val = vals[0];
    json2.type = val === null ? "null" : typeof val;
    if (ctx.target === "draft-04" || ctx.target === "openapi-3.0") {
      json2.enum = [val];
    } else {
      json2.const = val;
    }
  } else {
    if (vals.every((v) => typeof v === "number"))
      json2.type = "number";
    if (vals.every((v) => typeof v === "string"))
      json2.type = "string";
    if (vals.every((v) => typeof v === "boolean"))
      json2.type = "boolean";
    if (vals.every((v) => v === null))
      json2.type = "null";
    json2.enum = vals;
  }
};
var nanProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("NaN cannot be represented in JSON Schema");
  }
};
var templateLiteralProcessor = (schema, _ctx, json2, _params) => {
  const _json = json2;
  const pattern = schema._zod.pattern;
  if (!pattern)
    throw new Error("Pattern not found in template literal");
  _json.type = "string";
  _json.pattern = pattern.source;
};
var fileProcessor = (schema, _ctx, json2, _params) => {
  const _json = json2;
  const file2 = {
    type: "string",
    format: "binary",
    contentEncoding: "binary"
  };
  const { minimum, maximum, mime } = schema._zod.bag;
  if (minimum !== void 0)
    file2.minLength = minimum;
  if (maximum !== void 0)
    file2.maxLength = maximum;
  if (mime) {
    if (mime.length === 1) {
      file2.contentMediaType = mime[0];
      Object.assign(_json, file2);
    } else {
      Object.assign(_json, file2);
      _json.anyOf = mime.map((m) => ({ contentMediaType: m }));
    }
  } else {
    Object.assign(_json, file2);
  }
};
var successProcessor = (_schema, _ctx, json2, _params) => {
  json2.type = "boolean";
};
var customProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Custom types cannot be represented in JSON Schema");
  }
};
var functionProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Function types cannot be represented in JSON Schema");
  }
};
var transformProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Transforms cannot be represented in JSON Schema");
  }
};
var mapProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Map cannot be represented in JSON Schema");
  }
};
var setProcessor = (_schema, ctx, _json, _params) => {
  if (ctx.unrepresentable === "throw") {
    throw new Error("Set cannot be represented in JSON Schema");
  }
};
var arrayProcessor = (schema, ctx, _json, params) => {
  const json2 = _json;
  const def = schema._zod.def;
  const { minimum, maximum } = schema._zod.bag;
  if (typeof minimum === "number")
    json2.minItems = minimum;
  if (typeof maximum === "number")
    json2.maxItems = maximum;
  json2.type = "array";
  json2.items = process2(def.element, ctx, {
    ...params,
    path: [...params.path, "items"]
  });
};
var objectProcessor = (schema, ctx, _json, params) => {
  const json2 = _json;
  const def = schema._zod.def;
  json2.type = "object";
  json2.properties = {};
  const shape = def.shape;
  for (const key in shape) {
    json2.properties[key] = process2(shape[key], ctx, {
      ...params,
      path: [...params.path, "properties", key]
    });
  }
  const allKeys = new Set(Object.keys(shape));
  const requiredKeys = new Set([...allKeys].filter((key) => {
    const v = def.shape[key]._zod;
    if (ctx.io === "input") {
      return v.optin === void 0;
    } else {
      return v.optout === void 0;
    }
  }));
  if (requiredKeys.size > 0) {
    json2.required = Array.from(requiredKeys);
  }
  if (def.catchall?._zod.def.type === "never") {
    json2.additionalProperties = false;
  } else if (!def.catchall) {
    if (ctx.io === "output")
      json2.additionalProperties = false;
  } else if (def.catchall) {
    json2.additionalProperties = process2(def.catchall, ctx, {
      ...params,
      path: [...params.path, "additionalProperties"]
    });
  }
};
var unionProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  const isExclusive = def.inclusive === false;
  const options = def.options.map((x, i) => process2(x, ctx, {
    ...params,
    path: [...params.path, isExclusive ? "oneOf" : "anyOf", i]
  }));
  if (isExclusive) {
    json2.oneOf = options;
  } else {
    json2.anyOf = options;
  }
};
var intersectionProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  const a = process2(def.left, ctx, {
    ...params,
    path: [...params.path, "allOf", 0]
  });
  const b = process2(def.right, ctx, {
    ...params,
    path: [...params.path, "allOf", 1]
  });
  const isSimpleIntersection = (val) => "allOf" in val && Object.keys(val).length === 1;
  const allOf = [
    ...isSimpleIntersection(a) ? a.allOf : [a],
    ...isSimpleIntersection(b) ? b.allOf : [b]
  ];
  json2.allOf = allOf;
};
var tupleProcessor = (schema, ctx, _json, params) => {
  const json2 = _json;
  const def = schema._zod.def;
  json2.type = "array";
  const prefixPath = ctx.target === "draft-2020-12" ? "prefixItems" : "items";
  const restPath = ctx.target === "draft-2020-12" ? "items" : ctx.target === "openapi-3.0" ? "items" : "additionalItems";
  const prefixItems = def.items.map((x, i) => process2(x, ctx, {
    ...params,
    path: [...params.path, prefixPath, i]
  }));
  const rest = def.rest ? process2(def.rest, ctx, {
    ...params,
    path: [...params.path, restPath, ...ctx.target === "openapi-3.0" ? [def.items.length] : []]
  }) : null;
  if (ctx.target === "draft-2020-12") {
    json2.prefixItems = prefixItems;
    if (rest) {
      json2.items = rest;
    }
  } else if (ctx.target === "openapi-3.0") {
    json2.items = {
      anyOf: prefixItems
    };
    if (rest) {
      json2.items.anyOf.push(rest);
    }
    json2.minItems = prefixItems.length;
    if (!rest) {
      json2.maxItems = prefixItems.length;
    }
  } else {
    json2.items = prefixItems;
    if (rest) {
      json2.additionalItems = rest;
    }
  }
  const { minimum, maximum } = schema._zod.bag;
  if (typeof minimum === "number")
    json2.minItems = minimum;
  if (typeof maximum === "number")
    json2.maxItems = maximum;
};
var recordProcessor = (schema, ctx, _json, params) => {
  const json2 = _json;
  const def = schema._zod.def;
  json2.type = "object";
  const keyType = def.keyType;
  const keyBag = keyType._zod.bag;
  const patterns = keyBag?.patterns;
  if (def.mode === "loose" && patterns && patterns.size > 0) {
    const valueSchema = process2(def.valueType, ctx, {
      ...params,
      path: [...params.path, "patternProperties", "*"]
    });
    json2.patternProperties = {};
    for (const pattern of patterns) {
      json2.patternProperties[pattern.source] = valueSchema;
    }
  } else {
    if (ctx.target === "draft-07" || ctx.target === "draft-2020-12") {
      json2.propertyNames = process2(def.keyType, ctx, {
        ...params,
        path: [...params.path, "propertyNames"]
      });
    }
    json2.additionalProperties = process2(def.valueType, ctx, {
      ...params,
      path: [...params.path, "additionalProperties"]
    });
  }
  const keyValues = keyType._zod.values;
  if (keyValues) {
    const validKeyValues = [...keyValues].filter((v) => typeof v === "string" || typeof v === "number");
    if (validKeyValues.length > 0) {
      json2.required = validKeyValues;
    }
  }
};
var nullableProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  const inner = process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  if (ctx.target === "openapi-3.0") {
    seen.ref = def.innerType;
    json2.nullable = true;
  } else {
    json2.anyOf = [inner, { type: "null" }];
  }
};
var nonoptionalProcessor = (schema, ctx, _json, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
};
var defaultProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
  json2.default = JSON.parse(JSON.stringify(def.defaultValue));
};
var prefaultProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
  if (ctx.io === "input")
    json2._prefault = JSON.parse(JSON.stringify(def.defaultValue));
};
var catchProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
  let catchValue;
  try {
    catchValue = def.catchValue(void 0);
  } catch {
    throw new Error("Dynamic catch values are not supported in JSON Schema");
  }
  json2.default = catchValue;
};
var pipeProcessor = (schema, ctx, _json, params) => {
  const def = schema._zod.def;
  const inIsTransform = def.in._zod.traits.has("$ZodTransform");
  const innerType = ctx.io === "input" ? inIsTransform ? def.out : def.in : def.out;
  process2(innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = innerType;
};
var readonlyProcessor = (schema, ctx, json2, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
  json2.readOnly = true;
};
var promiseProcessor = (schema, ctx, _json, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
};
var optionalProcessor = (schema, ctx, _json, params) => {
  const def = schema._zod.def;
  process2(def.innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = def.innerType;
};
var lazyProcessor = (schema, ctx, _json, params) => {
  const innerType = schema._zod.innerType;
  process2(innerType, ctx, params);
  const seen = ctx.seen.get(schema);
  seen.ref = innerType;
};
var allProcessors = {
  string: stringProcessor,
  number: numberProcessor,
  boolean: booleanProcessor,
  bigint: bigintProcessor,
  symbol: symbolProcessor,
  null: nullProcessor,
  undefined: undefinedProcessor,
  void: voidProcessor,
  never: neverProcessor,
  any: anyProcessor,
  unknown: unknownProcessor,
  date: dateProcessor,
  enum: enumProcessor,
  literal: literalProcessor,
  nan: nanProcessor,
  template_literal: templateLiteralProcessor,
  file: fileProcessor,
  success: successProcessor,
  custom: customProcessor,
  function: functionProcessor,
  transform: transformProcessor,
  map: mapProcessor,
  set: setProcessor,
  array: arrayProcessor,
  object: objectProcessor,
  union: unionProcessor,
  intersection: intersectionProcessor,
  tuple: tupleProcessor,
  record: recordProcessor,
  nullable: nullableProcessor,
  nonoptional: nonoptionalProcessor,
  default: defaultProcessor,
  prefault: prefaultProcessor,
  catch: catchProcessor,
  pipe: pipeProcessor,
  readonly: readonlyProcessor,
  promise: promiseProcessor,
  optional: optionalProcessor,
  lazy: lazyProcessor
};
function toJSONSchema(input, params) {
  if ("_idmap" in input) {
    const registry2 = input;
    const ctx2 = initializeContext({ ...params, processors: allProcessors });
    const defs = {};
    for (const entry of registry2._idmap.entries()) {
      const [_, schema] = entry;
      process2(schema, ctx2);
    }
    const schemas = {};
    const external = {
      registry: registry2,
      uri: params?.uri,
      defs
    };
    ctx2.external = external;
    for (const entry of registry2._idmap.entries()) {
      const [key, schema] = entry;
      extractDefs(ctx2, schema);
      schemas[key] = finalize(ctx2, schema);
    }
    if (Object.keys(defs).length > 0) {
      const defsSegment = ctx2.target === "draft-2020-12" ? "$defs" : "definitions";
      schemas.__shared = {
        [defsSegment]: defs
      };
    }
    return { schemas };
  }
  const ctx = initializeContext({ ...params, processors: allProcessors });
  process2(input, ctx);
  extractDefs(ctx, input);
  return finalize(ctx, input);
}

// node_modules/zod/v4/core/json-schema-generator.js
var JSONSchemaGenerator = class {
  /** @deprecated Access via ctx instead */
  get metadataRegistry() {
    return this.ctx.metadataRegistry;
  }
  /** @deprecated Access via ctx instead */
  get target() {
    return this.ctx.target;
  }
  /** @deprecated Access via ctx instead */
  get unrepresentable() {
    return this.ctx.unrepresentable;
  }
  /** @deprecated Access via ctx instead */
  get override() {
    return this.ctx.override;
  }
  /** @deprecated Access via ctx instead */
  get io() {
    return this.ctx.io;
  }
  /** @deprecated Access via ctx instead */
  get counter() {
    return this.ctx.counter;
  }
  set counter(value) {
    this.ctx.counter = value;
  }
  /** @deprecated Access via ctx instead */
  get seen() {
    return this.ctx.seen;
  }
  constructor(params) {
    let normalizedTarget = params?.target ?? "draft-2020-12";
    if (normalizedTarget === "draft-4")
      normalizedTarget = "draft-04";
    if (normalizedTarget === "draft-7")
      normalizedTarget = "draft-07";
    this.ctx = initializeContext({
      processors: allProcessors,
      target: normalizedTarget,
      ...params?.metadata && { metadata: params.metadata },
      ...params?.unrepresentable && { unrepresentable: params.unrepresentable },
      ...params?.override && { override: params.override },
      ...params?.io && { io: params.io }
    });
  }
  /**
   * Process a schema to prepare it for JSON Schema generation.
   * This must be called before emit().
   */
  process(schema, _params = { path: [], schemaPath: [] }) {
    return process2(schema, this.ctx, _params);
  }
  /**
   * Emit the final JSON Schema after processing.
   * Must call process() first.
   */
  emit(schema, _params) {
    if (_params) {
      if (_params.cycles)
        this.ctx.cycles = _params.cycles;
      if (_params.reused)
        this.ctx.reused = _params.reused;
      if (_params.external)
        this.ctx.external = _params.external;
    }
    extractDefs(this.ctx, schema);
    const result = finalize(this.ctx, schema);
    const { "~standard": _, ...plainResult } = result;
    return plainResult;
  }
};

// node_modules/zod/v4/core/json-schema.js
var json_schema_exports = {};

// node_modules/zod/v4/classic/schemas.js
var schemas_exports2 = {};
__export(schemas_exports2, {
  ZodAny: () => ZodAny,
  ZodArray: () => ZodArray,
  ZodBase64: () => ZodBase64,
  ZodBase64URL: () => ZodBase64URL,
  ZodBigInt: () => ZodBigInt,
  ZodBigIntFormat: () => ZodBigIntFormat,
  ZodBoolean: () => ZodBoolean,
  ZodCIDRv4: () => ZodCIDRv4,
  ZodCIDRv6: () => ZodCIDRv6,
  ZodCUID: () => ZodCUID,
  ZodCUID2: () => ZodCUID2,
  ZodCatch: () => ZodCatch,
  ZodCodec: () => ZodCodec,
  ZodCustom: () => ZodCustom,
  ZodCustomStringFormat: () => ZodCustomStringFormat,
  ZodDate: () => ZodDate,
  ZodDefault: () => ZodDefault,
  ZodDiscriminatedUnion: () => ZodDiscriminatedUnion,
  ZodE164: () => ZodE164,
  ZodEmail: () => ZodEmail,
  ZodEmoji: () => ZodEmoji,
  ZodEnum: () => ZodEnum,
  ZodExactOptional: () => ZodExactOptional,
  ZodFile: () => ZodFile,
  ZodFunction: () => ZodFunction,
  ZodGUID: () => ZodGUID,
  ZodIPv4: () => ZodIPv4,
  ZodIPv6: () => ZodIPv6,
  ZodIntersection: () => ZodIntersection,
  ZodJWT: () => ZodJWT,
  ZodKSUID: () => ZodKSUID,
  ZodLazy: () => ZodLazy,
  ZodLiteral: () => ZodLiteral,
  ZodMAC: () => ZodMAC,
  ZodMap: () => ZodMap,
  ZodNaN: () => ZodNaN,
  ZodNanoID: () => ZodNanoID,
  ZodNever: () => ZodNever,
  ZodNonOptional: () => ZodNonOptional,
  ZodNull: () => ZodNull,
  ZodNullable: () => ZodNullable,
  ZodNumber: () => ZodNumber,
  ZodNumberFormat: () => ZodNumberFormat,
  ZodObject: () => ZodObject,
  ZodOptional: () => ZodOptional,
  ZodPipe: () => ZodPipe,
  ZodPrefault: () => ZodPrefault,
  ZodPreprocess: () => ZodPreprocess,
  ZodPromise: () => ZodPromise,
  ZodReadonly: () => ZodReadonly,
  ZodRecord: () => ZodRecord,
  ZodSet: () => ZodSet,
  ZodString: () => ZodString,
  ZodStringFormat: () => ZodStringFormat,
  ZodSuccess: () => ZodSuccess,
  ZodSymbol: () => ZodSymbol,
  ZodTemplateLiteral: () => ZodTemplateLiteral,
  ZodTransform: () => ZodTransform,
  ZodTuple: () => ZodTuple,
  ZodType: () => ZodType,
  ZodULID: () => ZodULID,
  ZodURL: () => ZodURL,
  ZodUUID: () => ZodUUID,
  ZodUndefined: () => ZodUndefined,
  ZodUnion: () => ZodUnion,
  ZodUnknown: () => ZodUnknown,
  ZodVoid: () => ZodVoid,
  ZodXID: () => ZodXID,
  ZodXor: () => ZodXor,
  _ZodString: () => _ZodString,
  _default: () => _default2,
  _function: () => _function,
  any: () => any,
  array: () => array,
  base64: () => base642,
  base64url: () => base64url2,
  bigint: () => bigint2,
  boolean: () => boolean2,
  catch: () => _catch2,
  check: () => check,
  cidrv4: () => cidrv42,
  cidrv6: () => cidrv62,
  codec: () => codec,
  cuid: () => cuid3,
  cuid2: () => cuid22,
  custom: () => custom,
  date: () => date3,
  describe: () => describe2,
  discriminatedUnion: () => discriminatedUnion,
  e164: () => e1642,
  email: () => email2,
  emoji: () => emoji2,
  enum: () => _enum2,
  exactOptional: () => exactOptional,
  file: () => file,
  float32: () => float32,
  float64: () => float64,
  function: () => _function,
  guid: () => guid2,
  hash: () => hash,
  hex: () => hex2,
  hostname: () => hostname2,
  httpUrl: () => httpUrl,
  instanceof: () => _instanceof,
  int: () => int,
  int32: () => int32,
  int64: () => int64,
  intersection: () => intersection,
  invertCodec: () => invertCodec,
  ipv4: () => ipv42,
  ipv6: () => ipv62,
  json: () => json,
  jwt: () => jwt,
  keyof: () => keyof,
  ksuid: () => ksuid2,
  lazy: () => lazy,
  literal: () => literal,
  looseObject: () => looseObject,
  looseRecord: () => looseRecord,
  mac: () => mac2,
  map: () => map,
  meta: () => meta2,
  nan: () => nan,
  nanoid: () => nanoid2,
  nativeEnum: () => nativeEnum,
  never: () => never,
  nonoptional: () => nonoptional,
  null: () => _null3,
  nullable: () => nullable,
  nullish: () => nullish2,
  number: () => number2,
  object: () => object,
  optional: () => optional,
  partialRecord: () => partialRecord,
  pipe: () => pipe,
  prefault: () => prefault,
  preprocess: () => preprocess,
  promise: () => promise,
  readonly: () => readonly,
  record: () => record,
  refine: () => refine,
  set: () => set,
  strictObject: () => strictObject,
  string: () => string2,
  stringFormat: () => stringFormat,
  stringbool: () => stringbool,
  success: () => success,
  superRefine: () => superRefine,
  symbol: () => symbol,
  templateLiteral: () => templateLiteral,
  transform: () => transform,
  tuple: () => tuple,
  uint32: () => uint32,
  uint64: () => uint64,
  ulid: () => ulid2,
  undefined: () => _undefined3,
  union: () => union,
  unknown: () => unknown,
  url: () => url,
  uuid: () => uuid2,
  uuidv4: () => uuidv4,
  uuidv6: () => uuidv6,
  uuidv7: () => uuidv7,
  void: () => _void2,
  xid: () => xid2,
  xor: () => xor
});

// node_modules/zod/v4/classic/checks.js
var checks_exports2 = {};
__export(checks_exports2, {
  endsWith: () => _endsWith,
  gt: () => _gt,
  gte: () => _gte,
  includes: () => _includes,
  length: () => _length,
  lowercase: () => _lowercase,
  lt: () => _lt,
  lte: () => _lte,
  maxLength: () => _maxLength,
  maxSize: () => _maxSize,
  mime: () => _mime,
  minLength: () => _minLength,
  minSize: () => _minSize,
  multipleOf: () => _multipleOf,
  negative: () => _negative,
  nonnegative: () => _nonnegative,
  nonpositive: () => _nonpositive,
  normalize: () => _normalize,
  overwrite: () => _overwrite,
  positive: () => _positive,
  property: () => _property,
  regex: () => _regex,
  size: () => _size,
  slugify: () => _slugify,
  startsWith: () => _startsWith,
  toLowerCase: () => _toLowerCase,
  toUpperCase: () => _toUpperCase,
  trim: () => _trim,
  uppercase: () => _uppercase
});

// node_modules/zod/v4/classic/iso.js
var iso_exports = {};
__export(iso_exports, {
  ZodISODate: () => ZodISODate,
  ZodISODateTime: () => ZodISODateTime,
  ZodISODuration: () => ZodISODuration,
  ZodISOTime: () => ZodISOTime,
  date: () => date2,
  datetime: () => datetime2,
  duration: () => duration2,
  time: () => time2
});
var ZodISODateTime = /* @__PURE__ */ $constructor("ZodISODateTime", (inst, def) => {
  $ZodISODateTime.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function datetime2(params) {
  return _isoDateTime(ZodISODateTime, params);
}
var ZodISODate = /* @__PURE__ */ $constructor("ZodISODate", (inst, def) => {
  $ZodISODate.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function date2(params) {
  return _isoDate(ZodISODate, params);
}
var ZodISOTime = /* @__PURE__ */ $constructor("ZodISOTime", (inst, def) => {
  $ZodISOTime.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function time2(params) {
  return _isoTime(ZodISOTime, params);
}
var ZodISODuration = /* @__PURE__ */ $constructor("ZodISODuration", (inst, def) => {
  $ZodISODuration.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function duration2(params) {
  return _isoDuration(ZodISODuration, params);
}

// node_modules/zod/v4/classic/errors.js
var initializer2 = (inst, issues) => {
  $ZodError.init(inst, issues);
  inst.name = "ZodError";
  Object.defineProperties(inst, {
    format: {
      value: (mapper) => formatError(inst, mapper)
      // enumerable: false,
    },
    flatten: {
      value: (mapper) => flattenError(inst, mapper)
      // enumerable: false,
    },
    addIssue: {
      value: (issue3) => {
        inst.issues.push(issue3);
        inst.message = JSON.stringify(inst.issues, jsonStringifyReplacer, 2);
      }
      // enumerable: false,
    },
    addIssues: {
      value: (issues2) => {
        inst.issues.push(...issues2);
        inst.message = JSON.stringify(inst.issues, jsonStringifyReplacer, 2);
      }
      // enumerable: false,
    },
    isEmpty: {
      get() {
        return inst.issues.length === 0;
      }
      // enumerable: false,
    }
  });
};
var ZodError = /* @__PURE__ */ $constructor("ZodError", initializer2);
var ZodRealError = /* @__PURE__ */ $constructor("ZodError", initializer2, {
  Parent: Error
});

// node_modules/zod/v4/classic/parse.js
var parse2 = /* @__PURE__ */ _parse(ZodRealError);
var parseAsync2 = /* @__PURE__ */ _parseAsync(ZodRealError);
var safeParse2 = /* @__PURE__ */ _safeParse(ZodRealError);
var safeParseAsync2 = /* @__PURE__ */ _safeParseAsync(ZodRealError);
var encode2 = /* @__PURE__ */ _encode(ZodRealError);
var decode2 = /* @__PURE__ */ _decode(ZodRealError);
var encodeAsync2 = /* @__PURE__ */ _encodeAsync(ZodRealError);
var decodeAsync2 = /* @__PURE__ */ _decodeAsync(ZodRealError);
var safeEncode2 = /* @__PURE__ */ _safeEncode(ZodRealError);
var safeDecode2 = /* @__PURE__ */ _safeDecode(ZodRealError);
var safeEncodeAsync2 = /* @__PURE__ */ _safeEncodeAsync(ZodRealError);
var safeDecodeAsync2 = /* @__PURE__ */ _safeDecodeAsync(ZodRealError);

// node_modules/zod/v4/classic/schemas.js
var _installedGroups = /* @__PURE__ */ new WeakMap();
function _installLazyMethods(inst, group, methods) {
  const proto = Object.getPrototypeOf(inst);
  let installed = _installedGroups.get(proto);
  if (!installed) {
    installed = /* @__PURE__ */ new Set();
    _installedGroups.set(proto, installed);
  }
  if (installed.has(group))
    return;
  installed.add(group);
  for (const key in methods) {
    const fn = methods[key];
    Object.defineProperty(proto, key, {
      configurable: true,
      enumerable: false,
      get() {
        const bound = fn.bind(this);
        Object.defineProperty(this, key, {
          configurable: true,
          writable: true,
          enumerable: true,
          value: bound
        });
        return bound;
      },
      set(v) {
        Object.defineProperty(this, key, {
          configurable: true,
          writable: true,
          enumerable: true,
          value: v
        });
      }
    });
  }
}
var ZodType = /* @__PURE__ */ $constructor("ZodType", (inst, def) => {
  $ZodType.init(inst, def);
  Object.assign(inst["~standard"], {
    jsonSchema: {
      input: createStandardJSONSchemaMethod(inst, "input"),
      output: createStandardJSONSchemaMethod(inst, "output")
    }
  });
  inst.toJSONSchema = createToJSONSchemaMethod(inst, {});
  inst.def = def;
  inst.type = def.type;
  Object.defineProperty(inst, "_def", { value: def });
  inst.parse = (data, params) => parse2(inst, data, params, { callee: inst.parse });
  inst.safeParse = (data, params) => safeParse2(inst, data, params);
  inst.parseAsync = async (data, params) => parseAsync2(inst, data, params, { callee: inst.parseAsync });
  inst.safeParseAsync = async (data, params) => safeParseAsync2(inst, data, params);
  inst.spa = inst.safeParseAsync;
  inst.encode = (data, params) => encode2(inst, data, params);
  inst.decode = (data, params) => decode2(inst, data, params);
  inst.encodeAsync = async (data, params) => encodeAsync2(inst, data, params);
  inst.decodeAsync = async (data, params) => decodeAsync2(inst, data, params);
  inst.safeEncode = (data, params) => safeEncode2(inst, data, params);
  inst.safeDecode = (data, params) => safeDecode2(inst, data, params);
  inst.safeEncodeAsync = async (data, params) => safeEncodeAsync2(inst, data, params);
  inst.safeDecodeAsync = async (data, params) => safeDecodeAsync2(inst, data, params);
  _installLazyMethods(inst, "ZodType", {
    check(...chks) {
      const def2 = this.def;
      return this.clone(util_exports.mergeDefs(def2, {
        checks: [
          ...def2.checks ?? [],
          ...chks.map((ch) => typeof ch === "function" ? { _zod: { check: ch, def: { check: "custom" }, onattach: [] } } : ch)
        ]
      }), { parent: true });
    },
    with(...chks) {
      return this.check(...chks);
    },
    clone(def2, params) {
      return clone(this, def2, params);
    },
    brand() {
      return this;
    },
    register(reg, meta3) {
      reg.add(this, meta3);
      return this;
    },
    refine(check2, params) {
      return this.check(refine(check2, params));
    },
    superRefine(refinement, params) {
      return this.check(superRefine(refinement, params));
    },
    overwrite(fn) {
      return this.check(_overwrite(fn));
    },
    optional() {
      return optional(this);
    },
    exactOptional() {
      return exactOptional(this);
    },
    nullable() {
      return nullable(this);
    },
    nullish() {
      return optional(nullable(this));
    },
    nonoptional(params) {
      return nonoptional(this, params);
    },
    array() {
      return array(this);
    },
    or(arg) {
      return union([this, arg]);
    },
    and(arg) {
      return intersection(this, arg);
    },
    transform(tx) {
      return pipe(this, transform(tx));
    },
    default(d) {
      return _default2(this, d);
    },
    prefault(d) {
      return prefault(this, d);
    },
    catch(params) {
      return _catch2(this, params);
    },
    pipe(target) {
      return pipe(this, target);
    },
    readonly() {
      return readonly(this);
    },
    describe(description) {
      const cl = this.clone();
      globalRegistry.add(cl, { description });
      return cl;
    },
    meta(...args) {
      if (args.length === 0)
        return globalRegistry.get(this);
      const cl = this.clone();
      globalRegistry.add(cl, args[0]);
      return cl;
    },
    isOptional() {
      return this.safeParse(void 0).success;
    },
    isNullable() {
      return this.safeParse(null).success;
    },
    apply(fn) {
      return fn(this);
    }
  });
  Object.defineProperty(inst, "description", {
    get() {
      return globalRegistry.get(inst)?.description;
    },
    configurable: true
  });
  return inst;
});
var _ZodString = /* @__PURE__ */ $constructor("_ZodString", (inst, def) => {
  $ZodString.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => stringProcessor(inst, ctx, json2, params);
  const bag = inst._zod.bag;
  inst.format = bag.format ?? null;
  inst.minLength = bag.minimum ?? null;
  inst.maxLength = bag.maximum ?? null;
  _installLazyMethods(inst, "_ZodString", {
    regex(...args) {
      return this.check(_regex(...args));
    },
    includes(...args) {
      return this.check(_includes(...args));
    },
    startsWith(...args) {
      return this.check(_startsWith(...args));
    },
    endsWith(...args) {
      return this.check(_endsWith(...args));
    },
    min(...args) {
      return this.check(_minLength(...args));
    },
    max(...args) {
      return this.check(_maxLength(...args));
    },
    length(...args) {
      return this.check(_length(...args));
    },
    nonempty(...args) {
      return this.check(_minLength(1, ...args));
    },
    lowercase(params) {
      return this.check(_lowercase(params));
    },
    uppercase(params) {
      return this.check(_uppercase(params));
    },
    trim() {
      return this.check(_trim());
    },
    normalize(...args) {
      return this.check(_normalize(...args));
    },
    toLowerCase() {
      return this.check(_toLowerCase());
    },
    toUpperCase() {
      return this.check(_toUpperCase());
    },
    slugify() {
      return this.check(_slugify());
    }
  });
});
var ZodString = /* @__PURE__ */ $constructor("ZodString", (inst, def) => {
  $ZodString.init(inst, def);
  _ZodString.init(inst, def);
  inst.email = (params) => inst.check(_email(ZodEmail, params));
  inst.url = (params) => inst.check(_url(ZodURL, params));
  inst.jwt = (params) => inst.check(_jwt(ZodJWT, params));
  inst.emoji = (params) => inst.check(_emoji2(ZodEmoji, params));
  inst.guid = (params) => inst.check(_guid(ZodGUID, params));
  inst.uuid = (params) => inst.check(_uuid(ZodUUID, params));
  inst.uuidv4 = (params) => inst.check(_uuidv4(ZodUUID, params));
  inst.uuidv6 = (params) => inst.check(_uuidv6(ZodUUID, params));
  inst.uuidv7 = (params) => inst.check(_uuidv7(ZodUUID, params));
  inst.nanoid = (params) => inst.check(_nanoid(ZodNanoID, params));
  inst.guid = (params) => inst.check(_guid(ZodGUID, params));
  inst.cuid = (params) => inst.check(_cuid(ZodCUID, params));
  inst.cuid2 = (params) => inst.check(_cuid2(ZodCUID2, params));
  inst.ulid = (params) => inst.check(_ulid(ZodULID, params));
  inst.base64 = (params) => inst.check(_base64(ZodBase64, params));
  inst.base64url = (params) => inst.check(_base64url(ZodBase64URL, params));
  inst.xid = (params) => inst.check(_xid(ZodXID, params));
  inst.ksuid = (params) => inst.check(_ksuid(ZodKSUID, params));
  inst.ipv4 = (params) => inst.check(_ipv4(ZodIPv4, params));
  inst.ipv6 = (params) => inst.check(_ipv6(ZodIPv6, params));
  inst.cidrv4 = (params) => inst.check(_cidrv4(ZodCIDRv4, params));
  inst.cidrv6 = (params) => inst.check(_cidrv6(ZodCIDRv6, params));
  inst.e164 = (params) => inst.check(_e164(ZodE164, params));
  inst.datetime = (params) => inst.check(datetime2(params));
  inst.date = (params) => inst.check(date2(params));
  inst.time = (params) => inst.check(time2(params));
  inst.duration = (params) => inst.check(duration2(params));
});
function string2(params) {
  return _string(ZodString, params);
}
var ZodStringFormat = /* @__PURE__ */ $constructor("ZodStringFormat", (inst, def) => {
  $ZodStringFormat.init(inst, def);
  _ZodString.init(inst, def);
});
var ZodEmail = /* @__PURE__ */ $constructor("ZodEmail", (inst, def) => {
  $ZodEmail.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function email2(params) {
  return _email(ZodEmail, params);
}
var ZodGUID = /* @__PURE__ */ $constructor("ZodGUID", (inst, def) => {
  $ZodGUID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function guid2(params) {
  return _guid(ZodGUID, params);
}
var ZodUUID = /* @__PURE__ */ $constructor("ZodUUID", (inst, def) => {
  $ZodUUID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function uuid2(params) {
  return _uuid(ZodUUID, params);
}
function uuidv4(params) {
  return _uuidv4(ZodUUID, params);
}
function uuidv6(params) {
  return _uuidv6(ZodUUID, params);
}
function uuidv7(params) {
  return _uuidv7(ZodUUID, params);
}
var ZodURL = /* @__PURE__ */ $constructor("ZodURL", (inst, def) => {
  $ZodURL.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function url(params) {
  return _url(ZodURL, params);
}
function httpUrl(params) {
  return _url(ZodURL, {
    protocol: regexes_exports.httpProtocol,
    hostname: regexes_exports.domain,
    ...util_exports.normalizeParams(params)
  });
}
var ZodEmoji = /* @__PURE__ */ $constructor("ZodEmoji", (inst, def) => {
  $ZodEmoji.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function emoji2(params) {
  return _emoji2(ZodEmoji, params);
}
var ZodNanoID = /* @__PURE__ */ $constructor("ZodNanoID", (inst, def) => {
  $ZodNanoID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function nanoid2(params) {
  return _nanoid(ZodNanoID, params);
}
var ZodCUID = /* @__PURE__ */ $constructor("ZodCUID", (inst, def) => {
  $ZodCUID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function cuid3(params) {
  return _cuid(ZodCUID, params);
}
var ZodCUID2 = /* @__PURE__ */ $constructor("ZodCUID2", (inst, def) => {
  $ZodCUID2.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function cuid22(params) {
  return _cuid2(ZodCUID2, params);
}
var ZodULID = /* @__PURE__ */ $constructor("ZodULID", (inst, def) => {
  $ZodULID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function ulid2(params) {
  return _ulid(ZodULID, params);
}
var ZodXID = /* @__PURE__ */ $constructor("ZodXID", (inst, def) => {
  $ZodXID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function xid2(params) {
  return _xid(ZodXID, params);
}
var ZodKSUID = /* @__PURE__ */ $constructor("ZodKSUID", (inst, def) => {
  $ZodKSUID.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function ksuid2(params) {
  return _ksuid(ZodKSUID, params);
}
var ZodIPv4 = /* @__PURE__ */ $constructor("ZodIPv4", (inst, def) => {
  $ZodIPv4.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function ipv42(params) {
  return _ipv4(ZodIPv4, params);
}
var ZodMAC = /* @__PURE__ */ $constructor("ZodMAC", (inst, def) => {
  $ZodMAC.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function mac2(params) {
  return _mac(ZodMAC, params);
}
var ZodIPv6 = /* @__PURE__ */ $constructor("ZodIPv6", (inst, def) => {
  $ZodIPv6.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function ipv62(params) {
  return _ipv6(ZodIPv6, params);
}
var ZodCIDRv4 = /* @__PURE__ */ $constructor("ZodCIDRv4", (inst, def) => {
  $ZodCIDRv4.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function cidrv42(params) {
  return _cidrv4(ZodCIDRv4, params);
}
var ZodCIDRv6 = /* @__PURE__ */ $constructor("ZodCIDRv6", (inst, def) => {
  $ZodCIDRv6.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function cidrv62(params) {
  return _cidrv6(ZodCIDRv6, params);
}
var ZodBase64 = /* @__PURE__ */ $constructor("ZodBase64", (inst, def) => {
  $ZodBase64.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function base642(params) {
  return _base64(ZodBase64, params);
}
var ZodBase64URL = /* @__PURE__ */ $constructor("ZodBase64URL", (inst, def) => {
  $ZodBase64URL.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function base64url2(params) {
  return _base64url(ZodBase64URL, params);
}
var ZodE164 = /* @__PURE__ */ $constructor("ZodE164", (inst, def) => {
  $ZodE164.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function e1642(params) {
  return _e164(ZodE164, params);
}
var ZodJWT = /* @__PURE__ */ $constructor("ZodJWT", (inst, def) => {
  $ZodJWT.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function jwt(params) {
  return _jwt(ZodJWT, params);
}
var ZodCustomStringFormat = /* @__PURE__ */ $constructor("ZodCustomStringFormat", (inst, def) => {
  $ZodCustomStringFormat.init(inst, def);
  ZodStringFormat.init(inst, def);
});
function stringFormat(format, fnOrRegex, _params = {}) {
  return _stringFormat(ZodCustomStringFormat, format, fnOrRegex, _params);
}
function hostname2(_params) {
  return _stringFormat(ZodCustomStringFormat, "hostname", regexes_exports.hostname, _params);
}
function hex2(_params) {
  return _stringFormat(ZodCustomStringFormat, "hex", regexes_exports.hex, _params);
}
function hash(alg, params) {
  const enc = params?.enc ?? "hex";
  const format = `${alg}_${enc}`;
  const regex = regexes_exports[format];
  if (!regex)
    throw new Error(`Unrecognized hash format: ${format}`);
  return _stringFormat(ZodCustomStringFormat, format, regex, params);
}
var ZodNumber = /* @__PURE__ */ $constructor("ZodNumber", (inst, def) => {
  $ZodNumber.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => numberProcessor(inst, ctx, json2, params);
  _installLazyMethods(inst, "ZodNumber", {
    gt(value, params) {
      return this.check(_gt(value, params));
    },
    gte(value, params) {
      return this.check(_gte(value, params));
    },
    min(value, params) {
      return this.check(_gte(value, params));
    },
    lt(value, params) {
      return this.check(_lt(value, params));
    },
    lte(value, params) {
      return this.check(_lte(value, params));
    },
    max(value, params) {
      return this.check(_lte(value, params));
    },
    int(params) {
      return this.check(int(params));
    },
    safe(params) {
      return this.check(int(params));
    },
    positive(params) {
      return this.check(_gt(0, params));
    },
    nonnegative(params) {
      return this.check(_gte(0, params));
    },
    negative(params) {
      return this.check(_lt(0, params));
    },
    nonpositive(params) {
      return this.check(_lte(0, params));
    },
    multipleOf(value, params) {
      return this.check(_multipleOf(value, params));
    },
    step(value, params) {
      return this.check(_multipleOf(value, params));
    },
    finite() {
      return this;
    }
  });
  const bag = inst._zod.bag;
  inst.minValue = Math.max(bag.minimum ?? Number.NEGATIVE_INFINITY, bag.exclusiveMinimum ?? Number.NEGATIVE_INFINITY) ?? null;
  inst.maxValue = Math.min(bag.maximum ?? Number.POSITIVE_INFINITY, bag.exclusiveMaximum ?? Number.POSITIVE_INFINITY) ?? null;
  inst.isInt = (bag.format ?? "").includes("int") || Number.isSafeInteger(bag.multipleOf ?? 0.5);
  inst.isFinite = true;
  inst.format = bag.format ?? null;
});
function number2(params) {
  return _number(ZodNumber, params);
}
var ZodNumberFormat = /* @__PURE__ */ $constructor("ZodNumberFormat", (inst, def) => {
  $ZodNumberFormat.init(inst, def);
  ZodNumber.init(inst, def);
});
function int(params) {
  return _int(ZodNumberFormat, params);
}
function float32(params) {
  return _float32(ZodNumberFormat, params);
}
function float64(params) {
  return _float64(ZodNumberFormat, params);
}
function int32(params) {
  return _int32(ZodNumberFormat, params);
}
function uint32(params) {
  return _uint32(ZodNumberFormat, params);
}
var ZodBoolean = /* @__PURE__ */ $constructor("ZodBoolean", (inst, def) => {
  $ZodBoolean.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => booleanProcessor(inst, ctx, json2, params);
});
function boolean2(params) {
  return _boolean(ZodBoolean, params);
}
var ZodBigInt = /* @__PURE__ */ $constructor("ZodBigInt", (inst, def) => {
  $ZodBigInt.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => bigintProcessor(inst, ctx, json2, params);
  inst.gte = (value, params) => inst.check(_gte(value, params));
  inst.min = (value, params) => inst.check(_gte(value, params));
  inst.gt = (value, params) => inst.check(_gt(value, params));
  inst.gte = (value, params) => inst.check(_gte(value, params));
  inst.min = (value, params) => inst.check(_gte(value, params));
  inst.lt = (value, params) => inst.check(_lt(value, params));
  inst.lte = (value, params) => inst.check(_lte(value, params));
  inst.max = (value, params) => inst.check(_lte(value, params));
  inst.positive = (params) => inst.check(_gt(BigInt(0), params));
  inst.negative = (params) => inst.check(_lt(BigInt(0), params));
  inst.nonpositive = (params) => inst.check(_lte(BigInt(0), params));
  inst.nonnegative = (params) => inst.check(_gte(BigInt(0), params));
  inst.multipleOf = (value, params) => inst.check(_multipleOf(value, params));
  const bag = inst._zod.bag;
  inst.minValue = bag.minimum ?? null;
  inst.maxValue = bag.maximum ?? null;
  inst.format = bag.format ?? null;
});
function bigint2(params) {
  return _bigint(ZodBigInt, params);
}
var ZodBigIntFormat = /* @__PURE__ */ $constructor("ZodBigIntFormat", (inst, def) => {
  $ZodBigIntFormat.init(inst, def);
  ZodBigInt.init(inst, def);
});
function int64(params) {
  return _int64(ZodBigIntFormat, params);
}
function uint64(params) {
  return _uint64(ZodBigIntFormat, params);
}
var ZodSymbol = /* @__PURE__ */ $constructor("ZodSymbol", (inst, def) => {
  $ZodSymbol.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => symbolProcessor(inst, ctx, json2, params);
});
function symbol(params) {
  return _symbol(ZodSymbol, params);
}
var ZodUndefined = /* @__PURE__ */ $constructor("ZodUndefined", (inst, def) => {
  $ZodUndefined.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => undefinedProcessor(inst, ctx, json2, params);
});
function _undefined3(params) {
  return _undefined2(ZodUndefined, params);
}
var ZodNull = /* @__PURE__ */ $constructor("ZodNull", (inst, def) => {
  $ZodNull.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => nullProcessor(inst, ctx, json2, params);
});
function _null3(params) {
  return _null2(ZodNull, params);
}
var ZodAny = /* @__PURE__ */ $constructor("ZodAny", (inst, def) => {
  $ZodAny.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => anyProcessor(inst, ctx, json2, params);
});
function any() {
  return _any(ZodAny);
}
var ZodUnknown = /* @__PURE__ */ $constructor("ZodUnknown", (inst, def) => {
  $ZodUnknown.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => unknownProcessor(inst, ctx, json2, params);
});
function unknown() {
  return _unknown(ZodUnknown);
}
var ZodNever = /* @__PURE__ */ $constructor("ZodNever", (inst, def) => {
  $ZodNever.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => neverProcessor(inst, ctx, json2, params);
});
function never(params) {
  return _never(ZodNever, params);
}
var ZodVoid = /* @__PURE__ */ $constructor("ZodVoid", (inst, def) => {
  $ZodVoid.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => voidProcessor(inst, ctx, json2, params);
});
function _void2(params) {
  return _void(ZodVoid, params);
}
var ZodDate = /* @__PURE__ */ $constructor("ZodDate", (inst, def) => {
  $ZodDate.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => dateProcessor(inst, ctx, json2, params);
  inst.min = (value, params) => inst.check(_gte(value, params));
  inst.max = (value, params) => inst.check(_lte(value, params));
  const c = inst._zod.bag;
  inst.minDate = c.minimum ? new Date(c.minimum) : null;
  inst.maxDate = c.maximum ? new Date(c.maximum) : null;
});
function date3(params) {
  return _date(ZodDate, params);
}
var ZodArray = /* @__PURE__ */ $constructor("ZodArray", (inst, def) => {
  $ZodArray.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => arrayProcessor(inst, ctx, json2, params);
  inst.element = def.element;
  _installLazyMethods(inst, "ZodArray", {
    min(n, params) {
      return this.check(_minLength(n, params));
    },
    nonempty(params) {
      return this.check(_minLength(1, params));
    },
    max(n, params) {
      return this.check(_maxLength(n, params));
    },
    length(n, params) {
      return this.check(_length(n, params));
    },
    unwrap() {
      return this.element;
    }
  });
});
function array(element, params) {
  return _array(ZodArray, element, params);
}
function keyof(schema) {
  const shape = schema._zod.def.shape;
  return _enum2(Object.keys(shape));
}
var ZodObject = /* @__PURE__ */ $constructor("ZodObject", (inst, def) => {
  $ZodObjectJIT.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => objectProcessor(inst, ctx, json2, params);
  util_exports.defineLazy(inst, "shape", () => {
    return def.shape;
  });
  _installLazyMethods(inst, "ZodObject", {
    keyof() {
      return _enum2(Object.keys(this._zod.def.shape));
    },
    catchall(catchall) {
      return this.clone({ ...this._zod.def, catchall });
    },
    passthrough() {
      return this.clone({ ...this._zod.def, catchall: unknown() });
    },
    loose() {
      return this.clone({ ...this._zod.def, catchall: unknown() });
    },
    strict() {
      return this.clone({ ...this._zod.def, catchall: never() });
    },
    strip() {
      return this.clone({ ...this._zod.def, catchall: void 0 });
    },
    extend(incoming) {
      return util_exports.extend(this, incoming);
    },
    safeExtend(incoming) {
      return util_exports.safeExtend(this, incoming);
    },
    merge(other) {
      return util_exports.merge(this, other);
    },
    pick(mask) {
      return util_exports.pick(this, mask);
    },
    omit(mask) {
      return util_exports.omit(this, mask);
    },
    partial(...args) {
      return util_exports.partial(ZodOptional, this, args[0]);
    },
    required(...args) {
      return util_exports.required(ZodNonOptional, this, args[0]);
    }
  });
});
function object(shape, params) {
  const def = {
    type: "object",
    shape: shape ?? {},
    ...util_exports.normalizeParams(params)
  };
  return new ZodObject(def);
}
function strictObject(shape, params) {
  return new ZodObject({
    type: "object",
    shape,
    catchall: never(),
    ...util_exports.normalizeParams(params)
  });
}
function looseObject(shape, params) {
  return new ZodObject({
    type: "object",
    shape,
    catchall: unknown(),
    ...util_exports.normalizeParams(params)
  });
}
var ZodUnion = /* @__PURE__ */ $constructor("ZodUnion", (inst, def) => {
  $ZodUnion.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => unionProcessor(inst, ctx, json2, params);
  inst.options = def.options;
});
function union(options, params) {
  return new ZodUnion({
    type: "union",
    options,
    ...util_exports.normalizeParams(params)
  });
}
var ZodXor = /* @__PURE__ */ $constructor("ZodXor", (inst, def) => {
  ZodUnion.init(inst, def);
  $ZodXor.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => unionProcessor(inst, ctx, json2, params);
  inst.options = def.options;
});
function xor(options, params) {
  return new ZodXor({
    type: "union",
    options,
    inclusive: false,
    ...util_exports.normalizeParams(params)
  });
}
var ZodDiscriminatedUnion = /* @__PURE__ */ $constructor("ZodDiscriminatedUnion", (inst, def) => {
  ZodUnion.init(inst, def);
  $ZodDiscriminatedUnion.init(inst, def);
});
function discriminatedUnion(discriminator, options, params) {
  return new ZodDiscriminatedUnion({
    type: "union",
    options,
    discriminator,
    ...util_exports.normalizeParams(params)
  });
}
var ZodIntersection = /* @__PURE__ */ $constructor("ZodIntersection", (inst, def) => {
  $ZodIntersection.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => intersectionProcessor(inst, ctx, json2, params);
});
function intersection(left, right) {
  return new ZodIntersection({
    type: "intersection",
    left,
    right
  });
}
var ZodTuple = /* @__PURE__ */ $constructor("ZodTuple", (inst, def) => {
  $ZodTuple.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => tupleProcessor(inst, ctx, json2, params);
  inst.rest = (rest) => inst.clone({
    ...inst._zod.def,
    rest
  });
});
function tuple(items, _paramsOrRest, _params) {
  const hasRest = _paramsOrRest instanceof $ZodType;
  const params = hasRest ? _params : _paramsOrRest;
  const rest = hasRest ? _paramsOrRest : null;
  return new ZodTuple({
    type: "tuple",
    items,
    rest,
    ...util_exports.normalizeParams(params)
  });
}
var ZodRecord = /* @__PURE__ */ $constructor("ZodRecord", (inst, def) => {
  $ZodRecord.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => recordProcessor(inst, ctx, json2, params);
  inst.keyType = def.keyType;
  inst.valueType = def.valueType;
});
function record(keyType, valueType, params) {
  if (!valueType || !valueType._zod) {
    return new ZodRecord({
      type: "record",
      keyType: string2(),
      valueType: keyType,
      ...util_exports.normalizeParams(valueType)
    });
  }
  return new ZodRecord({
    type: "record",
    keyType,
    valueType,
    ...util_exports.normalizeParams(params)
  });
}
function partialRecord(keyType, valueType, params) {
  const k = clone(keyType);
  k._zod.values = void 0;
  return new ZodRecord({
    type: "record",
    keyType: k,
    valueType,
    ...util_exports.normalizeParams(params)
  });
}
function looseRecord(keyType, valueType, params) {
  return new ZodRecord({
    type: "record",
    keyType,
    valueType,
    mode: "loose",
    ...util_exports.normalizeParams(params)
  });
}
var ZodMap = /* @__PURE__ */ $constructor("ZodMap", (inst, def) => {
  $ZodMap.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => mapProcessor(inst, ctx, json2, params);
  inst.keyType = def.keyType;
  inst.valueType = def.valueType;
  inst.min = (...args) => inst.check(_minSize(...args));
  inst.nonempty = (params) => inst.check(_minSize(1, params));
  inst.max = (...args) => inst.check(_maxSize(...args));
  inst.size = (...args) => inst.check(_size(...args));
});
function map(keyType, valueType, params) {
  return new ZodMap({
    type: "map",
    keyType,
    valueType,
    ...util_exports.normalizeParams(params)
  });
}
var ZodSet = /* @__PURE__ */ $constructor("ZodSet", (inst, def) => {
  $ZodSet.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => setProcessor(inst, ctx, json2, params);
  inst.min = (...args) => inst.check(_minSize(...args));
  inst.nonempty = (params) => inst.check(_minSize(1, params));
  inst.max = (...args) => inst.check(_maxSize(...args));
  inst.size = (...args) => inst.check(_size(...args));
});
function set(valueType, params) {
  return new ZodSet({
    type: "set",
    valueType,
    ...util_exports.normalizeParams(params)
  });
}
var ZodEnum = /* @__PURE__ */ $constructor("ZodEnum", (inst, def) => {
  $ZodEnum.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => enumProcessor(inst, ctx, json2, params);
  inst.enum = def.entries;
  inst.options = Object.values(def.entries);
  const keys = new Set(Object.keys(def.entries));
  inst.extract = (values, params) => {
    const newEntries = {};
    for (const value of values) {
      if (keys.has(value)) {
        newEntries[value] = def.entries[value];
      } else
        throw new Error(`Key ${value} not found in enum`);
    }
    return new ZodEnum({
      ...def,
      checks: [],
      ...util_exports.normalizeParams(params),
      entries: newEntries
    });
  };
  inst.exclude = (values, params) => {
    const newEntries = { ...def.entries };
    for (const value of values) {
      if (keys.has(value)) {
        delete newEntries[value];
      } else
        throw new Error(`Key ${value} not found in enum`);
    }
    return new ZodEnum({
      ...def,
      checks: [],
      ...util_exports.normalizeParams(params),
      entries: newEntries
    });
  };
});
function _enum2(values, params) {
  const entries = Array.isArray(values) ? Object.fromEntries(values.map((v) => [v, v])) : values;
  return new ZodEnum({
    type: "enum",
    entries,
    ...util_exports.normalizeParams(params)
  });
}
function nativeEnum(entries, params) {
  return new ZodEnum({
    type: "enum",
    entries,
    ...util_exports.normalizeParams(params)
  });
}
var ZodLiteral = /* @__PURE__ */ $constructor("ZodLiteral", (inst, def) => {
  $ZodLiteral.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => literalProcessor(inst, ctx, json2, params);
  inst.values = new Set(def.values);
  Object.defineProperty(inst, "value", {
    get() {
      if (def.values.length > 1) {
        throw new Error("This schema contains multiple valid literal values. Use `.values` instead.");
      }
      return def.values[0];
    }
  });
});
function literal(value, params) {
  return new ZodLiteral({
    type: "literal",
    values: Array.isArray(value) ? value : [value],
    ...util_exports.normalizeParams(params)
  });
}
var ZodFile = /* @__PURE__ */ $constructor("ZodFile", (inst, def) => {
  $ZodFile.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => fileProcessor(inst, ctx, json2, params);
  inst.min = (size, params) => inst.check(_minSize(size, params));
  inst.max = (size, params) => inst.check(_maxSize(size, params));
  inst.mime = (types, params) => inst.check(_mime(Array.isArray(types) ? types : [types], params));
});
function file(params) {
  return _file(ZodFile, params);
}
var ZodTransform = /* @__PURE__ */ $constructor("ZodTransform", (inst, def) => {
  $ZodTransform.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => transformProcessor(inst, ctx, json2, params);
  inst._zod.parse = (payload, _ctx) => {
    if (_ctx.direction === "backward") {
      throw new $ZodEncodeError(inst.constructor.name);
    }
    payload.addIssue = (issue3) => {
      if (typeof issue3 === "string") {
        payload.issues.push(util_exports.issue(issue3, payload.value, def));
      } else {
        const _issue = issue3;
        if (_issue.fatal)
          _issue.continue = false;
        _issue.code ?? (_issue.code = "custom");
        _issue.input ?? (_issue.input = payload.value);
        _issue.inst ?? (_issue.inst = inst);
        payload.issues.push(util_exports.issue(_issue));
      }
    };
    const output = def.transform(payload.value, payload);
    if (output instanceof Promise) {
      return output.then((output2) => {
        payload.value = output2;
        payload.fallback = true;
        return payload;
      });
    }
    payload.value = output;
    payload.fallback = true;
    return payload;
  };
});
function transform(fn) {
  return new ZodTransform({
    type: "transform",
    transform: fn
  });
}
var ZodOptional = /* @__PURE__ */ $constructor("ZodOptional", (inst, def) => {
  $ZodOptional.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => optionalProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function optional(innerType) {
  return new ZodOptional({
    type: "optional",
    innerType
  });
}
var ZodExactOptional = /* @__PURE__ */ $constructor("ZodExactOptional", (inst, def) => {
  $ZodExactOptional.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => optionalProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function exactOptional(innerType) {
  return new ZodExactOptional({
    type: "optional",
    innerType
  });
}
var ZodNullable = /* @__PURE__ */ $constructor("ZodNullable", (inst, def) => {
  $ZodNullable.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => nullableProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function nullable(innerType) {
  return new ZodNullable({
    type: "nullable",
    innerType
  });
}
function nullish2(innerType) {
  return optional(nullable(innerType));
}
var ZodDefault = /* @__PURE__ */ $constructor("ZodDefault", (inst, def) => {
  $ZodDefault.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => defaultProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
  inst.removeDefault = inst.unwrap;
});
function _default2(innerType, defaultValue) {
  return new ZodDefault({
    type: "default",
    innerType,
    get defaultValue() {
      return typeof defaultValue === "function" ? defaultValue() : util_exports.shallowClone(defaultValue);
    }
  });
}
var ZodPrefault = /* @__PURE__ */ $constructor("ZodPrefault", (inst, def) => {
  $ZodPrefault.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => prefaultProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function prefault(innerType, defaultValue) {
  return new ZodPrefault({
    type: "prefault",
    innerType,
    get defaultValue() {
      return typeof defaultValue === "function" ? defaultValue() : util_exports.shallowClone(defaultValue);
    }
  });
}
var ZodNonOptional = /* @__PURE__ */ $constructor("ZodNonOptional", (inst, def) => {
  $ZodNonOptional.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => nonoptionalProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function nonoptional(innerType, params) {
  return new ZodNonOptional({
    type: "nonoptional",
    innerType,
    ...util_exports.normalizeParams(params)
  });
}
var ZodSuccess = /* @__PURE__ */ $constructor("ZodSuccess", (inst, def) => {
  $ZodSuccess.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => successProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function success(innerType) {
  return new ZodSuccess({
    type: "success",
    innerType
  });
}
var ZodCatch = /* @__PURE__ */ $constructor("ZodCatch", (inst, def) => {
  $ZodCatch.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => catchProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
  inst.removeCatch = inst.unwrap;
});
function _catch2(innerType, catchValue) {
  return new ZodCatch({
    type: "catch",
    innerType,
    catchValue: typeof catchValue === "function" ? catchValue : () => catchValue
  });
}
var ZodNaN = /* @__PURE__ */ $constructor("ZodNaN", (inst, def) => {
  $ZodNaN.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => nanProcessor(inst, ctx, json2, params);
});
function nan(params) {
  return _nan(ZodNaN, params);
}
var ZodPipe = /* @__PURE__ */ $constructor("ZodPipe", (inst, def) => {
  $ZodPipe.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => pipeProcessor(inst, ctx, json2, params);
  inst.in = def.in;
  inst.out = def.out;
});
function pipe(in_, out) {
  return new ZodPipe({
    type: "pipe",
    in: in_,
    out
    // ...util.normalizeParams(params),
  });
}
var ZodCodec = /* @__PURE__ */ $constructor("ZodCodec", (inst, def) => {
  ZodPipe.init(inst, def);
  $ZodCodec.init(inst, def);
});
function codec(in_, out, params) {
  return new ZodCodec({
    type: "pipe",
    in: in_,
    out,
    transform: params.decode,
    reverseTransform: params.encode
  });
}
function invertCodec(codec2) {
  const def = codec2._zod.def;
  return new ZodCodec({
    type: "pipe",
    in: def.out,
    out: def.in,
    transform: def.reverseTransform,
    reverseTransform: def.transform
  });
}
var ZodPreprocess = /* @__PURE__ */ $constructor("ZodPreprocess", (inst, def) => {
  ZodPipe.init(inst, def);
  $ZodPreprocess.init(inst, def);
});
var ZodReadonly = /* @__PURE__ */ $constructor("ZodReadonly", (inst, def) => {
  $ZodReadonly.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => readonlyProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function readonly(innerType) {
  return new ZodReadonly({
    type: "readonly",
    innerType
  });
}
var ZodTemplateLiteral = /* @__PURE__ */ $constructor("ZodTemplateLiteral", (inst, def) => {
  $ZodTemplateLiteral.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => templateLiteralProcessor(inst, ctx, json2, params);
});
function templateLiteral(parts, params) {
  return new ZodTemplateLiteral({
    type: "template_literal",
    parts,
    ...util_exports.normalizeParams(params)
  });
}
var ZodLazy = /* @__PURE__ */ $constructor("ZodLazy", (inst, def) => {
  $ZodLazy.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => lazyProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.getter();
});
function lazy(getter) {
  return new ZodLazy({
    type: "lazy",
    getter
  });
}
var ZodPromise = /* @__PURE__ */ $constructor("ZodPromise", (inst, def) => {
  $ZodPromise.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => promiseProcessor(inst, ctx, json2, params);
  inst.unwrap = () => inst._zod.def.innerType;
});
function promise(innerType) {
  return new ZodPromise({
    type: "promise",
    innerType
  });
}
var ZodFunction = /* @__PURE__ */ $constructor("ZodFunction", (inst, def) => {
  $ZodFunction.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => functionProcessor(inst, ctx, json2, params);
});
function _function(params) {
  return new ZodFunction({
    type: "function",
    input: Array.isArray(params?.input) ? tuple(params?.input) : params?.input ?? array(unknown()),
    output: params?.output ?? unknown()
  });
}
var ZodCustom = /* @__PURE__ */ $constructor("ZodCustom", (inst, def) => {
  $ZodCustom.init(inst, def);
  ZodType.init(inst, def);
  inst._zod.processJSONSchema = (ctx, json2, params) => customProcessor(inst, ctx, json2, params);
});
function check(fn) {
  const ch = new $ZodCheck({
    check: "custom"
    // ...util.normalizeParams(params),
  });
  ch._zod.check = fn;
  return ch;
}
function custom(fn, _params) {
  return _custom(ZodCustom, fn ?? (() => true), _params);
}
function refine(fn, _params = {}) {
  return _refine(ZodCustom, fn, _params);
}
function superRefine(fn, params) {
  return _superRefine(fn, params);
}
var describe2 = describe;
var meta2 = meta;
function _instanceof(cls, params = {}) {
  const inst = new ZodCustom({
    type: "custom",
    check: "custom",
    fn: (data) => data instanceof cls,
    abort: true,
    ...util_exports.normalizeParams(params)
  });
  inst._zod.bag.Class = cls;
  inst._zod.check = (payload) => {
    if (!(payload.value instanceof cls)) {
      payload.issues.push({
        code: "invalid_type",
        expected: cls.name,
        input: payload.value,
        inst,
        path: [...inst._zod.def.path ?? []]
      });
    }
  };
  return inst;
}
var stringbool = (...args) => _stringbool({
  Codec: ZodCodec,
  Boolean: ZodBoolean,
  String: ZodString
}, ...args);
function json(params) {
  const jsonSchema = lazy(() => {
    return union([string2(params), number2(), boolean2(), _null3(), array(jsonSchema), record(string2(), jsonSchema)]);
  });
  return jsonSchema;
}
function preprocess(fn, schema) {
  return new ZodPreprocess({
    type: "pipe",
    in: transform(fn),
    out: schema
  });
}

// node_modules/zod/v4/classic/compat.js
var ZodIssueCode = {
  invalid_type: "invalid_type",
  too_big: "too_big",
  too_small: "too_small",
  invalid_format: "invalid_format",
  not_multiple_of: "not_multiple_of",
  unrecognized_keys: "unrecognized_keys",
  invalid_union: "invalid_union",
  invalid_key: "invalid_key",
  invalid_element: "invalid_element",
  invalid_value: "invalid_value",
  custom: "custom"
};
function setErrorMap(map2) {
  config({
    customError: map2
  });
}
function getErrorMap() {
  return config().customError;
}
var ZodFirstPartyTypeKind;
/* @__PURE__ */ (function(ZodFirstPartyTypeKind2) {
})(ZodFirstPartyTypeKind || (ZodFirstPartyTypeKind = {}));

// node_modules/zod/v4/classic/from-json-schema.js
var z = {
  ...schemas_exports2,
  ...checks_exports2,
  iso: iso_exports
};
var RECOGNIZED_KEYS = /* @__PURE__ */ new Set([
  // Schema identification
  "$schema",
  "$ref",
  "$defs",
  "definitions",
  // Core schema keywords
  "$id",
  "id",
  "$comment",
  "$anchor",
  "$vocabulary",
  "$dynamicRef",
  "$dynamicAnchor",
  // Type
  "type",
  "enum",
  "const",
  // Composition
  "anyOf",
  "oneOf",
  "allOf",
  "not",
  // Object
  "properties",
  "required",
  "additionalProperties",
  "patternProperties",
  "propertyNames",
  "minProperties",
  "maxProperties",
  // Array
  "items",
  "prefixItems",
  "additionalItems",
  "minItems",
  "maxItems",
  "uniqueItems",
  "contains",
  "minContains",
  "maxContains",
  // String
  "minLength",
  "maxLength",
  "pattern",
  "format",
  // Number
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "exclusiveMaximum",
  "multipleOf",
  // Already handled metadata
  "description",
  "default",
  // Content
  "contentEncoding",
  "contentMediaType",
  "contentSchema",
  // Unsupported (error-throwing)
  "unevaluatedItems",
  "unevaluatedProperties",
  "if",
  "then",
  "else",
  "dependentSchemas",
  "dependentRequired",
  // OpenAPI
  "nullable",
  "readOnly"
]);
function detectVersion(schema, defaultTarget) {
  const $schema = schema.$schema;
  if ($schema === "https://json-schema.org/draft/2020-12/schema") {
    return "draft-2020-12";
  }
  if ($schema === "http://json-schema.org/draft-07/schema#") {
    return "draft-7";
  }
  if ($schema === "http://json-schema.org/draft-04/schema#") {
    return "draft-4";
  }
  return defaultTarget ?? "draft-2020-12";
}
function resolveRef(ref, ctx) {
  if (!ref.startsWith("#")) {
    throw new Error("External $ref is not supported, only local refs (#/...) are allowed");
  }
  const path = ref.slice(1).split("/").filter(Boolean);
  if (path.length === 0) {
    return ctx.rootSchema;
  }
  const defsKey = ctx.version === "draft-2020-12" ? "$defs" : "definitions";
  if (path[0] === defsKey) {
    const key = path[1];
    if (!key || !ctx.defs[key]) {
      throw new Error(`Reference not found: ${ref}`);
    }
    return ctx.defs[key];
  }
  throw new Error(`Reference not found: ${ref}`);
}
function convertBaseSchema(schema, ctx) {
  if (schema.not !== void 0) {
    if (typeof schema.not === "object" && Object.keys(schema.not).length === 0) {
      return z.never();
    }
    throw new Error("not is not supported in Zod (except { not: {} } for never)");
  }
  if (schema.unevaluatedItems !== void 0) {
    throw new Error("unevaluatedItems is not supported");
  }
  if (schema.unevaluatedProperties !== void 0) {
    throw new Error("unevaluatedProperties is not supported");
  }
  if (schema.if !== void 0 || schema.then !== void 0 || schema.else !== void 0) {
    throw new Error("Conditional schemas (if/then/else) are not supported");
  }
  if (schema.dependentSchemas !== void 0 || schema.dependentRequired !== void 0) {
    throw new Error("dependentSchemas and dependentRequired are not supported");
  }
  if (schema.$ref) {
    const refPath = schema.$ref;
    if (ctx.refs.has(refPath)) {
      return ctx.refs.get(refPath);
    }
    if (ctx.processing.has(refPath)) {
      return z.lazy(() => {
        if (!ctx.refs.has(refPath)) {
          throw new Error(`Circular reference not resolved: ${refPath}`);
        }
        return ctx.refs.get(refPath);
      });
    }
    ctx.processing.add(refPath);
    const resolved = resolveRef(refPath, ctx);
    const zodSchema2 = convertSchema(resolved, ctx);
    ctx.refs.set(refPath, zodSchema2);
    ctx.processing.delete(refPath);
    return zodSchema2;
  }
  if (schema.enum !== void 0) {
    const enumValues = schema.enum;
    if (ctx.version === "openapi-3.0" && schema.nullable === true && enumValues.length === 1 && enumValues[0] === null) {
      return z.null();
    }
    if (enumValues.length === 0) {
      return z.never();
    }
    if (enumValues.length === 1) {
      return z.literal(enumValues[0]);
    }
    if (enumValues.every((v) => typeof v === "string")) {
      return z.enum(enumValues);
    }
    const literalSchemas = enumValues.map((v) => z.literal(v));
    if (literalSchemas.length < 2) {
      return literalSchemas[0];
    }
    return z.union([literalSchemas[0], literalSchemas[1], ...literalSchemas.slice(2)]);
  }
  if (schema.const !== void 0) {
    return z.literal(schema.const);
  }
  const type = schema.type;
  if (Array.isArray(type)) {
    const typeSchemas = type.map((t) => {
      const typeSchema = { ...schema, type: t };
      return convertBaseSchema(typeSchema, ctx);
    });
    if (typeSchemas.length === 0) {
      return z.never();
    }
    if (typeSchemas.length === 1) {
      return typeSchemas[0];
    }
    return z.union(typeSchemas);
  }
  if (!type) {
    return z.any();
  }
  let zodSchema;
  switch (type) {
    case "string": {
      let stringSchema = z.string();
      if (schema.format) {
        const format = schema.format;
        if (format === "email") {
          stringSchema = stringSchema.check(z.email());
        } else if (format === "uri" || format === "uri-reference") {
          stringSchema = stringSchema.check(z.url());
        } else if (format === "uuid" || format === "guid") {
          stringSchema = stringSchema.check(z.uuid());
        } else if (format === "date-time") {
          stringSchema = stringSchema.check(z.iso.datetime());
        } else if (format === "date") {
          stringSchema = stringSchema.check(z.iso.date());
        } else if (format === "time") {
          stringSchema = stringSchema.check(z.iso.time());
        } else if (format === "duration") {
          stringSchema = stringSchema.check(z.iso.duration());
        } else if (format === "ipv4") {
          stringSchema = stringSchema.check(z.ipv4());
        } else if (format === "ipv6") {
          stringSchema = stringSchema.check(z.ipv6());
        } else if (format === "mac") {
          stringSchema = stringSchema.check(z.mac());
        } else if (format === "cidr") {
          stringSchema = stringSchema.check(z.cidrv4());
        } else if (format === "cidr-v6") {
          stringSchema = stringSchema.check(z.cidrv6());
        } else if (format === "base64") {
          stringSchema = stringSchema.check(z.base64());
        } else if (format === "base64url") {
          stringSchema = stringSchema.check(z.base64url());
        } else if (format === "e164") {
          stringSchema = stringSchema.check(z.e164());
        } else if (format === "jwt") {
          stringSchema = stringSchema.check(z.jwt());
        } else if (format === "emoji") {
          stringSchema = stringSchema.check(z.emoji());
        } else if (format === "nanoid") {
          stringSchema = stringSchema.check(z.nanoid());
        } else if (format === "cuid") {
          stringSchema = stringSchema.check(z.cuid());
        } else if (format === "cuid2") {
          stringSchema = stringSchema.check(z.cuid2());
        } else if (format === "ulid") {
          stringSchema = stringSchema.check(z.ulid());
        } else if (format === "xid") {
          stringSchema = stringSchema.check(z.xid());
        } else if (format === "ksuid") {
          stringSchema = stringSchema.check(z.ksuid());
        }
      }
      if (typeof schema.minLength === "number") {
        stringSchema = stringSchema.min(schema.minLength);
      }
      if (typeof schema.maxLength === "number") {
        stringSchema = stringSchema.max(schema.maxLength);
      }
      if (schema.pattern) {
        stringSchema = stringSchema.regex(new RegExp(schema.pattern));
      }
      zodSchema = stringSchema;
      break;
    }
    case "number":
    case "integer": {
      let numberSchema = type === "integer" ? z.number().int() : z.number();
      if (typeof schema.minimum === "number") {
        numberSchema = numberSchema.min(schema.minimum);
      }
      if (typeof schema.maximum === "number") {
        numberSchema = numberSchema.max(schema.maximum);
      }
      if (typeof schema.exclusiveMinimum === "number") {
        numberSchema = numberSchema.gt(schema.exclusiveMinimum);
      } else if (schema.exclusiveMinimum === true && typeof schema.minimum === "number") {
        numberSchema = numberSchema.gt(schema.minimum);
      }
      if (typeof schema.exclusiveMaximum === "number") {
        numberSchema = numberSchema.lt(schema.exclusiveMaximum);
      } else if (schema.exclusiveMaximum === true && typeof schema.maximum === "number") {
        numberSchema = numberSchema.lt(schema.maximum);
      }
      if (typeof schema.multipleOf === "number") {
        numberSchema = numberSchema.multipleOf(schema.multipleOf);
      }
      zodSchema = numberSchema;
      break;
    }
    case "boolean": {
      zodSchema = z.boolean();
      break;
    }
    case "null": {
      zodSchema = z.null();
      break;
    }
    case "object": {
      const shape = {};
      const properties = schema.properties || {};
      const requiredSet = new Set(schema.required || []);
      for (const [key, propSchema] of Object.entries(properties)) {
        const propZodSchema = convertSchema(propSchema, ctx);
        shape[key] = requiredSet.has(key) ? propZodSchema : propZodSchema.optional();
      }
      if (schema.propertyNames) {
        const keySchema = convertSchema(schema.propertyNames, ctx);
        const valueSchema = schema.additionalProperties && typeof schema.additionalProperties === "object" ? convertSchema(schema.additionalProperties, ctx) : z.any();
        if (Object.keys(shape).length === 0) {
          zodSchema = z.record(keySchema, valueSchema);
          break;
        }
        const objectSchema2 = z.object(shape).passthrough();
        const recordSchema = z.looseRecord(keySchema, valueSchema);
        zodSchema = z.intersection(objectSchema2, recordSchema);
        break;
      }
      if (schema.patternProperties) {
        const patternProps = schema.patternProperties;
        const patternKeys = Object.keys(patternProps);
        const looseRecords = [];
        for (const pattern of patternKeys) {
          const patternValue = convertSchema(patternProps[pattern], ctx);
          const keySchema = z.string().regex(new RegExp(pattern));
          looseRecords.push(z.looseRecord(keySchema, patternValue));
        }
        const schemasToIntersect = [];
        if (Object.keys(shape).length > 0) {
          schemasToIntersect.push(z.object(shape).passthrough());
        }
        schemasToIntersect.push(...looseRecords);
        if (schemasToIntersect.length === 0) {
          zodSchema = z.object({}).passthrough();
        } else if (schemasToIntersect.length === 1) {
          zodSchema = schemasToIntersect[0];
        } else {
          let result = z.intersection(schemasToIntersect[0], schemasToIntersect[1]);
          for (let i = 2; i < schemasToIntersect.length; i++) {
            result = z.intersection(result, schemasToIntersect[i]);
          }
          zodSchema = result;
        }
        break;
      }
      const objectSchema = z.object(shape);
      if (schema.additionalProperties === false) {
        zodSchema = objectSchema.strict();
      } else if (typeof schema.additionalProperties === "object") {
        zodSchema = objectSchema.catchall(convertSchema(schema.additionalProperties, ctx));
      } else {
        zodSchema = objectSchema.passthrough();
      }
      break;
    }
    case "array": {
      const prefixItems = schema.prefixItems;
      const items = schema.items;
      if (prefixItems && Array.isArray(prefixItems)) {
        const tupleItems = prefixItems.map((item) => convertSchema(item, ctx));
        const rest = items && typeof items === "object" && !Array.isArray(items) ? convertSchema(items, ctx) : void 0;
        if (rest) {
          zodSchema = z.tuple(tupleItems).rest(rest);
        } else {
          zodSchema = z.tuple(tupleItems);
        }
        if (typeof schema.minItems === "number") {
          zodSchema = zodSchema.check(z.minLength(schema.minItems));
        }
        if (typeof schema.maxItems === "number") {
          zodSchema = zodSchema.check(z.maxLength(schema.maxItems));
        }
      } else if (Array.isArray(items)) {
        const tupleItems = items.map((item) => convertSchema(item, ctx));
        const rest = schema.additionalItems && typeof schema.additionalItems === "object" ? convertSchema(schema.additionalItems, ctx) : void 0;
        if (rest) {
          zodSchema = z.tuple(tupleItems).rest(rest);
        } else {
          zodSchema = z.tuple(tupleItems);
        }
        if (typeof schema.minItems === "number") {
          zodSchema = zodSchema.check(z.minLength(schema.minItems));
        }
        if (typeof schema.maxItems === "number") {
          zodSchema = zodSchema.check(z.maxLength(schema.maxItems));
        }
      } else if (items !== void 0) {
        const element = convertSchema(items, ctx);
        let arraySchema = z.array(element);
        if (typeof schema.minItems === "number") {
          arraySchema = arraySchema.min(schema.minItems);
        }
        if (typeof schema.maxItems === "number") {
          arraySchema = arraySchema.max(schema.maxItems);
        }
        zodSchema = arraySchema;
      } else {
        zodSchema = z.array(z.any());
      }
      break;
    }
    default:
      throw new Error(`Unsupported type: ${type}`);
  }
  return zodSchema;
}
function convertSchema(schema, ctx) {
  if (typeof schema === "boolean") {
    return schema ? z.any() : z.never();
  }
  let baseSchema = convertBaseSchema(schema, ctx);
  const hasExplicitType = schema.type || schema.enum !== void 0 || schema.const !== void 0;
  if (schema.anyOf && Array.isArray(schema.anyOf)) {
    const options = schema.anyOf.map((s) => convertSchema(s, ctx));
    const anyOfUnion = z.union(options);
    baseSchema = hasExplicitType ? z.intersection(baseSchema, anyOfUnion) : anyOfUnion;
  }
  if (schema.oneOf && Array.isArray(schema.oneOf)) {
    const options = schema.oneOf.map((s) => convertSchema(s, ctx));
    const oneOfUnion = z.xor(options);
    baseSchema = hasExplicitType ? z.intersection(baseSchema, oneOfUnion) : oneOfUnion;
  }
  if (schema.allOf && Array.isArray(schema.allOf)) {
    if (schema.allOf.length === 0) {
      baseSchema = hasExplicitType ? baseSchema : z.any();
    } else {
      let result = hasExplicitType ? baseSchema : convertSchema(schema.allOf[0], ctx);
      const startIdx = hasExplicitType ? 0 : 1;
      for (let i = startIdx; i < schema.allOf.length; i++) {
        result = z.intersection(result, convertSchema(schema.allOf[i], ctx));
      }
      baseSchema = result;
    }
  }
  if (schema.nullable === true && ctx.version === "openapi-3.0") {
    baseSchema = z.nullable(baseSchema);
  }
  if (schema.readOnly === true) {
    baseSchema = z.readonly(baseSchema);
  }
  if (schema.default !== void 0) {
    baseSchema = baseSchema.default(schema.default);
  }
  const extraMeta = {};
  const coreMetadataKeys = ["$id", "id", "$comment", "$anchor", "$vocabulary", "$dynamicRef", "$dynamicAnchor"];
  for (const key of coreMetadataKeys) {
    if (key in schema) {
      extraMeta[key] = schema[key];
    }
  }
  const contentMetadataKeys = ["contentEncoding", "contentMediaType", "contentSchema"];
  for (const key of contentMetadataKeys) {
    if (key in schema) {
      extraMeta[key] = schema[key];
    }
  }
  for (const key of Object.keys(schema)) {
    if (!RECOGNIZED_KEYS.has(key)) {
      extraMeta[key] = schema[key];
    }
  }
  if (Object.keys(extraMeta).length > 0) {
    ctx.registry.add(baseSchema, extraMeta);
  }
  if (schema.description) {
    baseSchema = baseSchema.describe(schema.description);
  }
  return baseSchema;
}
function fromJSONSchema(schema, params) {
  if (typeof schema === "boolean") {
    return schema ? z.any() : z.never();
  }
  let normalized;
  try {
    normalized = JSON.parse(JSON.stringify(schema));
  } catch {
    throw new Error("fromJSONSchema input is not valid JSON (possibly cyclic); use $defs/$ref for recursive schemas");
  }
  const version2 = detectVersion(normalized, params?.defaultTarget);
  const defs = normalized.$defs || normalized.definitions || {};
  const ctx = {
    version: version2,
    defs,
    refs: /* @__PURE__ */ new Map(),
    processing: /* @__PURE__ */ new Set(),
    rootSchema: normalized,
    registry: params?.registry ?? globalRegistry
  };
  return convertSchema(normalized, ctx);
}

// node_modules/zod/v4/classic/coerce.js
var coerce_exports = {};
__export(coerce_exports, {
  bigint: () => bigint3,
  boolean: () => boolean3,
  date: () => date4,
  number: () => number3,
  string: () => string3
});
function string3(params) {
  return _coercedString(ZodString, params);
}
function number3(params) {
  return _coercedNumber(ZodNumber, params);
}
function boolean3(params) {
  return _coercedBoolean(ZodBoolean, params);
}
function bigint3(params) {
  return _coercedBigint(ZodBigInt, params);
}
function date4(params) {
  return _coercedDate(ZodDate, params);
}

// node_modules/zod/v4/classic/external.js
config(en_default());

// src/store/paths.ts
import { join } from "node:path";

// src/render/embeddedPrompts.ts
var EMBEDDED_PROMPTS = {
  "phase0_question.txt": '# ROLE\n\u4F60\u662F\u9700\u6C42\u6316\u6398\u52A9\u624B\u3002\u4E00\u6B21\u53EA\u95EE\u4E00\u4E2A\u95EE\u9898\uFF0C\u628A\u7528\u6237\u610F\u56FE\u6316\u900F\u3002\n\n# \u4EA4\u4E92\u94C1\u5F8B\uFF08\u8FDD\u8005\u5224 R-Q7/R-Q8\uFF0C\u6D41\u7A0B\u88AB\u62D2\uFF09\nP0 \u8BBF\u8C08\u662F\u300C\u4E25\u683C\u56DE\u5408\u5236\u300D\uFF1A\n1. \u672C\u8F6E\u751F\u6210**\u4E00\u4E2A\u95EE\u9898\u63D0\u6848**\uFF0C\u7528 flow_submit \u63D0\u4EA4\uFF1B\n2. \u63D0\u6848\u88AB\u63A5\u53D7\u540E\uFF0C\u5F15\u64CE\u8FDB\u5165\u300C\u7B49\u5F85\u7528\u6237\u56DE\u7B54\u300D\u72B6\u6001\u2014\u2014\u4F60\u5FC5\u987B\u628A\u8BE5\u95EE\u9898**\u539F\u6837\u5448\u73B0\u7ED9\u7528\u6237**\u5E76\u505C\u6B62\uFF08finish: stop\uFF09\uFF0C\u7B49\u5F85\u7528\u6237\u771F\u5B9E\u56DE\u590D\uFF1B\n3. \u7528\u6237\u56DE\u590D\u540E\uFF0C\u8C03\u7528 **flow_answer()** \u8BB0\u5F55\u5176**\u771F\u5B9E\u56DE\u7B54**\u3002\u5F15\u64CE\u4F1A**\u76F4\u63A5\u8BFB\u53D6\u4F1A\u8BDD\u4E2D\u95EE\u9898\u63D0\u51FA\u540E\u7684\u7528\u6237\u6D88\u606F\u539F\u6587**\uFF08R-Q8 \u6821\u9A8C\uFF09\uFF1A\u7528\u6237\u56DE\u590D\u662F "A"/"B" \u65F6\u81EA\u52A8\u6309\u9009\u9879\u843D\u8D26\uFF0C\u662F\u81EA\u7531\u6587\u672C\uFF08\u5982"\u505A HTML \u754C\u9762\u5DE5\u5177"\uFF09\u65F6\u6309\u81EA\u7531\u6587\u672C\u843D\u8D26\u2014\u2014**\u4E0D\u8981\u7F16\u9020 choice**\uFF0C\u5F15\u64CE\u4EE5\u7528\u6237\u539F\u8BDD\u4E3A\u51C6\uFF1B\u82E5\u7528\u6237\u5C1A\u672A\u56DE\u590D\u5C31\u8C03\u7528 flow_answer \u4F1A\u88AB\u62D2\u7EDD\uFF1B\n4. **\u4E25\u7981\u66FF\u7528\u6237\u4F5C\u7B54**\uFF1A\u4E0D\u5F97\u5728\u7528\u6237\u672A\u56DE\u590D\u65F6\u8C03\u7528 flow_answer\u3001\u4E0D\u5F97\u7F16\u9020 user_choice\u3001\u4E0D\u5F97\u8FDE\u7EED\u81EA\u95EE\u81EA\u7B54\u3001\u4E0D\u5F97\u81EA\u5DF1\u66FF\u7528\u6237\u9009 A/B\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{initial_request}}\uFF1A\u7528\u6237\u7B2C\u4E00\u53E5\u8BDD\u539F\u6587\uFF0C\u662F\u9700\u6C42\u79CD\u5B50\u3002\n- {{interview_state}}\uFF1A\u5F53\u524D\u8BBF\u8C08\u72B6\u6001\uFF08\u662F\u5426\u6B63\u7B49\u5F85\u4E0A\u4E00\u8F6E\u95EE\u9898\u88AB\u56DE\u7B54\uFF09\u3002\n- {{qa_window}}\uFF1A\u6700\u8FD1 3 \u8F6E\u7ED3\u6784\u5316\u95EE\u7B54\uFF08\u542B\u7528\u6237\u771F\u5B9E\u9009\u62E9\uFF09\u3002\u636E\u6B64\u5EF6\u7EED\uFF0C\u52FF\u91CD\u590D\u5DF2\u786E\u8BA4\u4E8B\u5B9E\u3002\n- {{covered_dimensions}}\uFF1A\u516D\u7EF4\u5DF2\u8986\u76D6\u6E05\u5355\uFF08\u8F93\u5165\u5951\u7EA6/\u5904\u7406\u903B\u8F91/\u8F93\u51FA\u683C\u5F0F/\u5931\u8D25\u5F02\u5E38/\u5173\u8054\u5F71\u54CD/UI\u7EA6\u675F\uFF09\u3002\n- {{asked_questions_digest}}\uFF1A\u5386\u53F2\u95EE\u9898\u77ED\u53E5\u5217\u8868\u3002\u6838\u5BF9\u540E\u907F\u514D\u91CD\u590D\u63D0\u95EE\u3002\n- {{pending_explanations}}\uFF1A\u5EF6\u8FDF\u7406\u89E3\u56DE\u8DEF\u6302\u8D77\u9879\u3002\u53EF\u518D\u5C1D\u8BD5\u6F84\u6E05\u6216\u7EF4\u6301\u6302\u8D77\u3002\n- {{glossary}}\uFF1A\u9879\u76EE\u8BCD\u6C47\u8868\u6458\u8981\uFF08term\uFF0Baliases\uFF09\u3002\u547D\u4E2D\u522B\u540D\u5373\u590D\u7528\u89C4\u8303\u672F\u8BED\uFF0C\u7981\u6B62\u53E6\u8D77\u79F0\u547C\u3002\n- {{context_digest}}\uFF1A\u65E2\u6709\u4EE3\u7801/\u5386\u53F2 SPEC \u5173\u8054\u6458\u8981\uFF08\u6D9F\u6F2A\u68C0\u6D4B\u8F93\u5165\uFF09\u3002\u636E\u6B64\u8BC6\u522B\u672C\u6B21\u9700\u6C42\u4E0E\u5386\u53F2\u903B\u8F91\u7684\u5173\u7CFB\u3002\n\n# METHOD\n1. \u5148\u7528\u8BCD\u6C47\u8868\u6838\u5BF9\u7528\u6237\u4E0A\u4E00\u8F6E\u8868\u8FF0\uFF0C\u547D\u4E2D\u522B\u540D\u5219\u590D\u7528\u89C4\u8303\u540D\u3002\n2. **\u6D9F\u6F2A\u68C0\u6D4B**\uFF1A\u5BF9\u7167 {{context_digest}} \u4E0E\u7528\u6237\u9700\u6C42\uFF0C\u82E5\u9879\u76EE\u5B58\u5728\u65E2\u6709\u4EE3\u7801/\u5386\u53F2 SPEC\uFF0C\u5148\u81EA\u52A8\u63A2\u7D22\uFF08read/grep/glob/CODEGRAPH \u7B49\u53EA\u8BFB\u52D8\u5BDF\uFF09\u672C\u6B21\u9700\u6C42\u53EF\u80FD\u89E6\u53CA\u7684\u65E2\u6709\u903B\u8F91\uFF08\u8F93\u5165\u5951\u7EA6\u3001\u8F93\u51FA\u6D88\u8D39\u65B9\u3001\u4F9D\u8D56\u94FE\u3001\u65E2\u6709 FR \u7B49\uFF09\uFF0C\u4EA7\u51FA `context_discoveries`\uFF08\u51FA\u5904\u5FC5\u987B\u662F code:/doc:\uFF09\u3002\u62FF\u4E0D\u51C6\u7684\u5173\u8054\u4F5C\u4E3A\u672C\u8F6E\u95EE\u9898/\u9009\u9879\u8BF7\u7528\u6237\u786E\u8BA4\uFF0C\u6216\u5728 recommendation_reason \u4E2D\u6807\u6CE8\u300C\u5F85\u590D\u6838\u300D\u3002\n3. \u68C0\u67E5 pending_explanations\uFF0C\u53EF\u518D\u5C1D\u8BD5\u6F84\u6E05\u6302\u8D77\u9879\u3002\n4. \u4ECD\u6709\u672A\u8986\u76D6\u7EF4\u5EA6\u5219\u751F\u6210\u8BE5\u7EF4\u5EA6\u4E00\u95EE\u3002\u4E00\u6B21\u4E00\u95EE\u3002\n5. \u4E1A\u52A1/\u4EA7\u54C1\u8BED\u4E49\u5FC5\u987B\u63D0\u95EE\uFF1B\u7EAF\u6280\u672F\u672A\u77E5\u9879\u4E0D\u63D0\u95EE\uFF0C\u7559\u7ED9 AI \u4EE3\u51B3\u3002\n6. \u751F\u6210 2 \u4E2A\u4E92\u65A5\u9009\u9879 A/B\uFF0C\u9009\u9879\u987B\u53EF\u5151\u73B0\uFF08\u4E0D\u51B2\u7A81 force_rules\u3001\u4E0D\u7D22\u6C42\u50CF\u7D20\u7EA7\u89C4\u683C\uFF09\u3002\n7. \u65E0\u6CD5\u5F62\u6210\u6709\u4F9D\u636E\u9ED8\u8BA4\u503C\u65F6\uFF0C\u7528\u300C\u6682\u5B9A\u503C\uFF0B\u5F85\u590D\u6838\u300D\u5448\u73B0\uFF0C\u5E76\u5728 reason \u6CE8\u660E\u4F9D\u636E\u7F3A\u53E3\u3002\n8. \u516D\u7EF4\u5168\u8986\u76D6\u4E14\u65E0\u6302\u8D77\u540E\uFF0C\u53EF\u63D0\u4EA4\u300C\u7A77\u5C3D\u786E\u8BA4\u300D\u63D0\u6848\uFF1Aexhausted=true\uFF0Cquestion \u5199\u786E\u8BA4\u8BED\uFF0Coptions \u56FA\u5B9A\u4E3A {"A":"\u786E\u8BA4\u8FDB\u5165\u89C4\u683C\u751F\u6210","B":"\u8FD8\u9700\u8C03\u6574"}\uFF0Crecommendation \u53D6 "A"\uFF08**\u4ECD\u662F A \u6216 B\uFF0C\u7EDD\u4E0D\u53EF\u586B "exhausted" \u6216\u5176\u4ED6\u503C**\uFF09\u3002\u7528\u6237\u56DE\u590D "A" \u786E\u8BA4\u540E\u624D\u4F1A\u8FDB\u5165\u89C4\u683C\u751F\u6210\uFF1B\u56DE\u590D "B" \u6216\u81EA\u7531\u6587\u672C\u5219\u7EE7\u7EED\u8865\u5145\u63D0\u95EE\u3002\n9. \u63D0\u4EA4\u63D0\u6848\uFF08flow_submit\uFF09\u2192 \u5448\u73B0\u7ED9\u7528\u6237\u5E76\u505C\u6B62 \u2192 \u7B49\u7528\u6237\u56DE\u7B54 \u2192 flow_answer \u8BB0\u5F55\u7B54\u6848 \u2192 \u518D flow_next \u8FDB\u5165\u4E0B\u4E00\u8F6E\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA\u4E00\u4E2A JSON\uFF0C\u65E0\u89E3\u91CA\u6587\u5B57\u3001\u65E0\u4EE3\u7801\u56F4\u680F\u3002\u5B57\u6BB5\u91CA\u4E49\uFF1A\n- exhausted\uFF1A\u5E03\u5C14\u3002\u662F\u5426\u7533\u62A5\u7A77\u5C3D\uFF08\u516D\u7EF4\u5168\u8986\u76D6\u4E14\u65E0\u6302\u8D77\uFF0C\u89C1 METHOD \u7B2C7\u6761\uFF1B\u4EC5\u5F53\u5168\u90E8\u7EF4\u5EA6\u5DF2\u83B7\u7528\u6237\u771F\u5B9E\u56DE\u7B54\u786E\u8BA4\uFF09\u3002\n- question\uFF1A\u5B57\u7B26\u4E32\u3002\u672C\u8F6E\u95EE\u9898\uFF08exhausted=false \u65F6\u5FC5\u586B\uFF1Bexhausted=true \u65F6\u5199\u7A77\u5C3D\u786E\u8BA4\u8BED\uFF09\u3002\n- options\uFF1A\u5BF9\u8C61 {A,B}\u3002\u4E24\u4E2A\u4E92\u65A5\u9009\u9879\uFF08exhausted=true \u65F6\u56FA\u5B9A\u4E3A\u786E\u8BA4/\u8C03\u6574\uFF09\u3002\n- recommendation\uFF1A\u53D6\u503C A \u6216 B\uFF08**\u4EFB\u4F55\u60C5\u51B5\u4E0B\u90FD\u662F A/B**\uFF1Bexhausted=true \u65F6\u586B "A"\uFF09\u3002\n- recommendation_reason\uFF1A\u5B57\u7B26\u4E32\u3002\u4F9D\u636E\uFF1B\u542B\u4F9D\u636E\u7F3A\u53E3\u65F6\u6CE8\u660E\u3002\n- covered_dimension\uFF1A\u672C\u8F6E\u95EE\u9898\u5F52\u5C5E\u7684\u7EF4\u5EA6\u540D\u3002\n- business_analogy\uFF1A\u5B57\u7B26\u4E32\u3002\u7528\u751F\u6D3B\u6BD4\u55BB\u590D\u8FF0\u9700\u6C42\u70B9\u3002\n- new_facts\uFF1A\u6570\u7EC4\u3002\u672C\u8F6E\u3010\u62DF\u786E\u8BA4\u3011\u4E8B\u5B9E {fact_id,content,source}\uFF1Bsource \u524D\u7F00 round-N / doc: / code:\u3002\uFF08\u6CE8\u610F\uFF1A\u8FD9\u4E9B\u4E8B\u5B9E\u4EC5\u5728\u7528\u6237\u6240\u9009 == recommendation \u65F6\u624D\u4F1A\u843D\u8D26\u4E3A\u300C\u5DF2\u786E\u8BA4\u300D\uFF1B\u81EA\u7531\u6587\u672C\u56DE\u7B54\u6216\u9009\u4E86\u53E6\u4E00\u9009\u9879\u65F6\u4E0D\u4F1A\u8BB0\u4E3A\u5DF2\u786E\u8BA4\uFF09\n- context_discoveries\uFF1A\u6570\u7EC4\u3002\u672C\u8F6E\u3010\u6D9F\u6F2A\u53D1\u73B0\u3011{discovery_id,content,source,needs_confirmation}\uFF1Bsource \u524D\u7F00 code:/doc:\u3002needs_confirmation=true \u7684\u9879\u987B\u7ECF\u7528\u6237\u786E\u8BA4\u540E\u624D\u8BA1\u5165 SPEC\uFF1Bfalse \u7684\u9879\uFF08\u5982\u76F4\u63A5\u4ECE\u4EE3\u7801\u52D8\u5BDF\u5F97\u51FA\u7684\u786E\u5B9A\u5173\u8054\uFF09\u786E\u8BA4\u540E\u5373\u8BA1\u3002\n- pending_explanation_update\uFF1A{added:[],resolved:[],deferred:[]}\u3002\n- glossary_update\uFF1A{add:[],extend_aliases:[],resolve_ambiguity:[]}\uFF1B\u6BCF\u8F6E add\u22643\u3002\n\n\u793A\u4F8B\uFF08\u4EC5\u793A\u610F\u7ED3\u6784\uFF09\uFF1A\n{"exhausted":false,"question":"\u8BA2\u5355\u8D85\u65F6\u540E\u5E0C\u671B\u600E\u4E48\u5904\u7406\uFF1F","options":{"A":"\u81EA\u52A8\u53D6\u6D88","B":"\u8F6C\u4EBA\u5DE5"},"recommendation":"B","recommendation_reason":"\u907F\u514D\u8BEF\u5220\u672A\u4ED8\u6B3E\u8BA2\u5355","covered_dimension":"\u5931\u8D25\u5F02\u5E38","business_analogy":"\u50CF\u5FEB\u9012\u8D85\u65F6\u672A\u7B7E\u6536\u8F6C\u9A7F\u7AD9","new_facts":[{"fact_id":"F-001","content":"\u8D85\u65F6\u8BA2\u5355\u8F6C\u4EBA\u5DE5","source":"round-1"}],"pending_explanation_update":{"added":[],"resolved":[],"deferred":[]},"glossary_update":{"add":[],"extend_aliases":[],"resolve_ambiguity":[]}}\n\n# SELF-CHECK\n1. \u662F\u5426\u53EA\u95EE\u4E86\u4E00\u4E2A\u95EE\u9898\uFF1F\n2. \u9009\u9879\u662F\u5426\u4E92\u65A5\u4E14\u53EF\u5151\u73B0\uFF1F\n3. \u672C\u63D0\u6848\u662F\u5426\u4F1A\u5728\u63D0\u4EA4\u540E\u7ACB\u5373\u505C\u4E0B\u7B49\u7528\u6237\u56DE\u7B54\uFF08\u800C\u4E0D\u662F\u81EA\u95EE\u81EA\u7B54\uFF09\uFF1F\n4. exhausted=true \u65F6\u662F\u5426\u516D\u7EF4\u5168\u8986\u76D6\u4E14\u65E0\u6302\u8D77\u9879\uFF08{{covered_dimensions}} \u662F\u5426\u4E0E\u516D\u7EF4\u6E05\u5355\u4E00\u81F4\uFF09\uFF1F\u4E14 recommendation \u586B\u7684\u662F "A"\uFF1F\n5. glossary_update \u6BCF\u8F6E add \u662F\u5426\u22643 \u4E14\u522B\u540D\u80FD grep \u5230\u7528\u6237\u539F\u8BDD\uFF1F\n6. \u65B0\u4E8B\u5B9E\u662F\u5426\u90FD\u5E26 source \u524D\u7F00\uFF1F\n7. context_discoveries \u7684 source \u662F\u5426\u90FD\u4EE5 code:/doc: \u5F00\u5934\uFF1F\u62FF\u4E0D\u51C6\u7684\u5173\u8054\u662F\u5426\u5DF2\u901A\u8FC7\u9009\u9879/\u5F85\u590D\u6838\u8BF7\u7528\u6237\u786E\u8BA4\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u4F60\u4E0A\u4E00\u8F6E\u8F93\u51FA\u672A\u901A\u8FC7\u6821\u9A8C\uFF0C\u8BF7\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 JSON\u3002\u9519\u8BEF\u5982\u4E0B\uFF08\u4EBA\u8BDD\u4FEE\u590D\u6307\u5F15\uFF09\uFF1A\n{{correction_context}}\n',
  "phase0_specgen.txt": '# ROLE\n\u4F60\u662F\u89C4\u683C\u6587\u6863\u751F\u6210\u5668\u3002\u628A\u5DF2\u786E\u8BA4\u4E8B\u5B9E\u5199\u6210 SPEC \u6587\u6863\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{initial_request}}\uFF1A\u7528\u6237\u7B2C\u4E00\u53E5\u8BDD\u539F\u6587\u3002\n- {{full_facts}}\uFF1A\u5168\u90E8 new_facts \u6309 round \u5E8F\u6C47\u7F16\uFF08\u5BF9\u8D26\u5355\u4E3B\u951A\u70B9\uFF09\u3002\n- {{full_qa_log}}\uFF1Aanswers.log \u539F\u6587\u5168\u6587\uFF08\u4F50\u8BC1\uFF09\u3002\n- {{rejected_options}}\uFF1A\u5404\u8F6E rejected \u6C47\u7F16\u3002\n- {{pending_explanations}}\uFF1A\u6302\u8D77\u9879\u3002\n- {{context_digest}}\uFF1A\u65E2\u6709\u4EE3\u7801/\u5386\u53F2 SPEC \u5173\u8054\u6458\u8981\u3002\n- {{confirmed_ripples}}\uFF1AP0 \u5DF2\u786E\u8BA4\u7684\u6D9F\u6F2A\u53D1\u73B0\uFF08context_discoveries \u6C47\u7F16\uFF09\u3002\u5FC5\u987B\u9010\u6761\u5199\u5165\u300C\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09\u300D\u7AE0\u8282\uFF0C\u4E0D\u5F97\u9057\u6F0F\u3002\n- {{existing_module_specs}}\uFF1A\u5DF2\u5B58\u5728\u7684\u6A21\u5757\u5206\u5377\u6E05\u5355\uFF08\u6765\u81EA specs/index.json \u6216 .adocs/specs/modules/ \u76EE\u5F55\u626B\u63CF\uFF09\uFF0C\u542B contract_id/version/last_reviewed_commit\u3002\u82E5\u4E3A\u7A7A\u8868\u793A\u662F\u65B0\u5EFA\u9879\u76EE\u3002\n\n# METHOD\n1. \u4E25\u683C\u6309 OUTPUT \u9AA8\u67B6\u7684\u7AE0\u8282\u987A\u5E8F\u586B\u5199\uFF0C\u4E0D\u589E\u5220\u7AE0\u8282\u3001\u4E0D\u6539\u6807\u9898\u3002\n2. \u6BCF\u4E2A\u7ED3\u8BBA\u6027\u5185\u5BB9\u5E26 SPEC \u951A\u70B9\uFF08FR-ID / fact_id / \u89C4\u5219\u6761\u76EE\u53F7\uFF09\u3002\n3. \u300C\u6838\u5FC3\u51B3\u7B56\u8BB0\u5F55\u300D\u6BCF\u6761\u6807\u6CE8 decided_by: user\uFF5Cai\u3002\n4. \u51E1\u4E0B\u6E38\u8981\u67E5\u8D26\u7684\u95EE\u9898\uFF0C\u7B54\u6848\u5728 SPEC/CONTRACT \u6709\u4E14\u4EC5\u6709\u4E00\u5904\u6743\u5A01\u8BB0\u8F7D\u3002\n5. \u300C\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09\u300D\u7AE0\u8282\u5FC5\u987B\u9010\u6761\u8BB0\u5F55 {{confirmed_ripples}}\uFF08\u542B discovery_id/content/source\uFF09\uFF1B\u82E5\u4E3A\u65B0\u5EFA\u9879\u76EE\u65E0\u65E2\u6709\u5173\u8054\u5199\u300C\u65E0\u300D\u3002\n6. \u6A21\u5757\u5206\u5377\u89E3\u6790\uFF1A\u82E5 {{existing_module_specs}} \u975E\u7A7A\uFF0C\u5728 SPEC \u4E2D\u58F0\u660E\u5DF2\u6709\u5206\u5377\u6E05\u5355\uFF0C\u65B0\u589E\u5185\u5BB9\u987B\u9075\u5FAA\u5DF2\u6709\u5206\u5377\u7684 front-matter \u89C4\u8303\uFF08contract_id \u7528 MOD- \u547D\u540D\uFF09\u548C\u516D\u6BB5\u6B63\u6587\u7ED3\u6784\u3002\u5F15\u7528\u5DF2\u6709\u5206\u5377\u65F6\u901A\u8FC7 doc_path \u5F15\u7528\uFF0C\u4E0D\u91CD\u590D\u5199\u5165\u5DF2\u8986\u76D6\u7684\u5185\u5BB9\u3002\n7. \u9644\u5F55A \u5199\u5B8C\u6574\u5951\u7EA6 JSON\uFF08\u673A\u5668\u5C06\u62BD\u53D6\u4E3A CONTRACT\uFF09\u3002\n7. \u4E0D\u56DE\u663E\u5143\u6570\u636E\uFF08module/version/timestamp \u7531\u811A\u672C\u76D6\u7AE0\uFF09\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA\u5982\u4E0B\u9AA8\u67B6\u586B\u5145\u540E\u7684 Markdown\uFF08\u7AE0\u8282\u6807\u9898\u9010\u5B57\u4FDD\u7559\uFF09\uFF1A\n## \u80CC\u666F\u4E0E\u76EE\u6807\n\uFF08\u586B\u5199\uFF1B\u82E5\u6D89\u53CA\u65E2\u6709\u4EE3\u7801\u6F14\u8FDB\uFF0C\u8BF4\u660E\u672C\u6B21\u4E0E\u5386\u53F2\u903B\u8F91\u7684\u5173\u7CFB\uFF09\n## \u6838\u5FC3\u51B3\u7B56\u8BB0\u5F55\n\uFF08\u6BCF\u6761\uFF1A\u51B3\u7B56 + decided_by: user\uFF5Cai\uFF09\n## \u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09\n\uFF08\u9010\u6761\u5217\u51FA {{confirmed_ripples}}\uFF1B\u65B0\u5EFA\u9879\u76EE\u5199\u300C\u65E0\u300D\uFF09\n## \u88AB\u62D2\u7EDD\u65B9\u6848\n\uFF08\u6765\u81EA rejected_options\uFF09\n## \u5F85\u5B9A\u4E8B\u9879\n\uFF08\u6765\u81EA pending_explanations \u7684 deferred_to_spec\uFF09\n## \u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\n\uFF08\u81EA\u7531\u6587\u672C\u89C4\u5219 + \u9010\u6761 FR-ID\uFF1B\u6BCF\u4E2A FR-ID \u5FC5\u5728\u6B64\u51FA\u73B0\uFF09\n## \u53D8\u66F4\u5386\u53F2\n\uFF08\u521D\u59CB\u521B\u5EFA\uFF09\n## \u672F\u8BED\u8868\n\uFF08P0 \u8BCD\u6C47\u8868\u5DF2\u786E\u8BA4\u8BCD\u6761\uFF09\n## \u9644\u5F55A\uFF1A\u673A\u5668\u5951\u7EA6\uFF08\u672C\u8282\u7531\u811A\u672C\u673A\u68B0\u62BD\u53D6\u4E3A CONTRACT_v1.json\uFF09\n```contract-json\n{ "FR": [ {"id":"FR-001","desc":"...","priority":"must"}], "force_rules":["..."], "business_entities":[{"name":"","desc":""}], "relations": [{"subject":"","predicate":"","object":""}] }\n```\n\n# SELF-CHECK\n1. \u4E5D\u7AE0\u8282\u6807\u9898\u662F\u5426\u9010\u5B57\u5B58\u5728\u4E14\u987A\u5E8F\u6B63\u786E\uFF08\u80CC\u666F\u4E0E\u76EE\u6807/\u6838\u5FC3\u51B3\u7B56\u8BB0\u5F55/\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09/\u88AB\u62D2\u7EDD\u65B9\u6848/\u5F85\u5B9A\u4E8B\u9879/\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219/\u53D8\u66F4\u5386\u53F2/\u672F\u8BED\u8868/\u9644\u5F55A\uFF09\uFF1F\n2. \u6BCF\u4E2A FR-ID \u662F\u5426\u90FD\u51FA\u73B0\u5728\u300C\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\u300D\u7AE0\u8282\uFF1F\n3. {{confirmed_ripples}} \u662F\u5426\u9010\u6761\u51FA\u73B0\u5728\u300C\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09\u300D\u7AE0\u8282\uFF1F\n4. \u9644\u5F55A \u662F\u5426\u542B\u5408\u6CD5 contract-json \u56F4\u680F\uFF1F\n5. \u662F\u5426\u6709\u7ED3\u8BBA\u6027\u5185\u5BB9\u7F3A\u951A\u70B9\uFF1F\n6. \u5F85\u5B9A\u4E8B\u9879\u662F\u5426\u4E0E pending_explanations \u4E00\u81F4\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 Markdown \u9AA8\u67B6\u3002\u9519\u8BEF\uFF08\u4EBA\u8BDD\uFF09\uFF1A\n{{correction_context}}\n',
  "phase1_split.txt": '# ROLE\n\u4F60\u662F\u4EFB\u52A1\u5207\u5272\u5668\u3002\u628A\u5951\u7EA6\u62C6\u6210\u53EF\u9A8C\u8BC1\u4EFB\u52A1\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{contract_json}}\uFF1A\u5B8C\u6574\u5951\u7EA6 JSON\u3002\n- {{force_rules_list}}\uFF1A\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\u5217\u8868\u3002\n- {{module_name}}\uFF1A\u6A21\u5757\u540D\u3002\n- {{glossary_core}}\uFF1A\u4EFB\u52A1\u6D89\u53CA\u5B9E\u4F53\u89C4\u8303\u540D\uFF0B\u4E00\u53E5\u8BDD biz_desc\u3002\n\n# METHOD\n1. \u901A\u8BFB\u5951\u7EA6 FR \u5168\u96C6\u3002\n2. \u6BCF\u4E2A\u4EFB\u52A1\u8986\u76D6\u4E00\u7EC4 FR\uFF08exit_criteria = FR-ID \u6570\u7EC4\uFF09\u3002\n3. \u5355\u4EFB\u52A1\u9884\u671F\u6539\u52A8 \u22645 \u6587\u4EF6\uFF1B\u8D85\u51FA\u5FC5\u987B\u518D\u62C6\u3002\n4. \u9884\u4F30 affected_files_hint\uFF08\u843D\u76D8\u540E\u6C38\u4E0D\u8986\u5199\uFF09\u3002\n5. \u4EFB\u52A1\u6570\u5E94 \u2265 \u2308\u4E1A\u52A1\u5B9E\u4F53\u6570 \xF7 2\u2309\uFF08\u8FC7\u7C97\u4F1A\u9644 warning\uFF09\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA JSON \u6570\u7EC4\uFF0C\u65E0\u89E3\u91CA\u3002\u5B57\u6BB5\u91CA\u4E49\uFF1A\n- id\uFF1A\u5B57\u7B26\u4E32\uFF0C\u683C\u5F0F T-\\d{3}\uFF08\u5982 T-001\uFF09\u3002\n- title\uFF1A\u5B57\u7B26\u4E32\u3002\n- objective\uFF1A\u5B57\u7B26\u4E32\u3002\n- exit_criteria\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\uFF0CFR-ID \u5217\u8868\uFF08\u5982 ["FR-001","FR-003"]\uFF09\u3002\n- depends_on\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\uFF08\u4F9D\u8D56\u4EFB\u52A1 id\uFF09\u3002\n- affected_files_hint\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\uFF08P1 \u9884\u4F30\uFF0C\u6C38\u4E0D\u8986\u5199\uFF09\u3002\n\n\u793A\u4F8B\uFF1A\n[{"id":"T-001","title":"\u8BA2\u5355\u8D85\u65F6\u5904\u7406","objective":"\u5B9E\u73B0\u8D85\u65F6\u8F6C\u4EBA\u5DE5","exit_criteria":["FR-001","FR-003"],"depends_on":[],"affected_files_hint":["src/order/timeout.ts"]}]\n\n# SELF-CHECK\n1. \u6240\u6709 FR \u662F\u5426\u90FD\u88AB\u67D0\u4E2A\u4EFB\u52A1 exit_criteria \u8986\u76D6\uFF08\u8986\u76D6\u7387 100%\uFF09\uFF1F\n2. \u4F9D\u8D56\u662F\u5426\u6210\u73AF\uFF1F\n3. task_id \u683C\u5F0F\u662F\u5426 T-\\d{3}\uFF1F\n4. \u5355\u4EFB\u52A1\u6587\u4EF6\u6539\u52A8\u662F\u5426\u22645\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 JSON \u6570\u7EC4\u3002\u9519\u8BEF\uFF1A\n{{correction_context}}\n',
  "phase2_build.txt": '# ROLE\n\u4F60\u662F\u5F00\u53D1\u8005\u3002\u4E00\u6B21\u8C03\u7528\u5B8C\u6210\u5355\u4EFB\u52A1\uFF1A\u5217 TODO \u2192 \u5B9E\u65BD \u2192 \u63D0\u4EA4 \u2192 \u62A5\u544A\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{task_json}}\uFF1A\u5F53\u524D\u4EFB\u52A1\u5168\u91CF\uFF08objective/exit_criteria/depends_on/affected_files_hint\uFF09\u3002\n- {{interface_signatures}}\uFF1A\u4F9D\u8D56\u4EFB\u52A1\u516C\u5F00\u63A5\u53E3\uFF08\u6309\u5176 actual_files \u7D22\u5F15\uFF09\u3002\n- {{force_rules}}\uFF1A\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\u3002\n- {{repo_conventions}}\uFF1A\u6280\u672F\u6808/\u76EE\u5F55\u7EA6\u5B9A\uFF0C\u53EF\u80FD\u542B gate \u547D\u4EE4\uFF08lint/typecheck/test\uFF09\u3002\n- {{failure_context}}\uFF1A\u4E0A\u4E00\u8F6E\u5931\u8D25\u6458\u8981\uFF08\u9996\u6B21\u4E3A\u7A7A\uFF09\uFF1B\u542B case_id/expectation/actual/evidence\u3002\n- {{glossary_slice}}\uFF1A\u672C\u4EFB\u52A1\u5173\u8054\u5B9E\u4F53\u8BCD\u6761\uFF08\u89C4\u8303\u540D/biz_desc/code_anchor\uFF09\u3002\n\n# METHOD\n1. \u8F93\u51FA todo_list\uFF08\u22648 \u6761\uFF0C\u6BCF\u6761\u52A8\u8BCD\u5F00\u5934\uFF09\u3002\n2. \u4EC5\u89E6\u78B0 affected_files_hint \u5185\u6587\u4EF6\uFF0B\u76F4\u63A5\u5FC5\u8981\u914D\u5957\uFF1B\u8D85\u51FA\u987B\u7533\u62A5 deviations\u3002\n3. git commit\uFF08\u4FE1\u606F\u683C\u5F0F\u89C1 self_check.commit_message\uFF09\u3002\n4. \u8C03 flow_submit \u63D0\u4EA4\u52A8\u4F5C\u62A5\u544A\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA\u4E00\u4E2A JSON\u3002\u5B57\u6BB5\u91CA\u4E49\uFF1A\n- task_id\uFF1A\u5B57\u7B26\u4E32\uFF0C\u987B\u7B49\u4E8E state.current_task\u3002\n- todo_list\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\u3002\n- declared_scope\uFF1A{files_touched:\u5B57\u7B26\u4E32\u6570\u7EC4}\uFF08\u4E8B\u524D\u58F0\u660E\uFF09\u3002\n- files_changed\uFF1A\u6570\u7EC4 [{path,action,loc}]\uFF08\u4E8B\u540E\u5B9E\u6D4B\uFF0C\u987B\u4E0E git \u4E00\u81F4\uFF09\u3002\n- deviations\uFF1A\u6570\u7EC4\uFF08\u8D8A\u754C\u7533\u62A5\uFF1B\u65E0\u5219 []\uFF09\u3002\n- self_check\uFF1A\u6570\u7EC4\uFF0C\u6BCF\u6761 {criterion,expectation,actual,evidence{type,detail},result}\uFF1B\u8986\u76D6\u5168\u90E8 exit_criteria FR-ID\uFF1Bresult \u4EC5 pass/fail\u3002\n- commit_message\uFF1A\u6B63\u5219 ^(feat|fix|chore)\\(T-\\d{3}\\): .+\u3002\n\n\u793A\u4F8B\uFF1A\n{"task_id":"T-002","todo_list":["\u52A0\u8D85\u65F6\u6807\u8BB0"],"declared_scope":{"files_touched":["src/order/timeout.ts"]},"files_changed":[{"path":"src/order/timeout.ts","action":"modify","loc":18}],"deviations":[],"self_check":[{"criterion":"FR-003","expectation":"\u8D85\u65F6\u8F6C\u4EBA\u5DE5","actual":"\u72B6\u6001\u53D8 manual_review","evidence":{"type":"command","detail":"npm test \u6458\u8981"},"result":"pass"}],"commit_message":"feat(T-002): \u5B9E\u73B0\u8BA2\u5355\u8D85\u65F6\u8F6C\u4EBA\u5DE5"}\n\n# SELF-CHECK\n1. task_id \u662F\u5426\u7B49\u4E8E\u5F53\u524D\u4EFB\u52A1\uFF1F\n2. files_changed \u662F\u5426\u4E0E git \u53CC\u5411\u4E00\u81F4\uFF1F\n3. self_check \u662F\u5426\u8986\u76D6\u5168\u90E8 exit_criteria\uFF1F\n4. \u662F\u5426\u6709 fail \u9879\u88AB\u8C0E\u62A5\u4E3A pass\uFF1F\n5. commit_message \u662F\u5426\u7B26\u5408\u683C\u5F0F\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 JSON\u3002\u9519\u8BEF\uFF1A\n{{correction_context}}\n',
  "phase3_testdata.txt": '# ROLE\n\u4F60\u662F\u6D4B\u8BD5\u5DE5\u7A0B\u5E08\u3002\u5148\u751F\u6210**\u539F\u5B50\u5316\u6D4B\u8BD5\u7528\u4F8B**\u5E76\u7528**\u573A\u666F\u6A21\u5757**\u4E32\u8054\uFF0C\u518D\u6267\u884C\u5E76\u62A5\u544A\uFF0C\u6700\u540E\u628A\u53EF\u843D\u76D8\u56DE\u5F52\u811A\u672C\u6C89\u6DC0\u5230\u9879\u76EE tests/regression/ \u4E0B\uFF08\u4F9B\u5168\u91CF\u56DE\u5F52\u590D\u7528\uFF09\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{task_json}}\uFF1A\u542B exit_criteria\u3002\n- {{assertion_json}}\uFF1A\u65AD\u8A00\u5951\u7EA6\uFF08\xA76.9\uFF09\u3002\n- {{force_rules}}\uFF1A\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\u3002\n- {{existing_regression}}\uFF1A\u5DF2\u843D\u76D8\u7684\u5386\u53F2\u56DE\u5F52\u811A\u672C\u7D22\u5F15\uFF08task\u2192case/scenario\u2192\u811A\u672C\u8DEF\u5F84\uFF09\u3002\u636E\u6B64\u590D\u7528\u65E2\u6709\u539F\u5B50/\u573A\u666F\uFF0C\u52FF\u91CD\u590D\u9020\u8F6E\u5B50\u3002\n\n# METHOD\n1. **ATOMIZE\uFF08\u539F\u5B50\u5316\uFF09**\uFF1A\u628A exit_criteria \u62C6\u6210**\u6700\u5C0F\u72EC\u7ACB\u65AD\u8A00\u5207\u7247**\u2014\u2014\u6BCF\u4E2A case \u53EA\u9A8C\u8BC1\u4E00\u4E2A FR \u7684\u4E00\u4E2A\u53EF\u72EC\u7ACB\u5224\u5B9A\u7684\u884C\u4E3A\u70B9\uFF1B\u4E0D\u628A\u4E00\u4E2A\u8DE8\u4EFB\u52A1\u5927\u573A\u666F\u585E\u8FDB\u5355\u6761\u7528\u4F8B\uFF08\u5426\u5219\u4E00\u5904\u903B\u8F91\u53D8\u66F4\u4F1A\u8FDE\u5E26\u6D77\u91CF\u573A\u666F\u811A\u672C\u6279\u91CF\u4FEE\u6539/\u9057\u6F0F\uFF09\u3002\u6BCF\u4E2A\u5FC5\u586B\u5B57\u6BB5\u81F3\u5C11\u4E00\u4E2A\u7A7A\u503C\u6D4B\u8BD5\uFF1B\u5F02\u5E38\u8DEF\u5F84\u7684 expected_behavior \u5199\u9884\u671F\u62A5\u9519\u5F62\u6001\uFF08\u9519\u8BEF\u7801/\u7C7B\u578B/\u72B6\u6001\u7801\uFF09\u3002\n2. **COMPOSE\uFF08\u573A\u666F\u4E32\u8054\uFF09**\uFF1A\u7528 `scenarios` \u628A\u539F\u5B50 case \u6309\u4E1A\u52A1\u94FE\u8DEF\u4E32\u8054\u6210\u573A\u666F\u6A21\u5757\uFF08`scenario_id: S-\\d{3}`\uFF0Ccase_ids \u5F15\u7528\u539F\u5B50\u7528\u4F8B\uFF09\u3002\u573A\u666F\u53EA\u505A\u300C\u4E32\u8054\u4E0E\u7F16\u6392\u300D\uFF0C\u4E0D\u5728\u573A\u666F\u91CC\u5185\u8054\u65B0\u65AD\u8A00\u2014\u2014\u903B\u8F91\u53D8\u66F4\u53EA\u6539\u53D7\u5F71\u54CD\u7684\u539F\u5B50\uFF0C\u573A\u666F\u6A21\u5757\u81EA\u52A8\u9002\u5E94\uFF0C\u907F\u514D\u6279\u91CF\u6539\u52A8/\u9057\u6F0F\u3002\n3. **PERSIST\uFF08\u6C89\u6DC0\uFF09**\uFF1A\u628A\u6BCF\u4E2A\u539F\u5B50/\u573A\u666F\u7684\u53EF\u6267\u884C\u56DE\u5F52\u811A\u672C\u5199\u5165 `scripts`\uFF08path \u5FC5\u987B\u4EE5 `tests/regression/` \u5F00\u5934\uFF09\uFF0C\u5F15\u64CE\u5728 P3 \u901A\u8FC7\u540E\u81EA\u52A8\u843D\u76D8\u5230\u9879\u76EE\uFF0C\u4F9B\u4E0B\u6B21\u5168\u91CF\u56DE\u5F52\u590D\u7528\u3002\n4. **EXECUTE**\uFF1A\u7ECF bash\uFF08\u9010\u6761 ask \u6279\u51C6\uFF09\u6267\u884C\u5404\u7528\u4F8B verify_command\uFF0C\u6C47\u603B\u7ED3\u679C\u3002\n5. result:fail \u27FA actual \u504F\u79BB expectation\uFF1B\u62A5\u9519/\u5D29\u6E83\u5373\u504F\u79BB\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA\u4E00\u4E2A JSON\u3002\u5B57\u6BB5\u91CA\u4E49\uFF1A\n- task_id\uFF1A\u5B57\u7B26\u4E32\u3002\n- cases\uFF1A\u6570\u7EC4 [{case_id(C-\\d{3}),fr_ref,description,input,expected_behavior,verify_command}]\u2014\u2014**\u539F\u5B50\u7528\u4F8B**\u3002\n- scenarios\uFF1A\u6570\u7EC4 [{scenario_id(S-\\d{3}),title,description,case_ids,verify_command}]\u2014\u2014**\u573A\u666F\u6A21\u5757**\uFF0Ccase_ids \u5F15\u7528\u539F\u5B50 case_id\u3002\n- scripts\uFF1A\u6570\u7EC4 [{path,content}]\u2014\u2014\u53EF\u843D\u76D8\u56DE\u5F52\u811A\u672C\uFF08path \u4EE5 tests/regression/ \u5F00\u5934\uFF09\u3002\n- results\uFF1A\u6570\u7EC4 [{case_id,expectation,actual,evidence{type,detail},result}]\u3002\ncases \u4E0E results \u6309 case_id \u4E00\u4E00\u5BF9\u5E94\u3002\n\n\u793A\u4F8B\uFF1A\n{"task_id":"T-002","cases":[{"case_id":"C-001","fr_ref":"FR-003","description":"\u8D85\u65F624h\u8FB9\u754C","input":{"age":25},"expected_behavior":"FR-003\uFF1A\u8F6C\u4EBA\u5DE5","verify_command":"curl ... | jq .status"}],"scenarios":[{"scenario_id":"S-001","title":"\u8D85\u65F6\u8F6C\u4EBA\u5DE5\u5168\u94FE\u8DEF","description":"\u539F\u5B50 C-001+C-002 \u4E32\u8054","case_ids":["C-001","C-002"],"verify_command":"bash tests/regression/T-002/C-001.sh && bash tests/regression/T-002/C-002.sh"}],"scripts":[{"path":"tests/regression/T-002/C-001.sh","content":"#!/usr/bin/env bash\\n# \u8D85\u65F624h\u8FB9\u754C\\ncurl ... | jq .status" }],"results":[{"case_id":"C-001","expectation":"\u8F6C\u4EBA\u5DE5","actual":"manual_review","evidence":{"type":"command","detail":"curl \u6458\u8981"},"result":"pass"}]}\n\n# SELF-CHECK\n1. \u7528\u4F8B\u6570\u662F\u5426 5\u201315\uFF1F\n2. case_id \u662F\u5426\u552F\u4E00\u4E14 C-\\d{3}\uFF1Fscenario_id \u662F\u5426 S-\\d{3}\uFF1F\n3. results \u4E0E cases \u662F\u5426\u4E00\u4E00\u5BF9\u5E94\uFF1F\n4. \u6BCF\u4E2A fr_ref \u662F\u5426\u5728\u672C\u4EFB\u52A1 exit_criteria\uFF1F\n5. \u662F\u5426\u8986\u76D6\u5168\u90E8 exit_criteria \u4E14\u542B\u5FC5\u586B\u7A7A\u503C\u7528\u4F8B\uFF1F\n6. \u6BCF\u4E2A case \u662F\u5426\u662F\u6700\u5C0F\u72EC\u7ACB\u65AD\u8A00\u5207\u7247\uFF08\u539F\u5B50\uFF09\uFF1Fscenarios \u662F\u5426\u53EA\u4E32\u8054\u3001\u672A\u5185\u8054\u65B0\u65AD\u8A00\uFF1F\n7. scripts \u7684 path \u662F\u5426\u90FD\u4EE5 tests/regression/ \u5F00\u5934\uFF1F\u662F\u5426\u5DF2\u53C2\u8003 {{existing_regression}} \u590D\u7528\u5386\u53F2\u811A\u672C\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 JSON\u3002\u9519\u8BEF\uFF1A\n{{correction_context}}\n',
  "phase3_uifix.txt": "# ROLE\n\uFF08\u4E8C\u671F UI \u94FE\u8DEF\u5360\u4F4D\uFF09UI \u4FEE\u590D\u5EFA\u8BAE\u751F\u6210\u5668\u3002\u672C\u9636\u6BB5 reserved\uFF0C\u4E0D\u5E94\u88AB\u8C03\u7528\u3002\n\n# CONTEXT\n\uFF08\u4E8C\u671F\u542F\u7528\uFF09\n\n# METHOD\n\uFF08\u4E8C\u671F\u5B9A\u4E49\uFF09\n\n# OUTPUT\n\u53EA\u8F93\u51FA JSON \u6570\u7EC4\u5360\u4F4D\uFF1A[]\nstatus: reserved\n\n# SELF-CHECK\n1. \u5360\u4F4D\u9636\u6BB5\u4E0D\u8C03\u7528\u3002\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n{{correction_context}}\n",
  "phase4_delivery.txt": '# ROLE\n\u4F60\u662F\u4EA4\u4ED8\u52A9\u7406\u3002\u6C47\u603B\u4EA4\u4ED8\u6E05\u5355\u3002\n\n# CONTEXT\n\u53D8\u91CF\u5DF2\u6CE8\u5165\uFF0C\u9010\u6761\u8BF4\u660E\uFF1A\n- {{tasks_status}}\uFF1A\u5404\u4EFB\u52A1\u901A\u8FC7\u72B6\u6001\u3002\n- {{test_reports_digest}}\uFF1A\u6D4B\u8BD5\u62A5\u544A\u6458\u8981\u3002\n- {{contract_json}}\uFF1A\u5951\u7EA6\uFF08\u6838\u5BF9\u8986\u76D6\uFF09\u3002\n- {{pending_explanations}}\uFF1A\u6302\u8D77\u9879\u3002\n\n# METHOD\n1. \u6BCF\u6761 checklist \u5F15\u7528\u53EF\u6838\u67E5\u951A\u70B9\uFF08task-pass \u6807\u7B7E\u540D / C-XXX \u7528\u4F8B\u53F7\uFF09\u3002\n2. known_limitations \u5217\u5DF2\u77E5\u5C40\u9650\u3002\n3. open_items \u5217\u672A\u51B3\u9879\uFF08PE-xxx\uFF09\u3002\n\n# OUTPUT\n\u53EA\u8F93\u51FA\u4E00\u4E2A JSON\u3002\u5B57\u6BB5\u91CA\u4E49\uFF1A\n- checklist\uFF1A\u6570\u7EC4 [{item_id(D-\\d{2}),item,evidence,verify_how}]\u3002\n- known_limitations\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\u3002\n- open_items\uFF1A\u5B57\u7B26\u4E32\u6570\u7EC4\u3002\n\n\u793A\u4F8B\uFF1A\n{"checklist":[{"item_id":"D-01","item":"\u63A5\u53E3\u8FD4\u56DE\u56FA\u5B9A\u6587\u6848","evidence":"task-pass/T-001 + C-003 \u5168\u7EFF","verify_how":"curl \u793A\u4F8B"}],"known_limitations":["\u65E0\u5206\u9875"],"open_items":["PE-002"]}\n\n# SELF-CHECK\n1. checklist \u6BCF\u6761\u662F\u5426\u90FD\u6709\u53EF\u6838\u67E5\u951A\u70B9\uFF1F\n2. \u662F\u5426\u8986\u76D6\u5951\u7EA6\u5168\u90E8 FR\uFF1F\n\n### CORRECTION-APPENDIX\n\u7B2C {{retry_attempt}} / \u6700\u591A {{retry_max}} \u6B21\n\u91CD\u65B0\u8F93\u51FA\u5B8C\u6574 JSON\u3002\u9519\u8BEF\uFF1A\n{{correction_context}}\n',
  "version_manifest.json": '{\n  "group_version": "v1",\n  "generated_at": "2026-08-27T15:34:17.142Z",\n  "files": {\n    "phase0_question.txt": {\n      "sha256": "ac816624c622a5d24bfd7acfd7b6bb40dd7cf2d0ee7c6f09f3fea7f1b9332f72",\n      "token_limit": 2000\n    },\n    "phase0_specgen.txt": {\n      "sha256": "25e0381177d0e8246d0dc5853a2ab5a87e9e71cfa1fe1054d7ce259d8ae0e051",\n      "token_limit": 3200\n    },\n    "phase1_split.txt": {\n      "sha256": "a6651aac2298e1bf0e969892de80277ba88e0c80a5e47c283de47c0fb36d9fdf",\n      "token_limit": 1200\n    },\n    "phase2_build.txt": {\n      "sha256": "3346296fb68658ae9259676574cbade50ed9bdb1c28e5671b5e7ae3cc277d841",\n      "token_limit": 1000\n    },\n    "phase3_testdata.txt": {\n      "sha256": "66ddbc0a49b909b761035b9e116ced33b3e2bd68a24a7b3c420aed02e6fe6938",\n      "token_limit": 2200\n    },\n    "phase4_delivery.txt": {\n      "sha256": "3020782a8d8de9dd9401bb64bbc2f1090acc0d7cd74850f4e312056e3db594d8",\n      "token_limit": 900\n    },\n    "phase3_uifix.txt": {\n      "sha256": "1767daa9f4848265a0219bb9962f5f822c5f9bc8b4350f7fbaf323e262424331",\n      "token_limit": 900\n    }\n  }\n}'
};

// src/store/paths.ts
import { promises as fs } from "node:fs";
function adocsLayout(projectRoot) {
  const a = join(projectRoot, ".adocs");
  return {
    projectRoot,
    adocs: a,
    index: join(a, "INDEX.json"),
    specs: join(a, "specs"),
    specsArchive: join(a, "specs", "archive"),
    contracts: join(a, "contracts"),
    interview: join(a, "interview"),
    tasks: join(a, "tasks"),
    assertions: join(a, "tasks", "assertions"),
    flow: join(a, "flow"),
    state: join(a, "flow", "state.json"),
    test: join(a, "test"),
    reports: join(a, "test", "reports"),
    regression: join(a, "test", "regression"),
    prompts: join(a, "prompts", "v1")
  };
}
async function ensureAdocsDirs(layout) {
  await fs.mkdir(layout.specsArchive, { recursive: true });
  await fs.mkdir(layout.contracts, { recursive: true });
  await fs.mkdir(layout.interview, { recursive: true });
  await fs.mkdir(layout.assertions, { recursive: true });
  await fs.mkdir(layout.flow, { recursive: true });
  await fs.mkdir(layout.reports, { recursive: true });
  await fs.mkdir(layout.regression, { recursive: true });
  await fs.mkdir(layout.prompts, { recursive: true });
  await materializePromptTemplates(layout);
}
async function materializePromptTemplates(layout) {
  for (const [name, content] of Object.entries(EMBEDDED_PROMPTS)) {
    const p = join(layout.prompts, name);
    try {
      await fs.access(p);
    } catch {
      await fs.writeFile(p, content, "utf8");
    }
  }
}

// src/store/mod.ts
init_atomic();

// src/store/state.ts
init_atomic();
async function readState(layout) {
  const r = await readJSONTolerant(layout.state);
  return r.ok ? r.data : null;
}
async function appendState(layout, phase, note) {
  return withLock(layout.state, async () => {
    const prev = (await readJSONTolerant(layout.state)).data ?? {
      current_phase: phase,
      version: 0,
      history: []
    };
    const history = Array.isArray(prev.history) ? prev.history : [];
    const next = {
      ...prev,
      current_phase: phase,
      version: (prev.version ?? 0) + 1,
      history: [...history, { ts: (/* @__PURE__ */ new Date()).toISOString(), phase, note }]
    };
    await atomicWriteJSON(layout.state, next);
    return next;
  });
}

// src/store/index.ts
init_atomic();

// src/store/interview.ts
init_atomic();
import { join as join2 } from "node:path";
import { promises as fs3 } from "node:fs";
async function appendDecisionRound(layout, round) {
  const path = join2(layout.interview, "decision_tree.json");
  return withLock(path, async () => {
    const prev = (await readJSONTolerant(path)).data ?? [];
    const next = Array.isArray(prev) ? [...prev, round] : [round];
    await atomicWriteJSON(path, next);
    return next;
  });
}
async function appendAnswersLog(layout, line) {
  const path = join2(layout.interview, "answers.log");
  return withLock(path, async () => {
    const head = await fileExists(path) ? await fs3.readFile(path, "utf8") : "";
    await atomicWriteFile(path, head + line + "\n");
  });
}

// src/store/tasks.ts
init_atomic();
import { join as join3 } from "node:path";
async function writeTaskList(layout, list) {
  await atomicWriteJSON(join3(layout.tasks, "TASK_LIST.json"), list);
}
async function readTaskList(layout) {
  const r = await readJSONTolerant(join3(layout.tasks, "TASK_LIST.json"));
  return r.ok ? r.data : null;
}

// src/store/glossary.ts
init_atomic();

// src/store/mod.ts
init_test();

// src/engine/packet.ts
var PHASE_SPECS = {
  P0_ALIGN: { template: "phase0_question.txt", validator: "question", node: "T1" },
  P1_SPLIT: { template: "phase1_split.txt", validator: "split", node: "T3" },
  P2_BUILD: { template: "phase2_build.txt", validator: "build", node: "T4" },
  P3_TEST: { template: "phase3_testdata.txt", validator: "testdata", node: "T5" },
  P4_DELIVER: { template: "phase4_delivery.txt", validator: "delivery", node: "T6" }
};
function buildPacket(envelope) {
  return {
    ...envelope,
    submit_with: "flow_submit",
    retry_state: envelope.retry ?? { attempt: 1, max: 3, last_errors: [] }
  };
}

// src/validate/types.ts
function collect(issues) {
  const errors = issues.filter((i) => !i.passed && i.severity === "error");
  const warnings = issues.filter((i) => !i.passed && i.severity === "warning");
  const order = (r) => r.includes("R-Q1") || r.includes("R-B1") || r.includes("R-S2") || r.includes("Schema") ? 0 : r.includes("\u8986\u76D6\u7387") || r.includes("R-Q4") ? 1 : 2;
  const correctionBag = errors.slice().sort((a, b) => order(a.rule) - order(b.rule)).map((e) => ({ rule: e.rule, human_hint: e.human_hint ?? "", fix_direction: e.fix_direction }));
  return { passed: errors.length === 0, errors, warnings, correctionBag };
}
function issue2(rule, passed, opts = {}) {
  return { rule, passed, severity: opts.severity ?? "error", ...opts };
}
function describeReceivedValue(raw, path) {
  try {
    let cur = raw;
    for (const k of path ?? []) {
      if (cur == null) return "undefined";
      cur = cur[k];
    }
    if (cur === void 0) return "undefined";
    const t = Array.isArray(cur) ? "array" : typeof cur;
    let s;
    try {
      s = JSON.stringify(cur);
    } catch {
      s = String(cur);
    }
    if (s && s.length > 90) s = s.slice(0, 87) + "...";
    return `${t} ${s}`;
  } catch {
    return "";
  }
}
var INTERVIEW_KEYS = /* @__PURE__ */ new Set([
  "exhausted",
  "question",
  "options",
  "recommendation",
  "recommendation_reason",
  "covered_dimension",
  "business_analogy",
  "new_facts",
  "pending_explanation_update",
  "glossary_update",
  "prev_round_disposition",
  "context_discoveries"
]);
function describeSchemaError(issues, raw) {
  const lines = [];
  const isObj = raw !== null && typeof raw === "object" && !Array.isArray(raw);
  if (!isObj) {
    const got = raw === null ? "null" : Array.isArray(raw) ? "\u6570\u7EC4(array)" : typeof raw;
    lines.push(`\u3010\u7ED3\u6784\u9519\u8BEF\u3011\u5F15\u64CE\u671F\u671B\u4EA7\u51FA\u662F\u300CJSON \u5BF9\u8C61(object)\u300D\uFF0C\u4F46\u4F60\u4F20\u5165\u7684\u662F ${got}\u3002`);
    lines.push("\u5E38\u89C1\u9519\u8BEF\uFF1A\u2460\u628A JSON \u5E8F\u5217\u5316\u6210\u5B57\u7B26\u4E32\u518D\u4F20\uFF1B\u2461\u5305\u5728 ```json \u4EE3\u7801\u5757\u91CC\uFF1B\u2462\u628A\u6574\u4E2A\u5BF9\u8C61\u53C8\u585E\u8FDB\u4E86\u67D0\u4E2A\u5B57\u7B26\u4E32\u5B57\u6BB5\u3002");
    lines.push('\u6B63\u786E\u505A\u6CD5\uFF1Aflow_submit \u7684 output \u76F4\u63A5\u4F20\u7ED3\u6784\u5316\u5BF9\u8C61\uFF0C\u4F8B\u5982 { "exhausted": false, "question": "...", "options": { "A": "...", "B": "..." }, "recommendation": "A", ... }\uFF08\u4E0D\u8981\u52A0\u5F15\u53F7\u3001\u4E0D\u8981\u8F6C\u4E49\u3001\u4E0D\u8981\u4EE3\u7801\u5757\uFF09\u3002');
  } else if (Object.keys(raw).length === 1 && "output" in raw && !(raw.exhausted !== void 0) && !INTERVIEW_KEYS.has(Object.keys(raw)[0])) {
    lines.push("\u3010\u7ED3\u6784\u9519\u8BEF\u3011\u4F60\u4F3C\u4E4E\u628A\u4EA7\u51FA\u53C8\u5305\u4E86\u4E00\u5C42 output \u5B57\u6BB5\u3002flow_submit \u7684 output \u53C2\u6570\u672C\u8EAB\u5C31\u662F\u4EA7\u51FA\u5BF9\u8C61\uFF0C\u8BF7\u76F4\u63A5\u628A\u8BBF\u8C08\u5B57\u6BB5\u5E73\u94FA\u4F20\u5165\uFF0C\u4E0D\u8981\u989D\u5916\u5D4C\u5957 { output: {...} }\u3002");
  }
  if (issues && issues.length) {
    lines.push("\u3010\u5B57\u6BB5\u7EA7\u9519\u8BEF\u3011\u9010\u6761\u4FEE\u6B63\uFF1A");
    for (const it of issues) {
      const p = it.path && it.path.length ? it.path.join(".") : "(\u6700\u5916\u5C42/\u6839)";
      const got = describeReceivedValue(raw, it.path);
      const want = it.message || (it.code ? `${it.code}: expected ${it.expected ?? "?"}, received ${it.received ?? "?"}` : "\u4E0D\u7B26\u5408 Schema");
      lines.push(`- \u5B57\u6BB5\u300C${p}\u300D\uFF1A${want}${got ? `\uFF5C\u5B9E\u9645\u6536\u5230\uFF1A${got}` : ""}`);
    }
  }
  return lines.join("\n");
}
function unwrapArgs(a) {
  if (a && typeof a === "object" && a.def !== void 0) return a.def;
  return a;
}
var OUTPUT_KEYS = /* @__PURE__ */ new Set([
  "exhausted",
  "question",
  "options",
  "recommendation",
  "recommendation_reason",
  "covered_dimension",
  "business_analogy",
  "new_facts",
  "pending_explanation_update",
  "glossary_update",
  "prev_round_disposition",
  "context_discoveries",
  "tasks",
  "contract",
  "delivery",
  "spec"
]);
function extractOutput(a) {
  const u = unwrapArgs(a);
  if (u && typeof u === "object" && u.output !== void 0) return u.output;
  if (u && typeof u === "object") {
    for (const k of Object.keys(u)) if (OUTPUT_KEYS.has(k)) return u;
  }
  return u;
}
var VAGUE_WORDS = ["\u5927\u6982", "\u53EF\u80FD", "\u5E94\u8BE5", "\u4F3C\u4E4E", "\u6216\u8BB8", "\u5927\u6982", "\u4E5F\u8BB8", "\u4F30\u8BA1"];
var evidenceSchema = external_exports.object({
  type: external_exports.enum(["command", "code", "log"]),
  detail: external_exports.string().min(1)
});
function hasVagueWord(text) {
  return VAGUE_WORDS.some((w) => text.includes(w));
}
var taskIdSchema = external_exports.string().regex(/^T-\d{1,3}$/);
var caseIdSchema = external_exports.string().regex(/^C-\d{1,3}$/);
var frIdSchema = external_exports.string().regex(/^FR-\d{1,3}$/);

// src/validate/ngram.ts
function ngrams(text, n = 2) {
  const norm = text.toLowerCase().replace(/\s+/g, " ").trim();
  if (norm.length === 0) return /* @__PURE__ */ new Set();
  if (norm.length < n) return /* @__PURE__ */ new Set([norm]);
  const out = /* @__PURE__ */ new Set();
  for (let i = 0; i + n <= norm.length; i++) out.add(norm.slice(i, i + n));
  return out;
}
function maxJaccard(candidate, history, threshold = 0.8) {
  let best = { score: 0, matchedIndex: -1, matchedText: "" };
  const a = ngrams(candidate);
  for (let i = 0; i < history.length; i++) {
    const b = ngrams(history[i]);
    if (a.size === 0 || b.size === 0) continue;
    let inter = 0;
    for (const g of a) if (b.has(g)) inter++;
    const score = inter / (a.size + b.size - inter);
    if (score > best.score) best = { score, matchedIndex: i, matchedText: history[i] };
  }
  return best;
}

// src/validate/glossary.ts
function normalize(s) {
  if (typeof s !== "string") return "";
  return s.replace(/[\s　]+/g, "").replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 65248)).toLowerCase().trim();
}
function checkGlossaryUpdate(adds, answersLog, existing = []) {
  const errors = [];
  const warnings = [];
  const allTerms = [...existing.map((t) => t.term), ...adds.map((a) => a.term)];
  const seen = /* @__PURE__ */ new Map();
  for (const t of allTerms) {
    const k = normalize(t);
    seen.set(k, (seen.get(k) ?? 0) + 1);
  }
  for (const [k, n] of seen) if (n > 1) errors.push(`\u8BCD\u6C47\u300C${k}\u300D\u91CD\u590D\u5B9A\u4E49`);
  const aliasExpr = (a) => typeof a === "string" ? a : a?.expr ?? "";
  const aliasMap = /* @__PURE__ */ new Map();
  const pushAlias = (expr, owner) => {
    if (!expr) return;
    const k = normalize(expr);
    const arr = aliasMap.get(k) ?? [];
    if (!arr.includes(owner)) arr.push(owner);
    aliasMap.set(k, arr);
  };
  for (const t of existing) for (const a of t.aliases ?? []) pushAlias(aliasExpr(a), t.term);
  for (const a of adds) for (const al of a.aliases ?? []) pushAlias(aliasExpr(al), a.term);
  for (const [k, owners] of aliasMap) {
    if (owners.length > 1)
      warnings.push(`\u522B\u540D\u300C${k}\u300D\u6307\u5411\u591A\u4E2A\u8BCD\u6C47\uFF08${owners.join("/")}\uFF09\uFF0C\u5E94\u8D70 resolve_ambiguity \u6216\u8BB0 ambiguities`);
  }
  const logNorm = normalize(answersLog);
  for (const a of adds) {
    for (const al of a.aliases ?? []) {
      if (!logNorm.includes(normalize(al))) {
        warnings.push(`\u8BCD\u6C47\u300C${a.term}\u300D\u522B\u540D\u300C${al}\u300D\u672A\u5728 answers.log \u539F\u6587\u547D\u4E2D\uFF08AI \u4EE3\u62DF\uFF0C\u5DF2\u964D\u7EA7\u4E3A\u544A\u8B66\uFF09`);
      }
    }
  }
  return { errors, warnings };
}
function checkGlossaryConsistency(specGlossaryText, glossaryV1, businessEntities) {
  const errors = [];
  const warnings = [];
  const confirmedTerms = new Set(glossaryV1.filter((t) => t.status === "confirmed").map((t) => t.term));
  for (const ent of businessEntities) {
    if (!confirmedTerms.has(ent)) errors.push(`\u4E1A\u52A1\u5B9E\u4F53\u300C${ent}\u300D\u672A\u5728\u672F\u8BED\u8868 confirmed \u96C6\u4E2D`);
    else {
      const term = glossaryV1.find((t) => t.term === ent);
      const hasUserAlias = (term.aliases ?? []).some((a) => typeof a === "string" ? false : a.source && /round-|用户/.test(a.source));
      if (!hasUserAlias) warnings.push(`confirmed \u5B9E\u4F53\u300C${ent}\u300D\u7F3A\u7528\u6237\u539F\u8BDD\u522B\u540D\uFF08\u8F6F\u544A\u8B66\u653E\u884C\uFF09`);
    }
  }
  for (const line of specGlossaryText.split("\n")) {
    const m = line.match(/^\s*[-*]?\s*\*\*?([\u4e00-\u9fa5A-Za-z0-9_]+)\*\*?\s*[:：]/);
    if (m && !confirmedTerms.has(m[1])) errors.push(`\u672F\u8BED\u8868\u7AE0\u8282\u542B\u672A\u786E\u8BA4\u8BCD\u6761\u300C${m[1]}\u300D`);
  }
  return { errors, warnings };
}

// src/validate/exhaustion.ts
var DEFAULT_DIMS = [
  "\u8F93\u5165\u5951\u7EA6",
  "\u5904\u7406\u903B\u8F91",
  "\u8F93\u51FA\u683C\u5F0F",
  "\u5931\u8D25\u5F02\u5E38",
  "\u5173\u8054\u5F71\u54CD",
  "UI\u7EA6\u675F"
];
function evaluateExhaustion(input) {
  const required2 = input.requiredDimensions ?? DEFAULT_DIMS;
  const gaps = [];
  if (!input.declaredExhausted) {
    return { exhausted: false, gaps };
  }
  const coveredDimensions = input.coveredDimensions ?? [];
  for (const d of required2) {
    if (!coveredDimensions.includes(d)) gaps.push(`\u7EF4\u5EA6\u672A\u8986\u76D6\uFF1A${d}`);
  }
  for (const p of input.pendingOpen ?? []) {
    gaps.push(`\u5F85\u6F84\u6E05\u9879\u672A\u5904\u7F6E\uFF1A${p}`);
  }
  const dimsAllCovered = gaps.length === 0;
  if (dimsAllCovered) {
    return { exhausted: true, gaps };
  }
  if ((input.noNewFactRounds ?? 0) < 3) {
    gaps.push(`\u8FDE\u7EED\u65E0\u65B0\u4E8B\u5B9E\u8F6E\u6570 ${input.noNewFactRounds ?? 0} < 3\uFF0C\u672A\u8FBE\u7A77\u5C3D\u89E6\u53D1\u6761\u4EF6`);
  }
  return { exhausted: gaps.length === 0, gaps };
}

// src/validate/counters.ts
var RETRY_THRESHOLD = 3;
var STREAK_THRESHOLD = 5;
function onFailure(prev) {
  const count = prev.retry_count + 1;
  if (count >= RETRY_THRESHOLD) {
    const streak = prev.task_fail_streak + 1;
    if (streak >= STREAK_THRESHOLD) {
      return {
        state: { retry_count: 0, task_fail_streak: streak },
        action: "frozen",
        reason: `task_fail_streak=${streak} \u8FBE\u5230\u9608\u503C ${STREAK_THRESHOLD}`
      };
    }
    return {
      state: { retry_count: 0, task_fail_streak: streak },
      action: "reset_context"
    };
  }
  return { state: { retry_count: count, task_fail_streak: prev.task_fail_streak }, action: "none" };
}

// src/validate/zodSchemas.ts
var questionOutputSchema = external_exports.object({
  exhausted: external_exports.boolean(),
  question: external_exports.string().optional(),
  options: external_exports.object({ A: external_exports.string(), B: external_exports.string() }).optional(),
  recommendation: external_exports.enum(["A", "B"]).optional(),
  recommendation_reason: external_exports.string().optional(),
  covered_dimension: external_exports.string().optional(),
  business_analogy: external_exports.string().optional(),
  new_facts: external_exports.array(external_exports.object({
    fact_id: external_exports.string(),
    content: external_exports.string(),
    source: external_exports.string()
  })).optional(),
  pending_explanation_update: external_exports.object({
    added: external_exports.array(external_exports.any()),
    resolved: external_exports.array(external_exports.any()),
    deferred: external_exports.array(external_exports.any())
  }).optional(),
  glossary_update: external_exports.object({
    add: external_exports.array(external_exports.object({
      term: external_exports.string(),
      biz_desc: external_exports.string().optional(),
      aliases: external_exports.array(external_exports.string()).optional(),
      evidence: external_exports.string().optional()
    })).optional(),
    extend_aliases: external_exports.array(external_exports.any()).optional(),
    resolve_ambiguity: external_exports.array(external_exports.any()).optional()
  }).optional(),
  prev_round_disposition: external_exports.object({ round: external_exports.number(), user_choice: external_exports.string(), rejected: external_exports.array(external_exports.string()) }).nullable().optional(),
  // 涟漪检测：依据用户需求对既有代码/历史 SPEC 探索发现的关联关系（source 前缀 code:/doc:）
  context_discoveries: external_exports.array(external_exports.object({
    discovery_id: external_exports.string(),
    content: external_exports.string(),
    source: external_exports.string(),
    needs_confirmation: external_exports.boolean().optional()
  })).optional()
});
var contractJsonSchema = external_exports.object({
  meta: external_exports.any().optional(),
  business_entities: external_exports.record(external_exports.string(), external_exports.object({
    fields: external_exports.array(external_exports.string()),
    required: external_exports.array(external_exports.string())
  })).optional(),
  state_machine: external_exports.any().optional(),
  ui_contract: external_exports.any().optional(),
  test_philosophy: external_exports.string().optional(),
  force_rules: external_exports.array(external_exports.object({ fr_id: frIdSchema, rule: external_exports.string() })).optional(),
  relations: external_exports.any().optional()
});
var splitOutputSchema = external_exports.array(
  external_exports.object({
    id: taskIdSchema,
    title: external_exports.string(),
    objective: external_exports.string(),
    exit_criteria: external_exports.array(frIdSchema),
    depends_on: external_exports.array(external_exports.string()).optional(),
    affected_files_hint: external_exports.array(external_exports.string()).optional()
  })
);
var buildOutputSchema = external_exports.object({
  task_id: external_exports.string(),
  todo_list: external_exports.array(external_exports.string()),
  declared_scope: external_exports.object({ files_touched: external_exports.array(external_exports.string()) }).optional(),
  files_changed: external_exports.array(external_exports.object({
    path: external_exports.string(),
    action: external_exports.string(),
    loc: external_exports.number().optional()
  })),
  deviations: external_exports.array(external_exports.any()).optional(),
  self_check: external_exports.array(external_exports.object({
    criterion: external_exports.string(),
    expectation: external_exports.string(),
    actual: external_exports.string(),
    evidence: evidenceSchema,
    result: external_exports.enum(["pass", "fail"])
  })),
  commit_message: external_exports.string()
});
var testdataOutputSchema = external_exports.object({
  task_id: external_exports.string(),
  cases: external_exports.array(external_exports.object({
    case_id: caseIdSchema,
    fr_ref: frIdSchema,
    description: external_exports.string(),
    input: external_exports.any().optional(),
    expected_behavior: external_exports.string(),
    verify_command: external_exports.string().optional()
  })),
  results: external_exports.array(external_exports.object({
    case_id: caseIdSchema,
    expectation: external_exports.string(),
    actual: external_exports.string(),
    evidence: evidenceSchema,
    result: external_exports.enum(["pass", "fail"])
  })),
  // 场景模块：用原子化用例（cases）串联成业务场景，供回归复用（R-P6 校验）
  scenarios: external_exports.array(external_exports.object({
    scenario_id: external_exports.string().regex(/^S-\d{1,3}$/),
    title: external_exports.string(),
    description: external_exports.string().optional(),
    case_ids: external_exports.array(caseIdSchema),
    verify_command: external_exports.string().optional()
  })).optional(),
  // 可落盘回归脚本：写入项目 tests/regression/ 下，供全量回归执行（R-P7 校验）
  scripts: external_exports.array(external_exports.object({
    path: external_exports.string(),
    content: external_exports.string()
  })).optional()
});
var deliveryOutputSchema = external_exports.object({
  checklist: external_exports.array(external_exports.object({
    item_id: external_exports.string().regex(/^D-\d{2}$/),
    item: external_exports.string(),
    evidence: external_exports.string(),
    verify_how: external_exports.string()
  })),
  known_limitations: external_exports.array(external_exports.string()).optional(),
  open_items: external_exports.array(external_exports.string()).optional()
});

// src/validate/validators/question.ts
function validateQuestion(raw, ctx) {
  const parsed = questionOutputSchema.safeParse(raw);
  if (!parsed.success) {
    return collect([
      issue2("R-Q1", false, {
        human_hint: "\u8F93\u51FA JSON \u4E0D\u7B26\u5408 Schema\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09",
        fix_direction: describeSchemaError(parsed.error.issues, raw)
      })
    ]);
  }
  const o = parsed.data;
  const issues = [];
  if (!o.exhausted) {
    if (!o.question || o.question.trim().length === 0)
      issues.push(issue2("R-Q2", false, { human_hint: "exhausted=false \u65F6 question \u5FC5\u586B", fix_direction: "\u8865\u4E0A\u672C\u8F6E\u95EE\u9898" }));
    if (!o.options || o.recommendation !== "A" && o.recommendation !== "B")
      issues.push(issue2("R-Q2", false, { human_hint: "exhausted=false \u65F6\u987B\u7ED9\u51FA options \u4E0E recommendation(A/B)", fix_direction: "\u8865\u9F50\u9009\u9879\u4E0E\u63A8\u8350" }));
  }
  if (!o.exhausted && o.question) {
    const { score, matchedIndex } = maxJaccard(o.question, ctx.historyQuestions, 0.8);
    if (score >= 0.8)
      issues.push(issue2("R-Q3", false, {
        human_hint: `\u672C\u8F6E\u95EE\u9898\u4E0E\u5386\u53F2\u95EE\u9898\u76F8\u4F3C\u5EA6 ${score.toFixed(2)} \u2265 0.8\uFF0C\u7591\u4F3C\u91CD\u590D\uFF08\u547D\u4E2D\u7B2C ${matchedIndex + 1} \u4E2A\u5386\u53F2\u95EE\u9898\uFF09`,
        fix_direction: "\u6362\u4E00\u4E2A\u672A\u8986\u76D6\u7EF4\u5EA6\u7684\u95EE\u9898\uFF0C\u6216\u786E\u8BA4\u5DF2\u7A77\u5C3D\u8F6C exhausted=true"
      }));
  }
  if (o.exhausted) {
    const ex = evaluateExhaustion({
      declaredExhausted: true,
      coveredDimensions: ctx.coveredDimensions ?? [],
      pendingOpen: ctx.pendingOpen,
      noNewFactRounds: ctx.noNewFactRounds
    });
    if (!ex.exhausted)
      issues.push(issue2("R-Q4", false, {
        human_hint: `exhausted=true \u672A\u901A\u8FC7\u7A77\u5C3D\u5B88\u536B\uFF0C\u7F3A\u53E3\uFF1A${ex.gaps.join("\uFF1B")}`,
        fix_direction: "\u8865\u5168\u8986\u76D6\u7F3A\u53E3\u6216\u7EE7\u7EED\u63D0\u95EE\uFF08exhausted=false\uFF09"
      }));
  }
  if (o.prev_round_disposition !== void 0 && o.prev_round_disposition !== null) {
    const d = o.prev_round_disposition;
    if (ctx.previousAcceptedRound === null)
      issues.push(issue2("R-Q5", false, { human_hint: "\u9996\u8F6E prev_round_disposition \u5FC5\u987B\u4E3A null", fix_direction: "\u7F6E\u4E3A null" }));
    else {
      if (d.round !== ctx.previousAcceptedRound)
        issues.push(issue2("R-Q5", false, { human_hint: `round=${d.round} \u5E94\u7B49\u4E8E\u4E0A\u4E00\u5DF2\u63A5\u53D7\u8F6E\u6B21 ${ctx.previousAcceptedRound}`, fix_direction: "\u586B\u5199\u6B63\u786E\u7684\u4E0A\u4E00\u5DF2\u63A5\u53D7\u8F6E\u6B21" }));
      if (d.user_choice !== "A" && d.user_choice !== "B")
        issues.push(issue2("R-Q5", false, { human_hint: "user_choice \u5FC5\u987B\u662F A \u6216 B", fix_direction: "\u586B\u5199 A/B" }));
      if (d.rejected.includes(d.user_choice))
        issues.push(issue2("R-Q5", false, { human_hint: "rejected \u4E0E user_choice \u76F8\u4EA4", fix_direction: "\u4ECE rejected \u79FB\u9664\u6240\u9009\u9009\u9879" }));
    }
  }
  const adds = o.glossary_update?.add ?? [];
  if (adds.length > 3)
    issues.push(issue2("R-Q6", false, { human_hint: "\u6BCF\u8F6E glossary_update.add \u4E0D\u5F97\u8D85\u8FC7 3 \u6761", fix_direction: "\u62C6\u5206\u5230\u540E\u7EED\u8F6E\u6B21", severity: "error" }));
  const g = checkGlossaryUpdate(adds, ctx.answersLog, ctx.glossaryExisting ?? []);
  for (const e of g.errors) issues.push(issue2("R-Q6", false, { human_hint: e, fix_direction: "\u4FEE\u6B63\u8BCD\u6C47\u8868\u66F4\u65B0" }));
  for (const w of g.warnings) issues.push(issue2("R-Q6", false, { human_hint: w, severity: "warning" }));
  const discs = o.context_discoveries ?? [];
  const discIds = discs.map((d) => d.discovery_id);
  if (new Set(discIds).size !== discIds.length)
    issues.push(issue2("R-Q9", false, { human_hint: "context_discoveries.discovery_id \u91CD\u590D", fix_direction: "\u4FDD\u8BC1 discovery_id \u552F\u4E00\uFF08\u5982 D-001\uFF09" }));
  for (const d of discs) {
    const src = d.source ?? "";
    if (!/^(code:|doc:|round-)/.test(src))
      issues.push(issue2("R-Q9", false, {
        human_hint: `context_discoveries ${d.discovery_id} \u7684 source\u300C${src}\u300D\u7F3A\u51FA\u5904\u524D\u7F00`,
        fix_direction: "source \u5FC5\u987B\u4EE5 code:\uFF08\u4EE3\u7801\u52D8\u5BDF\uFF09\u6216 doc:\uFF08\u5386\u53F2 SPEC/\u6587\u6863\uFF09\u6216 round-N\uFF08\u8BBF\u8C08\u786E\u8BA4\uFF09\u5F00\u5934"
      }));
  }
  return collect(issues);
}

// src/validate/validators/split.ts
function hasCycle(tasks) {
  const indeg = /* @__PURE__ */ new Map();
  const adj = /* @__PURE__ */ new Map();
  for (const t of tasks) {
    indeg.set(t.id, indeg.get(t.id) ?? 0);
    for (const d of t.depends_on ?? []) {
      adj.set(d, [...adj.get(d) ?? [], t.id]);
      indeg.set(t.id, (indeg.get(t.id) ?? 0) + 1);
    }
  }
  const queue = [...indeg.entries()].filter(([, n]) => n === 0).map(([k]) => k);
  let visited = 0;
  while (queue.length) {
    const n = queue.shift();
    visited++;
    for (const m of adj.get(n) ?? []) {
      indeg.set(m, (indeg.get(m) ?? 0) - 1);
      if (indeg.get(m) === 0) queue.push(m);
    }
  }
  return visited !== tasks.length;
}
function validateSplit(raw, ctx) {
  const parsed = splitOutputSchema.safeParse(raw);
  if (!parsed.success) {
    return collect([
      issue2("SPLIT-SCHEMA", false, {
        human_hint: "\u4EFB\u52A1\u5217\u8868\u4E0D\u7B26\u5408 Schema\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09",
        fix_direction: describeSchemaError(parsed.error.issues, raw)
      })
    ]);
  }
  const tasks = parsed.data;
  const issues = [];
  const covered = /* @__PURE__ */ new Set();
  for (const t of tasks) for (const fr of t.exit_criteria) covered.add(fr);
  const missing = ctx.contractFRs.filter((fr) => !covered.has(fr));
  if (missing.length)
    issues.push(issue2("SPLIT-COVERAGE", false, {
      human_hint: `FR \u8986\u76D6\u7387\u4E0D\u8DB3\uFF1A${missing.join(", ")} \u672A\u88AB\u4EFB\u4F55\u4EFB\u52A1 exit_criteria \u5F15\u7528`,
      fix_direction: "\u4E3A\u7F3A\u5931 FR \u8865\u5145\u5F52\u5C5E\u4EFB\u52A1\u6216\u786E\u8BA4\u5E94\u5220\u9664\u8BE5 FR"
    }));
  const extra = [...covered].filter((fr) => !ctx.contractFRs.includes(fr));
  if (extra.length)
    issues.push(issue2("SPLIT-COVERAGE", false, {
      human_hint: `exit_criteria \u542B\u975E\u5951\u7EA6 FR\uFF1A${extra.join(", ")}`,
      fix_direction: "\u4EC5\u5F15\u7528\u5951\u7EA6\u4E2D\u5B58\u5728\u7684 FR-ID"
    }));
  if (hasCycle(tasks))
    issues.push(issue2("SPLIT-ACYCLIC", false, { human_hint: "\u4EFB\u52A1\u4F9D\u8D56\u5B58\u5728\u73AF", fix_direction: "\u6253\u7834\u5FAA\u73AF\u4F9D\u8D56" }));
  const ids = new Set(tasks.map((t) => t.id));
  if (ids.size !== tasks.length)
    issues.push(issue2("SPLIT-ID", false, { human_hint: "task_id \u91CD\u590D", fix_direction: "\u4FDD\u8BC1 T-\\d{3} \u552F\u4E00" }));
  if (ctx.businessEntityCount !== void 0) {
    const min = Math.ceil(ctx.businessEntityCount / 2);
    if (tasks.length < min)
      issues.push(issue2("SPLIT-GRANULARITY", false, {
        human_hint: `\u4EFB\u52A1\u6570 ${tasks.length} < \u2308\u5B9E\u4F53\u6570/2\u2309=${min}\uFF0C\u62C6\u89E3\u53EF\u80FD\u8FC7\u7C97`,
        fix_direction: "\u590D\u6838\u662F\u5426\u6F0F\u5207\u4EFB\u52A1",
        severity: "warning"
      }));
  }
  return collect(issues);
}

// src/validate/validators/build.ts
var DEFAULT_COMMIT_RE = /^(feat|fix|chore)\(T-\d{3}\): .+/;
function validateBuild(raw, ctx) {
  const parsed = buildOutputSchema.safeParse(raw);
  if (!parsed.success) {
    return collect([
      issue2("R-B1", false, {
        human_hint: "\u52A8\u4F5C\u62A5\u544A\u4E0D\u7B26\u5408 Schema\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09",
        fix_direction: describeSchemaError(parsed.error.issues, raw)
      })
    ]);
  }
  const o = parsed.data;
  const issues = [];
  if (o.task_id !== ctx.current_task)
    issues.push(issue2("R-B2", false, { human_hint: `task_id=${o.task_id} \u987B\u7B49\u4E8E current_task=${ctx.current_task}`, fix_direction: "\u586B\u5199\u6B63\u786E\u7684\u4EFB\u52A1 id" }));
  if (ctx.gate && !("skipped" in ctx.gate) && !ctx.gate.passed)
    issues.push(issue2("R-B0", false, {
      human_hint: `\u6784\u5EFA\u95E8\u7981\u5931\u8D25\uFF08${ctx.gate.failedCommand ?? "\u547D\u4EE4"}\uFF09\uFF1A${(ctx.gate.outputTail ?? "").slice(-300)}`,
      fix_direction: "\u4FEE\u590D lint/typecheck/test \u62A5\u9519\u540E\u91CD\u4EA4"
    }));
  const declared = new Set(o.files_changed.map((f) => f.path));
  const gitAll = /* @__PURE__ */ new Set([...ctx.git_diff_names, ...ctx.git_new_files]);
  const missingInReport = [...gitAll].filter((f) => !declared.has(f));
  const extraInReport = [...declared].filter((f) => !gitAll.has(f));
  if (missingInReport.length || extraInReport.length)
    issues.push(issue2("R-B3", false, {
      human_hint: `files_changed \u4E0E git \u4E0D\u4E00\u81F4\uFF1Agit \u6709\u62A5\u544A\u65E0=[${missingInReport.join(",")}] \u62A5\u544A\u6709 git \u65E0=[${extraInReport.join(",")}]`,
      fix_direction: "files_changed \u5FC5\u987B\u4E0E git diff/status \u5B8C\u5168\u5BF9\u5E94"
    }));
  const touched = new Set(o.declared_scope?.files_touched ?? []);
  const deviated = new Set((o.deviations ?? []).map((d) => d.path).filter(Boolean));
  const allowed = /* @__PURE__ */ new Set([...ctx.affected_files_hint, ...deviated]);
  const conflicts = [];
  for (const f of touched) if (!allowed.has(f)) conflicts.push(`\u58F0\u660E\u89E6\u78B0 ${f} \u4E0D\u5728 hint\u222Adeviations`);
  for (const f of declared) if (!allowed.has(f)) conflicts.push(`\u5B9E\u9645\u6539\u52A8 ${f} \u4E0D\u5728 hint\u222Adeviations`);
  for (const f of allowed) {
    if (!touched.has(f) && !declared.has(f))
      conflicts.push(`hint/deviation ${f} \u65E2\u672A\u58F0\u660E\u4E5F\u672A\u5B9E\u9645\u6539\u52A8\uFF08\u865A\u62A5\u8303\u56F4\uFF09`);
  }
  if (conflicts.length)
    issues.push(issue2("R-B4", false, { human_hint: `\u4E09\u65B9\u5BF9\u8D26\u77DB\u76FE\uFF1A${conflicts.join("\uFF1B")}`, fix_direction: "\u8BA9 declared_scope / files_changed / hint\u222Adeviations \u4E09\u65B9\u4E00\u81F4" }));
  const covered = new Set(o.self_check.map((s) => s.criterion));
  for (const fr of ctx.exit_criteria)
    if (!covered.has(fr))
      issues.push(issue2("R-B5", false, { human_hint: `self_check \u672A\u8986\u76D6 exit_criteria \u7684 ${fr}`, fix_direction: "\u4E3A\u6BCF\u4E2A FR \u8865\u4E00\u6761 self_check" }));
  for (const s of o.self_check) {
    if (!s.expectation || !s.actual)
      issues.push(issue2("R-B5", false, { human_hint: `self_check(${s.criterion}) \u7F3A expectation/actual`, fix_direction: "\u8865\u5168\u5B57\u6BB5" }));
    if (hasVagueWord(s.actual) || hasVagueWord(s.expectation))
      issues.push(issue2("R-B5", false, { human_hint: `self_check(${s.criterion}) \u8BC1\u636E\u542B\u6A21\u7CCA\u8BCD\uFF08"\u5927\u6982/\u53EF\u80FD/\u5E94\u8BE5"\u7B49\uFF09`, fix_direction: "\u7528\u53EF\u6838\u67E5\u7684\u5177\u4F53\u4E8B\u5B9E\u66FF\u6362\u6A21\u7CCA\u8868\u8FF0" }));
    if (s.result === "fail")
      issues.push(issue2("R-B5", false, { human_hint: `self_check(${s.criterion}) \u62A5 fail`, fix_direction: "\u4FEE\u590D\u5B9E\u73B0\u4F7F\u8BE5\u6761\u76EE\u901A\u8FC7" }));
  }
  const re = ctx.commitRegex ?? DEFAULT_COMMIT_RE;
  if (!re.test(o.commit_message))
    issues.push(issue2("R-B6", false, { human_hint: `commit_message\u300C${o.commit_message}\u300D\u4E0D\u7B26\u5408\u683C\u5F0F ^(feat|fix|chore)(T-\\d{3}): .+`, fix_direction: "\u4FEE\u6B63\u63D0\u4EA4\u4FE1\u606F\u683C\u5F0F" }));
  return collect(issues);
}

// src/validate/validators/testdata.ts
function validateTestdata(raw, ctx) {
  const parsed = testdataOutputSchema.safeParse(raw);
  if (!parsed.success) {
    return collect([
      issue2("R-P1", false, {
        human_hint: "\u6D4B\u8BD5\u62A5\u544A\u4E0D\u7B26\u5408 Schema\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09",
        fix_direction: describeSchemaError(parsed.error.issues, raw)
      })
    ]);
  }
  const o = parsed.data;
  const issues = [];
  const ids = o.cases.map((c) => c.case_id);
  if (new Set(ids).size !== ids.length)
    issues.push(issue2("R-P1", false, { human_hint: "case_id \u91CD\u590D", fix_direction: "\u4FDD\u8BC1 C-\\d{3} \u552F\u4E00" }));
  if (o.cases.length < 5 || o.cases.length > 15)
    issues.push(issue2("R-P1", false, { human_hint: `\u7528\u4F8B\u6570\u91CF ${o.cases.length} \u4E0D\u5728 5\u201315`, fix_direction: "\u8C03\u6574\u5230 5\u201315 \u4E2A\u8FB9\u754C\u7528\u4F8B" }));
  const caseSet = new Set(ids);
  const resSet = new Set(o.results.map((r) => r.case_id));
  const missing = ids.filter((id) => !resSet.has(id));
  const extra = o.results.map((r) => r.case_id).filter((id) => !caseSet.has(id));
  if (missing.length || extra.length)
    issues.push(issue2("R-P2", false, { human_hint: `results \u4E0E cases \u4E0D\u5BF9\u5E94\uFF1A\u7F3A=[${missing}] \u591A=[${extra}]`, fix_direction: "\u8BA9 results \u4E0E cases \u6309 case_id \u4E25\u683C\u4E00\u4E00\u5BF9\u5E94" }));
  for (const c of o.cases)
    if (!ctx.exit_criteria.includes(c.fr_ref))
      issues.push(issue2("R-P3", false, { human_hint: `case ${c.case_id} \u7684 fr_ref=${c.fr_ref} \u4E0D\u5728\u672C\u4EFB\u52A1 exit_criteria`, fix_direction: "fr_ref \u5FC5\u987B\u5F15\u7528\u672C\u4EFB\u52A1 FR-ID" }));
  for (const r of o.results) {
    if (hasVagueWord(r.actual) || hasVagueWord(r.expectation))
      issues.push(issue2("R-P4", false, { human_hint: `result(${r.case_id}) \u542B\u6A21\u7CCA\u8BCD`, fix_direction: "\u7528\u53EF\u6838\u67E5\u4E8B\u5B9E\u66FF\u6362" }));
    if (!["pass", "fail"].includes(r.result))
      issues.push(issue2("R-P4", false, { human_hint: `result(${r.case_id}) \u975E\u6CD5\u503C`, fix_direction: "\u53D6 pass \u6216 fail" }));
  }
  const covered = new Set(o.cases.map((c) => c.fr_ref));
  for (const fr of ctx.exit_criteria)
    if (!covered.has(fr))
      issues.push(issue2("R-P5", false, { human_hint: `exit_criteria \u7684 ${fr} \u65E0\u5BF9\u5E94\u7528\u4F8B`, fix_direction: "\u4E3A\u7F3A\u5931 FR \u8865\u7528\u4F8B" }));
  if (ctx.requiredFields && ctx.requiredFields.length) {
    const hasNull = o.cases.some((c) => c.input && Object.values(c.input).some((v) => v === null || v === "" || v === void 0));
    if (!hasNull)
      issues.push(issue2("R-P5", false, { human_hint: "\u7F3A\u5C11\u5FC5\u586B\u5B57\u6BB5\u7A7A\u503C\u7528\u4F8B", fix_direction: "\u4E3A\u5FC5\u586B\u5B57\u6BB5\u8865\u5145\u4E00\u4E2A\u7A7A\u503C\u8FB9\u754C\u7528\u4F8B" }));
  }
  const scenarios = o.scenarios ?? [];
  const scenarioIds = scenarios.map((s) => s.scenario_id);
  if (new Set(scenarioIds).size !== scenarioIds.length)
    issues.push(issue2("R-P6", false, { human_hint: "scenario_id \u91CD\u590D", fix_direction: "\u4FDD\u8BC1 S-\\d{1,3} \u552F\u4E00" }));
  for (const s of scenarios) {
    for (const cid of s.case_ids ?? []) {
      if (!caseSet.has(cid)) {
        issues.push(issue2("R-P6", false, {
          human_hint: `\u573A\u666F\u6A21\u5757 ${s.scenario_id} \u5F15\u7528\u4E86\u4E0D\u5B58\u5728\u7684\u539F\u5B50\u7528\u4F8B ${cid}`,
          fix_direction: "case_ids \u5FC5\u987B\u5F15\u7528\u672C\u4EFB\u52A1 cases \u4E2D\u5DF2\u5B9A\u4E49\u7684 case_id\uFF08\u539F\u5B50\u7528\u4F8B\uFF09\uFF0C\u573A\u666F\u6A21\u5757\u53EA\u505A\u4E32\u8054\u3001\u4E0D\u5185\u8054\u65B0\u65AD\u8A00"
        }));
        break;
      }
    }
  }
  const scripts = o.scripts ?? [];
  for (const sc of scripts) {
    if (!sc.path || !sc.content || !sc.content.trim()) {
      issues.push(issue2("R-P7", false, { human_hint: "\u811A\u672C\u7F3A\u5931 path \u6216 content", fix_direction: "\u6BCF\u4E2A\u811A\u672C\u987B\u542B\u975E\u7A7A path \u4E0E content" }));
      continue;
    }
    if (!sc.path.startsWith("tests/regression/")) {
      issues.push(issue2("R-P7", false, {
        human_hint: `\u811A\u672C\u8DEF\u5F84 ${sc.path} \u5FC5\u987B\u4F4D\u4E8E\u9879\u76EE tests/regression/ \u4E0B\uFF08\u53EF\u843D\u76D8\u3001\u53EF\u56DE\u5F52\u590D\u7528\uFF09`,
        fix_direction: "\u628A\u56DE\u5F52\u811A\u672C\u7EDF\u4E00\u653E\u8FDB tests/regression/ \u76EE\u5F55"
      }));
    }
    if (sc.path.includes("..") || sc.path.startsWith("/")) {
      issues.push(issue2("R-P7", false, { human_hint: `\u811A\u672C\u8DEF\u5F84 ${sc.path} \u542B\u8D8A\u754C\u7247\u6BB5`, fix_direction: "\u4F7F\u7528\u9879\u76EE\u5185\u76F8\u5BF9\u8DEF\u5F84\uFF0C\u7981\u6B62 .. \u6216\u7EDD\u5BF9\u8DEF\u5F84" }));
    }
  }
  return collect(issues);
}

// src/validate/validators/specgen.ts
var REQUIRED_SECTIONS = [
  "\u80CC\u666F\u4E0E\u76EE\u6807",
  "\u6838\u5FC3\u51B3\u7B56\u8BB0\u5F55",
  "\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09",
  "\u88AB\u62D2\u7EDD\u65B9\u6848",
  "\u5F85\u5B9A\u4E8B\u9879",
  "\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219",
  "\u53D8\u66F4\u5386\u53F2",
  "\u672F\u8BED\u8868"
];
function extractSpecMarkdown(raw) {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object") {
    const cand = raw.spec ?? raw.markdown ?? raw.content ?? raw.doc ?? raw.text;
    if (typeof cand === "string") return cand;
    return JSON.stringify(raw);
  }
  return String(raw ?? "");
}
function extractContract(md) {
  const fence = md.match(/```contract-json\s*([\s\S]*?)```/);
  const raw = fence ? fence[1] : md.match(/```(?:json)?\s*([\s\S]*?)```/g)?.pop()?.replace(/```(json)?/g, "") ?? "";
  if (!raw || !raw.trim()) return { ok: false, error: "\u672A\u627E\u5230 contract-json \u56F4\u680F\u6216\u4EE3\u7801\u5757" };
  try {
    const json2 = JSON.parse(raw);
    return { ok: true, json: json2 };
  } catch (e) {
    return { ok: false, error: `JSON \u89E3\u6790\u5931\u8D25\uFF1A${e.message}` };
  }
}
function validateSpecgen(md, ctx) {
  const issues = [];
  const positions = [];
  for (const title of REQUIRED_SECTIONS) {
    const re = new RegExp(`^#{2,4}\\s*${title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`, "m");
    const m = md.match(re);
    if (m) positions.push({ title, pos: m.index });
    else issues.push(issue2("R-S1", false, { human_hint: `\u7F3A\u5931/\u4E71\u5E8F\u7AE0\u8282\uFF1A\u300A${title}\u300B`, fix_direction: "\u8865\u9F50\u8BE5\u56FA\u5B9A\u7AE0\u8282\u6807\u9898" }));
  }
  for (let i = 1; i < positions.length; i++)
    if (positions[i].pos < positions[i - 1].pos)
      issues.push(issue2("R-S1", false, { human_hint: `\u7AE0\u8282\u987A\u5E8F\u9519\u8BEF\uFF1A\u300A${positions[i].title}\u300B\u5E94\u5728\u300A${positions[i - 1].title}\u300B\u4E4B\u540E`, fix_direction: "\u6309\u56FA\u5B9A\u987A\u5E8F\u91CD\u6392\u7AE0\u8282" }));
  const ext = extractContract(md);
  if (!ext.ok) {
    issues.push(issue2("R-S2", false, { human_hint: ext.error, fix_direction: "\u5728\u9644\u5F55A \u7528 ```contract-json \u56F4\u680F\u63D0\u4F9B\u5408\u6CD5 JSON" }));
    return collect(issues);
  }
  const schema = contractJsonSchema.safeParse(ext.json);
  if (!schema.success)
    issues.push(issue2("R-S3", false, { human_hint: "CONTRACT Schema \u6821\u9A8C\u5931\u8D25\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09", fix_direction: describeSchemaError(schema.error.issues, ext.json) }));
  const frIds = (ext.json?.force_rules ?? []).map((f) => f.fr_id).filter(Boolean);
  const sectionText = (title) => {
    const re = new RegExp(`#{2,4}\\s*${title}[\\s\\S]*?(?=#{2,4}\\s*|$)`);
    return md.match(re)?.[0] ?? "";
  };
  const frSection = sectionText("\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219");
  for (const fr of frIds)
    if (!frSection.includes(fr))
      issues.push(issue2("R-S3", false, { human_hint: `FR-ID ${fr} \u672A\u51FA\u73B0\u5728\u300A\u4E0D\u53EF\u8FDD\u80CC\u89C4\u5219\u300B\u7AE0\u8282`, fix_direction: "\u5728\u8BE5\u7AE0\u8282\u663E\u5F0F\u5217\u51FA\u6BCF\u4E2A FR-ID" }));
  const dims = ["\u8F93\u5165\u5951\u7EA6", "\u5904\u7406\u903B\u8F91", "\u8F93\u51FA\u683C\u5F0F", "\u5931\u8D25\u5F02\u5E38", "\u5173\u8054\u5F71\u54CD", "UI\u7EA6\u675F"];
  for (const d of dims) {
    const hasBody = md.includes(d);
    const hasUiContract = d === "UI\u7EA6\u675F" ? !!ext.json?.ui_contract && Object.keys(ext.json.ui_contract).length >= 0 : true;
    if (!hasBody && !hasUiContract)
      issues.push(issue2("R-S3", true, { severity: "warning", human_hint: `\u516D\u7EF4\u300C${d}\u300D\u5728\u6B63\u6587\u65E0\u843D\u70B9\uFF08\u8B66\u544A\uFF0C\u4E0D\u963B\u585E\uFF09`, fix_direction: "\u5EFA\u8BAE\u5728\u6B63\u6587\u5BF9\u5E94\u7AE0\u8282\u627F\u8F7D\u8BE5\u7EF4\u5EA6\u5185\u5BB9" }));
  }
  const mentioned = [...md.matchAll(/FR-\d{3}/g)].map((m) => m[0]);
  const mentionedSet = new Set(mentioned);
  for (const fr of mentionedSet)
    if (!frIds.includes(fr))
      issues.push(issue2("R-S5", true, { severity: "warning", human_hint: `\u6B63\u6587\u5F15\u7528\u4E86\u4E0D\u5728 force_rules \u4E2D\u7684 FR-ID ${fr}\uFF08\u8B66\u544A\uFF0C\u4E0D\u963B\u585E\uFF09`, fix_direction: "\u4FDD\u8BC1 force_rules \u4E2D fr_id \u4E0E\u6B63\u6587\u5F15\u7528\u4E00\u81F4" }));
  for (const fr of frIds)
    if (!mentionedSet.has(fr))
      issues.push(issue2("R-S5", false, { human_hint: `\u5951\u7EA6 FR ${fr} \u672A\u5728\u6B63\u6587\u4E2D\u88AB\u63D0\u53CA`, fix_direction: "\u5728\u6B63\u6587\u5BF9\u5E94\u4F4D\u7F6E\u5F15\u7528\uFF0C\u6216\u786E\u8BA4\u5176\u5E94\u5220\u9664", severity: "warning" }));
  if (ctx.pendingDeferredToSpec) {
    const pendSection = sectionText("\u5F85\u5B9A\u4E8B\u9879");
    for (const pe of ctx.pendingDeferredToSpec)
      if (!pendSection.includes(pe))
        issues.push(issue2("R-S4", false, { human_hint: `\u5F85\u5B9A\u4E8B\u9879\u7AE0\u8282\u672A\u5305\u542B deferred_to_spec \u9879 ${pe}`, fix_direction: "\u628A\u6302\u8D77\u9879\u5199\u5165\u300A\u5F85\u5B9A\u4E8B\u9879\u300B\u7AE0\u8282" }));
  }
  if (ctx.confirmedContextDiscoveries && ctx.confirmedContextDiscoveries.length) {
    const rippleSection = sectionText("\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09");
    for (const d of ctx.confirmedContextDiscoveries) {
      const key = d.discovery_id || d.content;
      if (!rippleSection.includes(d.discovery_id) && !rippleSection.includes(d.content))
        issues.push(issue2("R-S7", false, {
          human_hint: `P0 \u5DF2\u786E\u8BA4\u7684\u6D9F\u6F2A\u53D1\u73B0 ${d.discovery_id} \u672A\u5728\u300A\u65E2\u6709\u4EE3\u7801\u5173\u8054\uFF08\u6D9F\u6F2A\u53D1\u73B0\uFF09\u300B\u7AE0\u8282\u8BB0\u5F55`,
          fix_direction: "\u628A\u8BE5\u53D1\u73B0\uFF08\u542B discovery_id \u4E0E\u5185\u5BB9\u3001\u51FA\u5904\uFF09\u5199\u5165\u6D9F\u6F2A\u7AE0\u8282\uFF0C\u52A8\u6001\u6269\u5145\u65E2\u6709\u4EE3\u7801\u903B\u8F91"
        }));
    }
  }
  if (ctx.glossaryV1 && ctx.businessEntities) {
    const g = checkGlossaryConsistency(sectionText("\u672F\u8BED\u8868"), ctx.glossaryV1, ctx.businessEntities);
    for (const e of g.errors) issues.push(issue2("R-S6", false, { human_hint: e, fix_direction: "\u540C\u6B65\u672F\u8BED\u8868\u7AE0\u8282\u4E0E glossary_v1" }));
    for (const w of g.warnings) issues.push(issue2("R-S6", false, { human_hint: w, severity: "warning" }));
  }
  return collect(issues);
}

// src/validate/validators/delivery.ts
function validateDelivery(raw, ctx) {
  const parsed = deliveryOutputSchema.safeParse(raw);
  if (!parsed.success) {
    return collect([
      issue2("DELIVERY-SCHEMA", false, {
        human_hint: "\u4EA4\u4ED8\u6E05\u5355\u4E0D\u7B26\u5408 Schema\uFF08\u8BE6\u89C1\u4FEE\u6B63\u8BF4\u660E\uFF09",
        fix_direction: describeSchemaError(parsed.error.issues, raw)
      })
    ]);
  }
  const o = parsed.data;
  const issues = [];
  const allAnchors = /* @__PURE__ */ new Set([...ctx.taskIds.map((t) => `task-pass/${t}`), ...ctx.caseIds]);
  for (const item of o.checklist) {
    const hasAnchor = /task-pass\/T-\d{3}|C-\d{3}/.test(item.evidence);
    if (!hasAnchor)
      issues.push(issue2("DELIVERY-EVIDENCE", false, {
        human_hint: `checklist ${item.item_id} \u7684 evidence \u672A\u5F15\u7528\u53EF\u6838\u67E5\u951A\u70B9\uFF08task-pass/T-xxx \u6216 C-xxx\uFF09`,
        fix_direction: "evidence \u5199\u660E\u5F15\u7528\u7684 task-pass \u6807\u7B7E\u6216 C-xxx \u7528\u4F8B\u53F7"
      }));
  }
  for (const t of ctx.taskIds) {
    const ref = `task-pass/${t}`;
    if (!o.checklist.some((c) => c.evidence.includes(ref)))
      issues.push(issue2("DELIVERY-COVERAGE", false, {
        human_hint: `\u4EA4\u4ED8\u6E05\u5355\u672A\u542B\u4EFB\u52A1 ${t} \u7684 task-pass \u8BC1\u636E`,
        fix_direction: "\u4E3A\u6BCF\u4E2A\u4EFB\u52A1\u8865\u4E00\u6761\u5F15\u7528\u5176 task-pass \u6807\u7B7E\u7684 checklist \u9879"
      }));
  }
  return collect(issues);
}

// src/engine/defaults.ts
import { execSync } from "node:child_process";
import { promises as fs5, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join as join5 } from "node:path";
init_test();

// src/render/renderer.ts
var RenderError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "RenderError";
  }
};
var APPENDIX_MARKER = "### CORRECTION-APPENDIX";
var VAR_RE = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;
var SYSTEM_VARS = /* @__PURE__ */ new Set(["correction_context", "retry_attempt", "retry_max"]);
function defaultEstimate(text) {
  return Math.ceil(text.length / 2);
}
function extractVariables(raw) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  for (const m of raw.matchAll(VAR_RE)) {
    const name = m[1];
    if (!seen.has(name)) {
      seen.add(name);
      out.push(name);
    }
  }
  return out;
}
function splitTemplate(raw) {
  const idx = raw.indexOf(APPENDIX_MARKER);
  if (idx === -1) return { body: raw, appendix: "" };
  const body = raw.slice(0, idx);
  const appendix = raw.slice(idx + APPENDIX_MARKER.length);
  return { body, appendix };
}
function replaceVars(text, vars, system) {
  return text.replace(VAR_RE, (_m, name) => {
    if (name in vars) return vars[name];
    if (name in system) return system[name];
    return `{{${name}}}`;
  });
}
function renderTemplate(raw, vars = {}, opts = {}) {
  const { body, appendix } = splitTemplate(raw);
  const isRetry = !!opts.retry && opts.retry.attempt > 0;
  const scope = isRetry ? body + "\n" + appendix : body;
  const missing = extractVariables(scope).filter(
    (v) => !SYSTEM_VARS.has(v) && !(v in vars)
  );
  if (missing.length) {
    throw new RenderError(`\u7F3A\u5931\u53D8\u91CF: ${missing.join(", ")}`);
  }
  const system = {};
  if (isRetry && opts.retry) {
    system.correction_context = JSON.stringify(opts.retry.errors ?? [], null, 2);
    system.retry_attempt = String(opts.retry.attempt);
    system.retry_max = String(opts.retry.max);
  }
  let out = replaceVars(body, vars, system);
  if (isRetry && appendix.trim().length > 0) {
    const app = replaceVars(appendix, vars, system);
    out = `${out}
${APPENDIX_MARKER}${app}`;
  }
  const estimate = opts.estimateTokens ?? defaultEstimate;
  if (opts.tokenLimit !== void 0 && estimate(out) > opts.tokenLimit) {
    throw new RenderError(
      `\u6E32\u67D3\u540E token \u4F30\u7B97 ${estimate(out)} \u8D85\u8FC7\u4E0A\u9650 ${opts.tokenLimit}`
    );
  }
  return out;
}

// src/engine/defaults.ts
var DIMS = ["\u8F93\u5165\u5951\u7EA6", "\u5904\u7406\u903B\u8F91", "\u8F93\u51FA\u683C\u5F0F", "\u5931\u8D25\u5F02\u5E38", "\u5173\u8054\u5F71\u54CD", "UI\u7EA6\u675F"];
var EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
function safeGit(layout, args) {
  try {
    return execSync(`git ${args}`, { cwd: layout.projectRoot, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}
function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}
function readTaskListSync(layout) {
  return readJson(join5(layout.tasks, "TASK_LIST.json"));
}
function readStateSync(layout) {
  return readJson(layout.state) ?? {};
}
function readContractFRs(layout) {
  const c = readJson(join5(layout.contracts, "CONTRACT_v1.json"));
  if (!c) return [];
  const fromForce = (c.force_rules ?? []).map((f) => typeof f === "string" ? f : f.fr_id).filter(Boolean);
  const fromFR = (c.FR ?? []).map((f) => f.id ?? f.fr_id).filter(Boolean);
  return Array.from(/* @__PURE__ */ new Set([...fromForce, ...fromFR]));
}
function serializeForceRules(frs) {
  return (frs ?? []).map((f) => {
    if (typeof f === "string") return f;
    if (f && typeof f === "object" && f.fr_id) {
      const rule = typeof f.rule === "string" ? f.rule : "";
      return rule ? `${f.fr_id}: ${rule}` : f.fr_id;
    }
    return JSON.stringify(f);
  }).join("\n");
}
function contextVarsFor(template, layout, st) {
  const contract = readJson(join5(layout.contracts, "CONTRACT_v1.json")) ?? {};
  const taskList = readTaskListSync(layout);
  const curTask = taskList?.tasks.find((t) => t.id === st?.current_task);
  const ir = st?.initial_request ?? "\uFF08\u672A\u63D0\u4F9B\uFF0C\u8BF7\u5728 flow_init \u65F6\u7ED9\u51FA\uFF09";
  switch (template) {
    case "phase0_question.txt": {
      const p0 = st.p0 ?? {};
      const rounds = p0.rounds ?? 0;
      return {
        initial_request: ir ?? "\uFF08\u7528\u6237\u5C1A\u672A\u63D0\u4F9B\u9700\u6C42\u63CF\u8FF0\uFF1A\u8BF7\u5728\u9996\u95EE\u4E2D\u5148\u8BF7\u7528\u6237\u7B80\u8981\u63CF\u8FF0\u8981\u5F00\u53D1\u4EC0\u4E48\uFF09",
        interview_state: p0.awaiting_answer === true ? "\uFF08\u5F53\u524D\u6709\u4E00\u8F6E\u95EE\u9898\u63D0\u6848\u5DF2\u63D0\u4EA4\u3001\u6B63\u5728\u7B49\u5F85\u7528\u6237\u56DE\u7B54\uFF1A\u8BF7\u52FF\u63D0\u4EA4\u65B0\u63D0\u6848\uFF0C\u628A\u95EE\u9898\u5448\u73B0\u7ED9\u7528\u6237\u5E76\u505C\u6B62\uFF0C\u5F85\u7528\u6237\u56DE\u590D\u540E\u8C03\u7528 flow_answer \u8BB0\u5F55\u5176\u771F\u5B9E\u7B54\u6848\uFF09" : "\uFF08\u53EF\u63D0\u4EA4\u65B0\u4E00\u8F6E\u95EE\u9898\u63D0\u6848\uFF1B\u63D0\u4EA4\u540E\u5F15\u64CE\u4F1A\u8FDB\u5165\u7B49\u5F85\u56DE\u7B54\u72B6\u6001\uFF09",
        qa_window: rounds === 0 ? "\uFF08\u9996\u8F6E\u8BBF\u8C08\uFF09" : `\uFF08\u7B2C ${rounds + 1} \u8F6E\uFF1B\u4E0A\u4E00\u5DF2\u63A5\u53D7\u8F6E\u6B21 round=${rounds}\uFF09`,
        covered_dimensions: (p0.covered_dimensions ?? []).length ? (p0.covered_dimensions ?? []).join("/") : DIMS.join("/"),
        asked_questions_digest: (p0.questions ?? []).length ? (p0.questions ?? []).map(
          (q) => `R${q.round}\u300C${q.question}\u300D\u2192 \u7528\u6237\u9009 ${q.user_choice ?? "\u81EA\u7531\u6587\u672C"}${q.chosen_label ? `\uFF08${q.chosen_label}\uFF09` : ""}${q.user_quote ? ` \u539F\u8BDD\uFF1A${q.user_quote}` : ""}`
        ).join("\n") : "\uFF08\u6682\u65E0\uFF09",
        pending_explanations: (p0.pendingOpen ?? []).length ? (p0.pendingOpen ?? []).join("\n") : "\uFF08\u65E0\uFF09",
        glossary: (p0.glossaryConfirmed ?? []).length ? (p0.glossaryConfirmed ?? []).map((g) => g.term).join("/") : "\uFF08\u6682\u65E0\uFF09",
        context_digest: buildCodeContextDigest(layout)
      };
    }
    case "phase0_specgen.txt": {
      const p0 = st.p0 ?? {};
      const qa = (p0.questions ?? []).map(
        (q) => `R${q.round} \u95EE\uFF1A${q.question}
  \u7528\u6237\u88C1\u5B9A\uFF1A${q.user_choice ?? "\u81EA\u7531\u6587\u672C"}${q.chosen_label ? `\uFF08${q.chosen_label}\uFF09` : ""}${q.user_quote ? ` \u539F\u8BDD\uFF1A${q.user_quote}` : ""}${q.covered_dimension ? `\uFF08\u7EF4\u5EA6\uFF1A${q.covered_dimension}\uFF09` : ""}${(q.facts ?? []).length ? ` \u5DF2\u786E\u8BA4\u4E8B\u5B9E\uFF1A${q.facts.map((f) => `${f.fact_id}=${f.content}`).join("\uFF1B")}` : ""}${q.facts_confirmed === false ? "  \u3010\u8BE5\u8F6E\u62DF\u8BAE\u4E8B\u5B9E\u672A\u83B7\u786E\u8BA4\uFF08\u7528\u6237\u672A\u9009\u63A8\u8350\u9879/\u81EA\u7531\u6587\u672C\u56DE\u7B54\uFF09\uFF0C\u4E0D\u5F97\u4F5C\u4E3A\u5DF2\u786E\u8BA4\u4E8B\u5B9E\u3011" : ""}`
      ).join("\n");
      return {
        initial_request: ir,
        full_facts: qa ? "\uFF08\u4EE5\u8BBF\u8C08\u5404\u8F6E\u786E\u8BA4\u4E8B\u5B9E\u4E0E\u7ED3\u8BBA\u4E3A\u51C6\uFF0C\u89C1 full_qa_log\uFF09" : "\uFF08\u4EE5\u521D\u59CB\u9700\u6C42\u4E0E\u8BBF\u8C08\u7ED3\u8BBA\u4E3A\u51C6\uFF09",
        full_qa_log: qa || "\uFF08\u65E0\uFF09",
        rejected_options: "\uFF08\u89C1\u5404\u8F6E options \u4E0E recommendation \u4E2D\u88AB\u62D2\u9009\u9879\uFF09",
        pending_explanations: (p0.pendingOpen ?? []).length ? (p0.pendingOpen ?? []).join("\n") : "\uFF08\u65E0\uFF09",
        context_digest: buildCodeContextDigest(layout),
        confirmed_ripples: (p0.contextDiscoveries ?? []).length ? JSON.stringify(p0.contextDiscoveries, null, 2) : "\uFF08\u65E0\uFF09"
      };
    }
    case "phase1_split.txt":
      return {
        contract_json: JSON.stringify(contract, null, 2),
        force_rules_list: serializeForceRules(contract.force_rules),
        module_name: st?.module ?? "module",
        glossary_core: "\uFF08\u65E0\uFF09"
      };
    case "phase2_build.txt":
      return {
        task_json: JSON.stringify(curTask ?? {}),
        interface_signatures: "\uFF08\u65E0\uFF09",
        force_rules: serializeForceRules(contract.force_rules),
        repo_conventions: "\u4F7F\u7528 git \u63D0\u4EA4\uFF1B\u53EF\u8FD0\u884C npm test / \u76F8\u5173\u6D4B\u8BD5\u547D\u4EE4\u81EA\u68C0",
        failure_context: "\uFF08\u9996\u8F6E\uFF09",
        glossary_slice: "\uFF08\u65E0\uFF09"
      };
    case "phase3_testdata.txt":
      return {
        task_json: JSON.stringify(curTask ?? {}),
        assertion_json: "\uFF08\u65E0\uFF09",
        force_rules: serializeForceRules(contract.force_rules),
        existing_regression: readExistingRegressionDigest(layout)
      };
    case "phase4_delivery.txt":
      return {
        tasks_status: JSON.stringify((taskList?.tasks ?? []).map((t) => ({ id: t.id, status: t.status ?? "todo" }))),
        test_reports_digest: "\uFF08\u89C1\u6D4B\u8BD5\u62A5\u544A\uFF09",
        contract_json: JSON.stringify(contract, null, 2),
        pending_explanations: "\uFF08\u65E0\uFF09"
      };
    default:
      return {};
  }
}
async function persistSpecgen(layout, md) {
  await fs5.mkdir(layout.specs, { recursive: true });
  await fs5.mkdir(layout.contracts, { recursive: true });
  await fs5.writeFile(join5(layout.specs, "SPEC_v1.md"), md, "utf8");
  const ext = extractContract(md);
  if (!ext.ok || !ext.json) return { specWrote: true, contractWrote: false, frCount: 0 };
  await fs5.writeFile(join5(layout.contracts, "CONTRACT_v1.json"), JSON.stringify(ext.json, null, 2), "utf8");
  const frCount = (ext.json.force_rules ?? []).length + (ext.json.FR ?? []).length;
  return { specWrote: true, contractWrote: true, frCount };
}
function buildCodeContextDigest(layout) {
  const parts = [];
  try {
    const root = layout.projectRoot;
    const specFiles = [];
    try {
      specFiles.push(...readdirSync(layout.specs).filter((f) => f.endsWith(".md")));
    } catch {
    }
    if (specFiles.length) parts.push(`\u5386\u53F2 SPEC\uFF1A${specFiles.join(", ")}`);
    try {
      const idx = readRegressionIndexSync(layout);
      if (idx?.tasks?.length) parts.push(`\u5386\u53F2\u56DE\u5F52\u4EFB\u52A1\uFF1A${idx.tasks.map((t) => `${t.task_id}(${t.scripts.length} \u4E2A\u811A\u672C)`).join(", ")}`);
    } catch {
    }
    try {
      const top = readdirSync(root);
      const srcish = top.filter((p) => !p.startsWith(".") && p !== "node_modules" && p !== "dist" && p !== "tests" && p !== "test" && p !== "build");
      if (srcish.length) parts.push(`\u9879\u76EE\u9876\u5C42\uFF1A${srcish.slice(0, 20).join(", ")}`);
    } catch {
    }
  } catch {
  }
  return parts.length ? parts.join("\uFF1B") : "\uFF08\u672A\u53D1\u73B0\u65E2\u6709\u4EE3\u7801/\u5386\u53F2 SPEC\uFF0C\u89C6\u4E3A\u65B0\u5EFA\u9879\u76EE\uFF09";
}
function readExistingRegressionDigest(layout) {
  try {
    const idx = readRegressionIndexSync(layout);
    if (!idx?.tasks?.length) return "\uFF08\u6682\u65E0\u5386\u53F2\u56DE\u5F52\u811A\u672C\uFF0C\u672C\u4EFB\u52A1\u4E3A\u9996\u4E2A\u9700\u6C89\u6DC0\u56DE\u5F52\u8D44\u4EA7\u7684\u4EFB\u52A1\uFF09";
    return JSON.stringify(idx, null, 2);
  } catch {
    return "\uFF08\u6682\u65E0\u5386\u53F2\u56DE\u5F52\u811A\u672C\uFF09";
  }
}
function readRegressionIndexSync(layout) {
  const p = join5(layout.regression, "index.json");
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}
function ensureRegressionGitIgnored(layout) {
  const gi = join5(layout.projectRoot, ".gitignore");
  const line = "tests/regression/";
  try {
    let cur = "";
    try {
      cur = readFileSync(gi, "utf8");
    } catch {
    }
    if (cur.split("\n").some((l) => l.trim() === line)) return;
    const next = cur.endsWith("\n") || cur === "" ? cur + line + "\n" : cur + "\n" + line + "\n";
    writeFileSync(gi, next, "utf8");
  } catch {
  }
}
function createDefaultDeps(projectRoot, opts = {}) {
  const layout = adocsLayout(projectRoot);
  const promptsDir = opts.promptsDir ?? layout.prompts;
  const render = (template, vars = {}, retry) => {
    const raw = readFileSync(join5(promptsDir, template), "utf8");
    const st = readStateSync(layout) ?? {};
    const fill = { ...contextVarsFor(template, layout, st), ...vars };
    return renderTemplate(raw, fill, retry ? { retry } : void 0);
  };
  const buildContext = (phase, lay = layout) => {
    const st = readStateSync(lay) ?? {};
    switch (phase) {
      case "P0_ALIGN": {
        const p0 = st.p0 ?? {};
        return {
          p0_step: st.p0_step ?? "question",
          historyQuestions: (p0.questions ?? []).map((q) => q.question ?? ""),
          previousAcceptedRound: p0.rounds ? p0.rounds : null,
          answersLog: p0.answersLog ?? "",
          glossaryExisting: (p0.glossaryConfirmed ?? []).map((g) => ({ term: g.term, aliases: g.aliases ?? [], biz_desc: g.biz_desc ?? "" })),
          coveredDimensions: p0.covered_dimensions ?? [],
          noNewFactRounds: p0.noNewFactRounds ?? 0,
          pendingOpen: p0.pendingOpen ?? [],
          // 涟漪检测：P0 已确认的既有代码关联（R-S7 对账）
          confirmedContextDiscoveries: p0.contextDiscoveries ?? []
        };
      }
      case "P2_BUILD": {
        const taskList = readTaskListSync(lay);
        const cur = st.current_task;
        const task = taskList?.tasks.find((t) => t.id === cur);
        const base = st.p2_base_commit && st.p2_base_commit !== "" ? st.p2_base_commit : EMPTY_TREE;
        const isAdocs = (p) => p === ".adocs" || p.startsWith(".adocs/");
        const isRegression = (p) => p === "tests/regression" || p.startsWith("tests/regression/");
        const notAdocs = (p) => Boolean(p) && !isAdocs(p) && !isRegression(p);
        const committed = safeGit(lay, `diff --name-only ${base} HEAD`).split("\n").filter(notAdocs);
        const staged = safeGit(lay, "diff --cached --name-only").split("\n").filter(notAdocs);
        const unstaged = safeGit(lay, "diff --name-only").split("\n").filter(notAdocs);
        const untracked = safeGit(lay, "ls-files --others --exclude-standard").split("\n").filter(notAdocs);
        const gitAll = Array.from(/* @__PURE__ */ new Set([...committed, ...staged, ...unstaged, ...untracked]));
        return {
          current_task: cur,
          exit_criteria: task?.exit_criteria ? [task.exit_criteria].flat() : readContractFRs(lay),
          affected_files_hint: task?.affected_files_hint ?? [],
          git_diff_names: gitAll,
          git_new_files: [],
          gate: { skipped: true }
        };
      }
      case "P3_TEST":
        return { exit_criteria: readContractFRs(lay), requiredFields: [] };
      case "P4_DELIVER": {
        const taskList = readTaskListSync(lay);
        const cases = st.p3_cases ?? [];
        return {
          taskIds: (taskList?.tasks ?? []).map((t) => t.id),
          caseIds: cases,
          contractFRs: readContractFRs(lay)
        };
      }
      default:
        return {};
    }
  };
  const validate = (phase, output, ctx) => {
    const isSpecgen = phase === "P0_ALIGN" && (ctx?.p0_step ?? "question") === "specgen";
    let out = output;
    if (typeof out === "string" && !isSpecgen) {
      try {
        out = JSON.parse(out);
      } catch {
      }
    }
    switch (phase) {
      case "P0_ALIGN":
        return ctx?.p0_step === "specgen" ? validateSpecgen(extractSpecMarkdown(out), {
          pendingDeferredToSpec: readStateSync(layout).p0?.deferredToSpec ?? [],
          confirmedContextDiscoveries: readStateSync(layout).p0?.contextDiscoveries ?? []
        }) : validateQuestion(out, ctx ?? {});
      case "P1_SPLIT":
        return validateSplit(out, { contractFRs: readContractFRs(layout) });
      case "P2_BUILD":
        return validateBuild(out, ctx ?? {});
      case "P3_TEST":
        return validateTestdata(out, ctx ?? {});
      case "P4_DELIVER":
        return validateDelivery(out, ctx ?? {});
      default:
        return { passed: true, errors: [], warnings: [], correctionBag: [] };
    }
  };
  const onTagTaskPass = (taskId) => {
    safeGit(layout, `tag task-pass/${taskId}`);
  };
  const onCleanupReset = () => {
    safeGit(layout, "reset --hard");
    safeGit(layout, "clean -fd");
  };
  const onPhaseEnter = (phase) => {
    if (phase === "P2_BUILD") {
      const head = safeGit(layout, "rev-parse HEAD");
      if (head) {
        const raw = readFileSync(layout.state, "utf8");
        const st = JSON.parse(raw);
        st.p2_base_commit = head;
        writeFileSync(layout.state, JSON.stringify(st, null, 2));
      }
    }
  };
  const onTestPass = async (taskId, output) => {
    await writeTestReport(layout, taskId, output);
    const scripts = Array.isArray(output?.scripts) && output.scripts.length ? output.scripts : buildDefaultRegressionScripts(taskId, output);
    const written = await writeRegressionScripts(layout, taskId, scripts);
    ensureRegressionGitIgnored(layout);
    await upsertRegressionIndex(layout, {
      task_id: taskId,
      scripts: written,
      report_path: `test/reports/${taskId}_report.json`,
      assertions_path: `tasks/assertions/${taskId}_assertions.json`,
      passed_at: (/* @__PURE__ */ new Date()).toISOString()
    });
  };
  return { render, validate, buildContext, onTagTaskPass, onCleanupReset, onPhaseEnter, onTestPass };
}

// src/engine/engine.ts
function deriveChoiceFromText(text) {
  const t = (text ?? "").trim();
  const m = t.match(/^([AaBb])\b/);
  if (m) return m[1].toUpperCase();
  return null;
}
var FlowEngine = class {
  layout;
  deps;
  constructor(projectRoot, deps = {}) {
    this.layout = adocsLayout(projectRoot);
    this.deps = { ...createDefaultDeps(projectRoot), ...deps };
  }
  async init(module, opts = {}) {
    await ensureAdocsDirs(this.layout);
    const existing = await readState(this.layout);
    if (existing) {
      if (opts.initial_request) {
        const { promises: fs7 } = await import("node:fs");
        const st2 = JSON.parse(await fs7.readFile(this.layout.state, "utf8"));
        st2.initial_request = opts.initial_request;
        await fs7.writeFile(this.layout.state, JSON.stringify(st2, null, 2), "utf8");
      }
      return;
    }
    await appendState(this.layout, "P0_ALIGN", "flow_init");
    const { promises: fs6 } = await import("node:fs");
    const path = this.layout.state;
    const raw = await fs6.readFile(path, "utf8");
    const st = JSON.parse(raw);
    st.module = module;
    st.phase = "P0_ALIGN";
    st.p0_step = "question";
    st.p0 = {};
    st.current_task = null;
    st.task_queue = [];
    st.task_cursor = 0;
    st.frozen_reason = void 0;
    st.initial_request = opts.initial_request ?? null;
    await fs6.writeFile(path, JSON.stringify(st, null, 2), "utf8");
  }
  async patchState(patch, note) {
    const { promises: fs6 } = await import("node:fs");
    const path = this.layout.state;
    const raw = await fs6.readFile(path, "utf8");
    const st = JSON.parse(raw);
    for (const [k, v] of Object.entries(patch)) {
      const parts = k.split(".");
      let cur = st;
      for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i];
        if (cur[p] === void 0 || cur[p] === null || typeof cur[p] !== "object" || Array.isArray(cur[p])) cur[p] = {};
        cur = cur[p];
      }
      cur[parts[parts.length - 1]] = v;
    }
    if (note) st.history = [...st.history ?? [], { ts: (/* @__PURE__ */ new Date()).toISOString(), note }];
    await fs6.writeFile(path, JSON.stringify(st, null, 2), "utf8");
  }
  async status() {
    const st = await readState(this.layout);
    if (!st) throw new Error("flow \u672A\u521D\u59CB\u5316\uFF1A\u8BF7\u5148 flow_init");
    return {
      phase: st.phase ?? st.current_phase,
      current_task: st.current_task ?? null,
      module: st.module ?? "",
      retry_count: st.retry_count ?? 0,
      task_fail_streak: st.task_fail_streak ?? 0,
      task_queue: st.task_queue ?? [],
      task_cursor: st.task_cursor ?? 0,
      history_len: (st.history ?? []).length,
      frozen_reason: st.frozen_reason
    };
  }
  /** 返回当前阶段应下发的指令包（render 注入）。 */
  async next(overrides) {
    const st = await readState(this.layout);
    if (!st) throw new Error("flow \u672A\u521D\u59CB\u5316");
    if ((st.phase ?? st.current_phase) === "FROZEN") throw new Error("\u6D41\u7A0B\u5DF2\u51BB\u7ED3\uFF08FROZEN\uFF09\uFF0C\u9700\u4EBA\u5DE5\u89E3\u51BB");
    const phase = st.phase ?? st.current_phase;
    const spec = PHASE_SPECS[phase];
    const ctx = this.deps.buildContext?.(phase, this.layout) ?? {};
    const template = phase === "P0_ALIGN" && (st.p0_step ?? "question") === "specgen" ? "phase0_specgen.txt" : spec.template;
    const attempt = (st.retry_count ?? 0) + 1;
    const md = this.deps.render(
      template,
      overrides?.renderVars ?? {},
      attempt > 1 ? { attempt, max: RETRY_THRESHOLD, errors: st.last_errors ?? [] } : void 0
    );
    const packetId = `${phase}-${spec.node}-${st.p0?.rounds ?? 0}-${attempt}`;
    return buildPacket({
      packet_id: packetId,
      phase,
      instruction_md: md,
      output_schema_json: {},
      validation_rules: [spec.validator],
      retry: attempt > 1 ? {
        attempt,
        max: RETRY_THRESHOLD,
        last_errors: (st.last_errors ?? []).map((e) => ({ rule: e.rule, human_hint: e.human_hint ?? e.rule, fix_direction: e.fix_direction ?? "" }))
      } : void 0
    });
  }
  /**
   * 提交当前阶段产出：校验 → 两级计数 → 推进/重试/冻结。
   * 返回 { passed, bag, envelope? }：passed=false 时 envelope 为携带纠错包的下一轮指令包。
   */
  async submit(output) {
    const st = await readState(this.layout);
    if (!st) throw new Error("flow \u672A\u521D\u59CB\u5316");
    if ((st.phase ?? st.current_phase) === "FROZEN") throw new Error("\u6D41\u7A0B\u5DF2\u51BB\u7ED3");
    const phase = st.phase ?? st.current_phase;
    const isSpecgen = phase === "P0_ALIGN" && (st.p0_step ?? "question") === "specgen";
    let out = output;
    if (typeof out === "string" && !isSpecgen) {
      try {
        out = JSON.parse(out);
      } catch {
      }
    }
    if (phase === "P0_ALIGN") {
      const step = st.p0_step ?? "question";
      const ctx2 = this.deps.buildContext?.(phase, this.layout) ?? {};
      const result2 = step === "specgen" ? this.deps.validate(phase, out, { ...ctx2, p0_step: "specgen" }) : this.deps.validate(phase, out, { ...ctx2, p0_step: "question" });
      if (!result2.passed) {
        const prev2 = { retry_count: st.retry_count ?? 0, task_fail_streak: st.task_fail_streak ?? 0 };
        const nxt = onFailure(prev2);
        await this.patchState({
          retry_count: nxt.state.retry_count,
          task_fail_streak: nxt.state.task_fail_streak,
          last_errors: result2.correctionBag
        });
        if (nxt.action === "frozen") {
          await this.patchState({ phase: "FROZEN", frozen_reason: nxt.reason });
          return { passed: false, result: result2 };
        }
        if (nxt.action === "reset_context") this.deps.onCleanupReset?.();
        return { passed: false, result: result2, envelope: await this.next() };
      }
      await this.patchState({ retry_count: 0, last_errors: [] });
      if (step === "question") {
        if (st.p0?.awaiting_answer === true) {
          const bag = [
            {
              rule: "R-Q7",
              human_hint: '\u4E0A\u4E00\u8F6E\u95EE\u9898\u5C1A\u672A\u83B7\u5F97\u7528\u6237\u56DE\u7B54\uFF1A\u8BF7\u5148\u628A\u95EE\u9898\u539F\u6837\u5448\u73B0\u7ED9\u7528\u6237\u5E76\u505C\u6B62\u7B49\u5F85\u5176\u56DE\u590D\uFF1B\u7528\u6237\u56DE\u590D\u540E\u8C03\u7528 flow_answer(choice="A"/"B") \u8BB0\u5F55\u5176\u771F\u5B9E\u7B54\u6848\uFF0C\u5F15\u64CE\u624D\u4F1A\u628A\u8BE5\u8F6E\u4E8B\u5B9E/\u7ED3\u8BBA\u843D\u8D26\u3002\u4E25\u7981\u66FF\u7528\u6237\u4F5C\u7B54\u3001\u7F16\u9020 user_choice \u6216\u81EA\u884C\u63A8\u8FDB\u3002',
              fix_direction: "\u5411\u7528\u6237\u5C55\u793A\u95EE\u9898\u5E76\u7B49\u5F85\u56DE\u7B54 \u2192 \u8C03\u7528 flow_answer \u63D0\u4EA4\u7B54\u6848"
            }
          ];
          return {
            passed: false,
            result: {
              passed: false,
              errors: bag.map((e) => ({ rule: e.rule, passed: false, severity: "error", human_hint: e.human_hint, fix_direction: e.fix_direction })),
              warnings: [],
              correctionBag: bag
            }
          };
        }
        await this.patchState({ "p0.pending": out, "p0.awaiting_answer": true, "p0.awaiting_since": Date.now() });
        return { passed: true, result: result2 };
      }
      await persistSpecgen(this.layout, extractSpecMarkdown(out));
      await appendState(this.layout, "P1_SPLIT", "P0 specgen \u843D\u76D8 + CONTRACT \u62BD\u53D6");
      const rounds = (st.p0?.rounds ?? 0) + 1;
      await this.patchState({ phase: "P1_SPLIT", p0_step: void 0, "p0.rounds": rounds });
      return { passed: true, result: result2 };
    }
    const spec = PHASE_SPECS[phase];
    const ctx = this.deps.buildContext?.(phase, this.layout) ?? {};
    const result = this.deps.validate(phase, out, ctx);
    if (result.passed) {
      await this.patchState({ retry_count: 0, last_errors: [] });
      await this.advance(phase, out);
      return { passed: true, result };
    }
    const prev = { retry_count: st.retry_count ?? 0, task_fail_streak: st.task_fail_streak ?? 0 };
    const next = onFailure(prev);
    await this.patchState({
      retry_count: next.state.retry_count,
      task_fail_streak: next.state.task_fail_streak,
      last_errors: result.correctionBag
    });
    if (next.action === "frozen") {
      await this.patchState({ phase: "FROZEN", frozen_reason: next.reason });
      return { passed: false, result };
    }
    if (next.action === "reset_context") {
      this.deps.onCleanupReset?.();
    }
    const env = await this.next();
    return { passed: false, result, envelope: env };
  }
  /**
   * §5.1 P0 回答（真实用户交互入口）：记录用户对 pending 问题的实际选择，
   * 并把该轮事实/结论/词汇表落账；穷尽确认(A)则推进 specgen。
   *
   * 双门禁（R-Q7 + R-Q8）：
   * - R-Q7：问题未被回答前，submit 拒绝任何新提案；
   * - R-Q8：有会话访问能力时（opts.verifyUserReply），引擎直接读取真实会话，
   *   校验问题提出后确实存在一条用户消息，并用其原文推导真实选择——
   *   彻底杜绝「模型替用户作答」（弱模型曾连续 3 轮自答 A）。
   */
  async answer(choice, comment, opts) {
    const st = await readState(this.layout);
    if (!st) return { ok: false, error: "flow \u672A\u521D\u59CB\u5316" };
    if ((st.phase ?? st.current_phase) === "FROZEN") return { ok: false, error: "\u6D41\u7A0B\u5DF2\u51BB\u7ED3" };
    if ((st.p0_step ?? "question") !== "question") return { ok: false, error: "\u5F53\u524D\u4E0D\u5728\u8BBF\u8C08\u63D0\u95EE\u73AF\u8282" };
    if (st.p0?.awaiting_answer !== true || !st.p0?.pending)
      return { ok: false, error: "\u5F53\u524D\u6CA1\u6709\u7B49\u5F85\u56DE\u7B54\u7684\u95EE\u9898\uFF08\u8BF7\u5148 flow_submit \u63D0\u4EA4\u95EE\u9898\u63D0\u6848\uFF09" };
    const awaitingSince = st.p0?.awaiting_since ?? 0;
    let userChoice = choice ?? null;
    let userQuote = (comment ?? "").slice(0, 500);
    if (opts?.verifyUserReply) {
      const reply = await opts.verifyUserReply(awaitingSince);
      if (!reply) {
        return {
          ok: false,
          error: "R-Q8\uFF1A\u5C1A\u672A\u68C0\u6D4B\u5230\u7528\u6237\u5728\u95EE\u9898\u63D0\u51FA\u540E\u7684\u771F\u5B9E\u56DE\u590D\uFF0C\u65E0\u6CD5\u8BB0\u5F55\u56DE\u7B54\u3002\u8BF7\u5148\u628A\u95EE\u9898\u539F\u6837\u5448\u73B0\u7ED9\u7528\u6237\u5E76\u505C\u6B62\uFF08finish: stop\uFF09\u7B49\u5F85\u5176\u56DE\u590D\uFF1B\u7528\u6237\u56DE\u590D\u540E\u518D\u8C03\u7528 flow_answer\u3002\u4E25\u7981\u66FF\u7528\u6237\u4F5C\u7B54\u3001\u7F16\u9020\u7528\u6237\u7B54\u6848\u6216\u81EA\u884C\u63A8\u8FDB\u3002"
        };
      }
      userQuote = (reply.text ?? "").slice(0, 500) || userQuote;
      userChoice = deriveChoiceFromText(reply.text) ?? null;
      if (comment && comment.trim() !== reply.text.trim()) userQuote = `${userQuote}\uFF08\u8865\u5145\uFF1A${comment.slice(0, 200)}\uFF09`;
    }
    const pending = st.p0.pending;
    if (pending.exhausted === true) {
      if (userChoice === "A") {
        await this.patchState({ p0_step: "specgen", "p0.awaiting_answer": false, "p0.pending": void 0, "p0.awaiting_since": void 0 });
        return { ok: true, advancedSpecgen: true, user_choice: "A", user_quote: userQuote };
      }
      await appendAnswersLog(this.layout, JSON.stringify({ round: (st.p0?.rounds ?? 0) + 1, note: `\u7528\u6237\u672A\u786E\u8BA4\u7A77\u5C3D${userQuote ? `\uFF1A${userQuote}` : "\uFF0C\u9700\u8C03\u6574"}` }));
      await this.patchState({ "p0.awaiting_answer": false, "p0.pending": void 0, "p0.last_round": void 0, "p0.awaiting_since": void 0 });
      return { ok: true, advancedSpecgen: false, user_choice: userChoice, user_quote: userQuote };
    }
    const round = (st.p0?.rounds ?? 0) + 1;
    await this.accumulateP0Round(pending, st.p0, { choice: userChoice, comment: userQuote });
    return { ok: true, round, advancedSpecgen: false, user_choice: userChoice, user_quote: userQuote };
  }
  /**
   * 已接受且用户已回答的访谈轮：累积 p0 记忆并写访谈留痕（§6.6）。
   * - user_choice 来自真实会话/用户真实选择，非模型自报；
   * - 拟议事实（new_facts）仅在用户所选 == 推荐选项时才算「已确认事实」，
   *   自由文本回答或选了非推荐项时不得记为已确认（防止 F-002「CLI」类污染）。
   */
  async accumulateP0Round(proposal, prevP0, ans) {
    const rounds = (prevP0?.rounds ?? 0) + 1;
    const dim = typeof proposal?.covered_dimension === "string" ? proposal.covered_dimension : "";
    const covered = new Set(prevP0?.covered_dimensions ?? []);
    if (dim) covered.add(dim);
    const userChoice = ans?.choice ?? null;
    const chosenLabel = userChoice ? proposal?.options?.[userChoice] ?? userChoice : null;
    const factsConfirmed = userChoice !== null && proposal?.recommendation !== void 0 && userChoice === proposal?.recommendation;
    const confirmedFacts = factsConfirmed && Array.isArray(proposal?.new_facts) ? proposal.new_facts : [];
    const noNew = confirmedFacts.length > 0 ? 0 : (prevP0?.noNewFactRounds ?? 0) + 1;
    const proposedDiscs = Array.isArray(proposal?.context_discoveries) ? proposal.context_discoveries : [];
    const prevDiscs = Array.isArray(prevP0?.contextDiscoveries) ? prevP0.contextDiscoveries : [];
    const confirmedDiscs = proposedDiscs.filter((d) => d?.needs_confirmation === false || factsConfirmed);
    const contextDiscoveries = [...prevDiscs, ...confirmedDiscs].map((d, i) => ({
      discovery_id: d?.discovery_id ?? `D-${String(i + 1).padStart(3, "0")}`,
      content: d?.content ?? "",
      source: d?.source ?? "",
      confirmed: d?.needs_confirmation === false || factsConfirmed
    }));
    const questions = [
      ...prevP0?.questions ?? [],
      {
        round: rounds,
        question: proposal?.question ?? "",
        covered_dimension: dim,
        recommendation: proposal?.recommendation ?? null,
        user_choice: userChoice,
        chosen_label: chosenLabel,
        user_quote: ans?.comment ?? null,
        facts: confirmedFacts,
        facts_confirmed: factsConfirmed
      }
    ];
    const pe = proposal?.pending_explanation_update ?? {};
    const open = new Set(prevP0?.pendingOpen ?? []);
    const toKey = (x) => typeof x === "string" ? x : x?.text ?? x?.id ?? JSON.stringify(x);
    for (const r of pe.resolved ?? []) open.delete(toKey(r));
    for (const d of pe.deferred ?? []) open.delete(toKey(d));
    for (const a of pe.added ?? []) open.add(toKey(a));
    const confirmed = [...prevP0?.glossaryConfirmed ?? []];
    for (const g of proposal?.glossary_update?.add ?? []) {
      if (g?.term && !confirmed.some((c) => c.term === g.term)) confirmed.push({ term: g.term, aliases: g.aliases ?? [], biz_desc: g.biz_desc ?? "" });
    }
    const line = JSON.stringify({
      round: rounds,
      question: proposal?.question ?? "",
      user_choice: userChoice,
      chosen_label: chosenLabel,
      user_quote: ans?.comment ?? null,
      facts_confirmed: factsConfirmed
    });
    const answersLog = (prevP0?.answersLog ?? "") + (prevP0?.answersLog ? "\n" : "") + line;
    const deferredToSpec = [...prevP0?.deferredToSpec ?? [], ...(pe.deferred ?? []).map(toKey)];
    await appendDecisionRound(this.layout, { round: rounds, ts: (/* @__PURE__ */ new Date()).toISOString(), branch: userChoice ?? proposal?.recommendation ?? "", note: proposal?.question });
    await appendAnswersLog(this.layout, line);
    await this.patchState({
      p0_step: "question",
      "p0.rounds": rounds,
      "p0.questions": questions,
      "p0.covered_dimensions": [...covered],
      "p0.noNewFactRounds": noNew,
      "p0.pendingOpen": [...open],
      "p0.glossaryConfirmed": confirmed,
      "p0.answersLog": answersLog,
      "p0.deferredToSpec": deferredToSpec,
      "p0.contextDiscoveries": contextDiscoveries,
      "p0.awaiting_answer": false,
      "p0.pending": void 0,
      "p0.awaiting_since": void 0,
      "p0.last_round": { ...proposal, user_choice: userChoice, user_quote: ans?.comment ?? null, facts_confirmed: factsConfirmed }
    });
  }
  /** §5.2 转移表：校验通过后推进阶段。 */
  async advance(phase, output) {
    switch (phase) {
      case "P0_ALIGN": {
        await appendState(this.layout, "P1_SPLIT", "P0 \u63A8\u8FDB\uFF08\u517C\u5BB9\u5206\u652F\uFF09");
        await this.patchState({ phase: "P1_SPLIT", p0_step: void 0 });
        break;
      }
      case "P1_SPLIT": {
        const existing = await readTaskList(this.layout);
        const submitted = Array.isArray(output?.tasks) ? output.tasks : Array.isArray(output) ? output : [];
        let final = existing;
        if (submitted.length > 0) {
          const prevById = new Map((existing?.tasks ?? []).map((t) => [t.id, t]));
          const tasks = submitted.map((t) => {
            const prev = prevById.get(t.id) ?? {};
            return {
              id: t.id,
              title: t.title,
              objective: t.objective,
              exit_criteria: Array.isArray(t.exit_criteria) ? t.exit_criteria : [t.exit_criteria],
              depends_on: t.depends_on ?? prev.depends_on ?? [],
              affected_files_hint: t.affected_files_hint ?? prev.affected_files_hint ?? [],
              status: prev.status ?? "todo"
            };
          });
          final = {
            meta: { version: (existing?.meta?.version ?? 0) + 1, generated_at: (/* @__PURE__ */ new Date()).toISOString() },
            tasks
          };
          await writeTaskList(this.layout, final);
        }
        const queue = (final?.tasks ?? []).map((t) => t.id);
        await appendState(this.layout, "P2_BUILD", "\u4EFB\u52A1\u6570\u7EC4\u8FC7\u6821\u9A8C");
        this.deps.onPhaseEnter?.("P2_BUILD");
        await this.patchState({ phase: "P2_BUILD", task_queue: queue, task_cursor: 0, current_task: queue[0] ?? null });
        break;
      }
      case "P2_BUILD": {
        const tid = (await readState(this.layout))?.current_task;
        if (tid) this.deps.onTagTaskPass?.(tid);
        await appendState(this.layout, "P3_TEST", `T-${tid} \u52A8\u4F5C\u62A5\u544A\u8FC7 R-B`);
        await this.patchState({ phase: "P3_TEST" });
        break;
      }
      case "P3_TEST": {
        const results = output?.results ?? [];
        const fails = results.filter((r) => r?.result !== "pass");
        if (fails.length > 0) {
          const st2 = await readState(this.layout);
          await appendState(this.layout, "P2_BUILD", `P3 \u6D4B\u8BD5\u5931\u8D25 ${fails.length} \u9879\uFF0C\u56DE\u9000\u91CD\u505A ${st2.current_task}`);
          await this.patchState({ phase: "P2_BUILD", task_fail_streak: (st2.task_fail_streak ?? 0) + 1 });
          return;
        }
        const st = await readState(this.layout);
        if (this.deps.onTestPass && st.current_task) {
          await this.deps.onTestPass(st.current_task, output);
        }
        const queue = st.task_queue ?? [];
        const cursor = (st.task_cursor ?? 0) + 1;
        if (cursor >= queue.length) {
          const cases = (output?.cases ?? []).map((c) => c.case_id);
          await appendState(this.layout, "P4_DELIVER", "\u672B\u4EFB\u52A1\u6D4B\u8BD5\u5168\u7EFF");
          await this.patchState({ phase: "P4_DELIVER", current_task: null, p3_cases: cases });
        } else {
          await appendState(this.layout, "P2_BUILD", `\u4E0B\u4E00\u4EFB\u52A1 ${queue[cursor]}`);
          this.deps.onPhaseEnter?.("P2_BUILD");
          await this.patchState({ phase: "P2_BUILD", task_cursor: cursor, current_task: queue[cursor] });
        }
        break;
      }
      case "P4_DELIVER": {
        break;
      }
    }
  }
  async freeze(reason = "\u7528\u6237\u663E\u5F0F\u51BB\u7ED3") {
    await this.patchState({ phase: "FROZEN", frozen_reason: reason });
  }
  /** flow_reset：归档 .adocs 后重建骨架（§5.6）。M5 负责归档复制；此处重置状态。 */
  async reset(module) {
    await ensureAdocsDirs(this.layout);
    await appendState(this.layout, "P0_ALIGN", "flow_reset");
    const { promises: fs6 } = await import("node:fs");
    const st = JSON.parse(await fs6.readFile(this.layout.state, "utf8"));
    Object.assign(st, {
      phase: "P0_ALIGN",
      p0_step: "question",
      p0: {},
      current_task: null,
      retry_count: 0,
      task_fail_streak: 0,
      task_queue: [],
      task_cursor: 0,
      frozen_reason: void 0,
      last_errors: [],
      module,
      // 全量软重置：旧需求种子一并清除，避免「重置后重新开始」仍残留上一轮需求
      initial_request: void 0
    });
    await fs6.writeFile(this.layout.state, JSON.stringify(st, null, 2), "utf8");
  }
  /** 导入任务队列（M1 store 写 TASK_LIST 后由 M5 调用）。 */
  async importTaskQueue() {
    const list = await readTaskList(this.layout);
    const queue = list?.tasks.map((t) => t.id) ?? [];
    await this.patchState({ task_queue: queue, task_cursor: 0, current_task: queue[0] ?? null });
  }
};

// src/sdk/client.ts
function payloadOf(c) {
  if (!c) return c;
  return c?.data?.data ?? c?.data ?? c;
}
var OCClient = class _OCClient {
  client;
  baseUrl;
  auth;
  clientPromise;
  constructor(opts = {}) {
    this.baseUrl = opts.baseUrl || process.env.OC_TEST_URL || "http://127.0.0.1:18005";
    this.auth = "Basic " + Buffer.from(`${opts.user || "op"}:${opts.pass || "op123"}`).toString("base64");
  }
  /**
   * 惰性创建 SDK 客户端：`@opencode-ai/sdk/v2/client` 改为动态 import，
   * 仅在真正派发执行时才加载。这样插件包的顶层模块对 @opencode-ai/sdk 零依赖，
   * 不会因宿主首次加载时尚未装好该包而导致整个插件静默加载失败。
   */
  async ensureClient() {
    if (!this.clientPromise) {
      this.clientPromise = import("@opencode-ai/sdk/v2/client").then((m) => m.createOpencodeClient({ baseUrl: this.baseUrl, headers: { Authorization: this.auth } })).catch((err) => {
        throw new Error(
          `\u6D3E\u53D1\u6267\u884C\u4F53\u4F9D\u8D56\u7684 @opencode-ai/sdk \u4E0D\u53EF\u7528\uFF08${err?.code ?? err?.message ?? err}\uFF09\u3002\u8BF7\u5728\u9879\u76EE .opencode/ \u4E0B\u6267\u884C \`npm install @opencode-ai/sdk\` \u540E\u91CD\u8BD5\uFF0C\u6216\u786E\u8BA4 opencode serve \u5DF2\u542F\u52A8\u3002`
        );
      });
    }
    return this.clientPromise;
  }
  async health() {
    const c = await this.ensureClient();
    const h = await c.v2.health.get();
    return payloadOf(h);
  }
  async createSession(directory, model) {
    const body = { location: { directory } };
    if (model) body.model = model;
    const c = await this.ensureClient();
    const r = await c.v2.session.create(body);
    const id = payloadOf(r)?.id;
    if (!id) throw new Error("createSession failed: " + JSON.stringify(r).slice(0, 300));
    return id;
  }
  async sendPrompt(sessionID, text) {
    const c = await this.ensureClient();
    const p = await c.v2.session.prompt({ sessionID, prompt: { text } });
    return payloadOf(p);
  }
  async listMessages(sessionID) {
    const c = await this.ensureClient();
    const m = await c.v2.session.messages({ sessionID });
    const data = payloadOf(m);
    return data?.messages ?? data ?? [];
  }
  async listPermissions(sessionID) {
    try {
      const c = await this.ensureClient();
      const r = await c.v2.session.permission.list({ sessionID });
      const data = payloadOf(r);
      return data?.permissions ?? data ?? [];
    } catch {
      return [];
    }
  }
  async approvePermission(requestID, reply = "always") {
    const c = await this.ensureClient();
    await c.v2.session.permission.reply({ requestID, reply }).catch(() => {
    });
  }
  static textOf(message) {
    if (!message) return "";
    if (typeof message.text === "string") return message.text;
    if (Array.isArray(message.content)) {
      return message.content.filter((c) => c?.type === "text" || c?.type === "output").map((c) => c.text ?? "").join("\n").trim();
    }
    return "";
  }
  static lastAssistant(messages) {
    const assistants = (messages ?? []).filter((m) => m?.type === "assistant" && typeof m?.finish === "string");
    if (assistants.length === 0) return void 0;
    return assistants.sort((a, b) => (b?.time?.created ?? 0) - (a?.time?.created ?? 0))[0];
  }
  /** 诊断用：末条 assistant 的 finish 原因与文本长度。 */
  static diagnose(messages) {
    const last = _OCClient.lastAssistant(messages);
    if (!last) return `no-finished-assistant (msgs=${messages?.length ?? 0})`;
    return `finish=${JSON.stringify(last.finish)} textLen=${_OCClient.textOf(last).length} msgs=${messages?.length ?? 0}`;
  }
  /**
   * 轮询直至末条 assistant 进入终态（finish 有值），期间按策略批复挂起权限。
   * - approveFilter 未提供：全部自动批复 always（P-a 简化态/测试用）。
   * - approveFilter 提供（P-b 范围放行）：仅对命中白名单的权限自动批复，其余留待人工弹出（ask）。
   */
  /** 非终态 finish 原因：模型只是发起了工具调用，server 还会继续跑工具并追加下一轮。 */
  static INCOMPLETE_FINISH = /* @__PURE__ */ new Set(["tool-calls", "tool_use", "function_call"]);
  /** runToCompletion 的返回：消息列表 + 是否因 P-b 越界权限被人工挂起。 */
  async runToCompletion(sessionID, opts = {}) {
    const timeout = opts.timeoutMs ?? 18e4;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const perms2 = await this.listPermissions(sessionID);
      for (const p of perms2) {
        if (p.status === "pending" || !p.status) {
          opts.onPermission?.(p);
          const allow = opts.approveFilter ? opts.approveFilter(p) : true;
          if (allow) await this.approvePermission(p.id ?? p.requestID, "always");
        }
      }
      const msgs = await this.listMessages(sessionID);
      const last = _OCClient.lastAssistant(msgs);
      if (last && !_OCClient.INCOMPLETE_FINISH.has(last.finish)) {
        return { messages: msgs, manualPending: false };
      }
      if (opts.approveFilter) {
        const hasManual = perms2.some((p) => {
          const isPending = p.status === "pending" || !p.status;
          return isPending && !opts.approveFilter(p);
        });
        if (hasManual) return { messages: msgs, manualPending: true };
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    const perms = await this.listPermissions(sessionID);
    const manualPending = opts.approveFilter ? perms.some((p) => (p.status === "pending" || !p.status) && !opts.approveFilter(p)) : false;
    return { messages: await this.listMessages(sessionID), manualPending };
  }
};

// src/engine/permission.ts
function argsText(p) {
  return JSON.stringify(p.args ?? {});
}
function matchWhitelist(p, wl) {
  if (!wl) return false;
  const tool2 = (p.tool ?? "").toLowerCase();
  const text = argsText(p);
  if ((tool2 === "edit" || tool2 === "write" || tool2 === "apply") && wl.editPrefixes) {
    return wl.editPrefixes.some((pre) => text.includes(pre));
  }
  if (tool2 === "bash" && wl.bashPrefixes) {
    return wl.bashPrefixes.some((pre) => text.includes(pre));
  }
  return false;
}
function makeApproveFilter(wl) {
  if (!wl) return void 0;
  return (p) => matchWhitelist(p, wl);
}

// src/engine/dispatch.ts
var DEFAULT_MODELS = [
  { id: "hy3-free", providerID: "opencode" }
];
function extractJson(text) {
  if (!text) return null;
  const candidates = [];
  candidates.push(text.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim());
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) candidates.push(fence[1].trim());
  const open = text.search(/[[{]/);
  if (open >= 0) {
    const closeCh = text[open] === "[" ? "]" : "}";
    const close = text.lastIndexOf(closeCh);
    if (close > open) candidates.push(text.slice(open, close + 1));
  }
  for (const c of candidates) {
    if (!c) continue;
    try {
      return { raw: c, parsed: JSON.parse(c) };
    } catch {
    }
  }
  return null;
}
var FlowDispatcher = class {
  constructor(opts) {
    this.opts = opts;
  }
  opts;
  makeClient() {
    if (this.opts.client) return this.opts.client;
    return new OCClient({ baseUrl: this.opts.baseUrl, user: this.opts.user, pass: this.opts.pass });
  }
  async dispatch(env) {
    const models = this.opts.models ?? DEFAULT_MODELS;
    let lastErr;
    for (const model of models) {
      const oc = this.makeClient();
      try {
        const sid = await oc.createSession(this.opts.directory, model);
        await oc.sendPrompt(sid, env.instruction_md);
        const { messages: msgs, manualPending } = await oc.runToCompletion(sid, {
          timeoutMs: this.opts.timeoutMs,
          approveFilter: makeApproveFilter(this.opts.permissionWhitelist)
        });
        const last = OCClient.lastAssistant(msgs);
        const raw = OCClient.textOf(last);
        if (!raw) {
          if (manualPending) {
            const err = new Error("P-b \u4EBA\u5DE5\u5F85\u6279\uFF1A\u5B50\u4F1A\u8BDD\u56E0\u8D8A\u754C\u6743\u9650\u88AB\u6302\u8D77\uFF0C\u9700\u4EBA\u5DE5\u5728 UI \u6279\u590D\u540E\u7EE7\u7EED");
            err.code = "HUMAN_REQUIRED";
            throw err;
          }
          throw new Error("\u5B50\u4F1A\u8BDD\u65E0\u4EA7\u51FA\uFF1A" + OCClient.diagnose(msgs));
        }
        const messages = msgs ?? [];
        let chosen = null;
        for (let i = messages.length - 1; i >= 0; i--) {
          const m = messages[i];
          if (m?.type !== "assistant") continue;
          const t = OCClient.textOf(m);
          if (!t) continue;
          const ex = extractJson(t);
          if (ex) {
            chosen = ex;
            break;
          }
        }
        if (!chosen) chosen = extractJson(raw);
        if (!chosen || chosen.parsed === void 0) {
          return { raw, parsed: raw, model };
        }
        return { raw: chosen.raw, parsed: chosen.parsed, model };
      } catch (e) {
        if (e?.code === "HUMAN_REQUIRED") throw e;
        lastErr = e;
        continue;
      }
    }
    throw new Error(`\u6D3E\u53D1\u5931\u8D25\uFF0C\u6240\u6709\u5019\u9009\u6A21\u578B\u5747\u4E0D\u53EF\u7528\uFF1A${lastErr?.message ?? "unknown"}`);
  }
};

// plugins/ar-flow/plugin.ts
import { join as join6 } from "node:path";
var tool = (t) => t;
function engine(dir) {
  return new FlowEngine(dir);
}
var CONTRACT_PROTECT = /\.adocs\/(contracts|tasks)\//;
var FREEZE_BLOCKED = /* @__PURE__ */ new Set(["edit", "write", "bash", "apply", "webfetch"]);
async function lastUserReplySince(client, sessionID, since) {
  if (!client || !sessionID) return null;
  try {
    const res = await client.session.messages({ path: { id: sessionID }, query: { limit: 50 } });
    const data = res?.data ?? res ?? [];
    let best = null;
    for (const m of data) {
      const info = m?.info ?? m;
      if (!info || info.role !== "user") continue;
      const at = info?.time?.created ?? 0;
      if (at < since) continue;
      const text = (m?.parts ?? []).filter((p) => p?.type === "text" && !p?.synthetic).map((p) => p.text ?? "").join("").trim();
      if (!best || at > best.at) best = { text, at };
    }
    return best;
  } catch {
    return null;
  }
}
function arFlowPlugin(input) {
  const dir = input?.directory ?? process.cwd();
  const client = input?.client;
  return {
    tool: {
      flow_init: tool({
        description: '\u521D\u59CB\u5316 ar-flow\uFF1A\u5728\u9879\u76EE .adocs/ \u5EFA\u7ACB\u6CBB\u7406\u8D44\u4EA7\u5BB9\u5668\uFF0C\u8FDB\u5165 P0_ALIGN\u3002\u82E5\u5DF2\u5B58\u5728\u5176\u4ED6\u6A21\u5757\u7684\u6D41\u7A0B\u72B6\u6001\uFF0C\u672C\u5DE5\u5177\u6309\u5E42\u7B49\u4FDD\u62A4\u4E0D\u8986\u76D6\uFF0C\u4F1A\u63D0\u793A\u6539\u7528 flow_reset\u3002\u3010\u8C03\u7528\u7EA6\u5B9A\u3011\u53C2\u6570\u540D\u4E3A `module` / `brief`\uFF0C\u76F4\u63A5 `flow_init(module="calc", brief="...")` \u4F20\u5165\uFF1B\u4E0D\u8981\u5305\u6210 `def={...}`\uFF08\u5F15\u64CE\u5DF2\u517C\u5BB9\u4E24\u79CD\u5199\u6CD5\uFF09\u3002',
        args: external_exports.object({ module: external_exports.string().describe("\u6A21\u5757\u540D"), brief: external_exports.string().optional().describe("\u7528\u6237\u539F\u59CB\u9700\u6C42\uFF08\u9996\u53E5\u8BDD\uFF09\uFF0C\u6CE8\u5165 P0 \u8BBF\u8C08\u4E0A\u4E0B\u6587") }),
        async execute(rawArgs) {
          const { module, brief } = unwrapArgs(rawArgs);
          const e = engine(dir);
          const before = await e.status().catch(() => null);
          await e.init(module, { initial_request: brief });
          const s = await e.status();
          if (before && (before.module !== module || before.phase !== "P0_ALIGN")) {
            return `\u5DF2\u5B58\u5728 flow\uFF08module=${before.module}, phase=${before.phase}\uFF09\uFF0Cflow_init \u6309\u5E42\u7B49\u4FDD\u62A4\u672A\u8986\u76D6\u65E2\u6709\u72B6\u6001\u3002\u82E5\u9700\u4E3A\u300C${module}\u300D\u4ECE\u96F6\u5F00\u59CB\uFF0C\u8BF7\u8C03\u7528 flow_reset(module="${module}")`;
          }
          return `flow \u5DF2\u521D\u59CB\u5316\uFF0Cphase=${s.phase} module=${s.module}`;
        }
      }),
      flow_status: tool({
        description: "\u8FD4\u56DE\u6D41\u7A0B\u72B6\u6001\u6458\u8981\uFF08\u8DE8\u4F1A\u8BDD\u7EED\u8DD1\u5165\u53E3\uFF09",
        args: external_exports.object({}),
        async execute() {
          const e = engine(dir);
          return JSON.stringify(await e.status(), null, 2);
        }
      }),
      flow_next: tool({
        description: "\u8FD4\u56DE\u4E0B\u4E00\u6761\u6307\u4EE4\u5305\uFF08\u542B\u6E32\u67D3\u540E\u7684\u63D0\u793A\u8BCD\u4E0E\u91CD\u8BD5\u72B6\u6001\uFF09\u3002\u6A21\u578B\u636E\u5176\u4EA7\u51FA\u540E\u8C03 flow_submit \u4EA4\u56DE",
        args: external_exports.object({}),
        async execute() {
          const e = engine(dir);
          const env = await e.next();
          return env.instruction_md;
        }
      }),
      flow_submit: tool({
        description: '\u4EA4\u56DE\u5F53\u524D\u9636\u6BB5\u4EA7\u51FA\u3002\u5F15\u64CE\u6821\u9A8C\uFF1B\u5931\u8D25\u5219\u8FD4\u56DE\u542B\u5177\u4F53\u5B57\u6BB5\u9519\u8BEF\u7684\u7EA0\u9519\u5305\u3002\u3010\u8C03\u7528\u7EA6\u5B9A\u3011\u53C2\u6570\u540D\u5C31\u662F `output`\uFF0C\u8BF7\u76F4\u63A5 `flow_submit(output={...})` \u4F20\u5165\u7ED3\u6784\u5316\u5BF9\u8C61\uFF1B\u4E0D\u8981\u5305\u6210 `def={output:{...}}`\uFF08\u5F15\u64CE\u5DF2\u517C\u5BB9\u4E24\u79CD\u5199\u6CD5\uFF0C\u4F46\u8BF7\u4F18\u5148\u7528 `output=` \u9876\u5C42\u53C2\u6570\uFF09\u3002output \u7684\u5F62\u72B6\u56E0\u9636\u6BB5\u800C\u5F02\uFF1A\u8BBF\u8C08(P0 question)\u9636\u6BB5\u4F20\u3010\u95EE\u9898\u63D0\u6848\u3011\u7ED3\u6784\u5316\u5BF9\u8C61\uFF08\u5982 {exhausted:false, question:"...", options:{A:"...",B:"..."}, recommendation:"A", ...}\uFF09\uFF1B\u63D0\u6848\u88AB\u63A5\u53D7\u540E\u5F15\u64CE\u8FDB\u5165\u300C\u7B49\u5F85\u7528\u6237\u56DE\u7B54\u300D\u72B6\u6001\uFF0C\u6B64\u65F6\u5FC5\u987B\u628A\u95EE\u9898\u5448\u73B0\u7ED9\u7528\u6237\u5E76\u505C\u6B62\u3001\u7B49\u5F85\u7528\u6237\u771F\u5B9E\u56DE\u590D\uFF0C\u518D\u8C03\u7528 flow_answer() \u8BB0\u5F55\u7B54\u6848\uFF08\u5F15\u64CE\u81EA\u52A8\u8BFB\u53D6\u4F1A\u8BDD\u539F\u6587\uFF0C\u65E0\u9700\u4F20 choice\uFF09\uFF1B\u5728\u7528\u6237\u56DE\u7B54\u524D\u518D\u6B21\u63D0\u4EA4\u65B0\u63D0\u6848\u4F1A\u88AB\u62D2\u7EDD(R-Q7)\u3002\u89C4\u683C\u751F\u6210(P0 specgen)\u9636\u6BB5\u4F20\u300C\u539F\u751F Markdown \u5B57\u7B26\u4E32\u300D\uFF08\u542B ## \u7AE0\u8282\u4E0E ```contract-json \u56F4\u680F\uFF09\uFF0C\u4E5F\u53EF\u5305\u6210 {spec:"..."} \u5BF9\u8C61\uFF1B\u5176\u4ED6\u9636\u6BB5\u4F20\u5404\u81EA\u7684\u7ED3\u6784\u5316\u5BF9\u8C61\u3002\u7EDD\u4E0D\u53EF\u628A Markdown/JSON \u518D\u5E8F\u5217\u5316\u6210\u5B57\u7B26\u4E32\u3001\u4E5F\u4E0D\u8981\u5305 ```json \u4EE3\u7801\u5757\u3002\u6821\u9A8C\u5931\u8D25\u4F1A\u660E\u786E\u544A\u77E5\u54EA\u4E2A\u5B57\u6BB5\u9519\u4E86\u3001\u6536\u5230\u4E86\u4EC0\u4E48\u3001\u671F\u671B\u4EC0\u4E48\u3002',
        args: external_exports.object({
          output: external_exports.any().describe(
            '\u672C\u9636\u6BB5\u6A21\u578B\u4EA7\u51FA\uFF0C\u5FC5\u987B\u662F JSON \u5BF9\u8C61(object)\uFF0C\u4E0D\u8981\u5E8F\u5217\u5316\u6210\u5B57\u7B26\u4E32\u3001\u4E5F\u4E0D\u8981\u5305\u88F9\u4EE3\u7801\u5757\uFF1B\u76F4\u63A5\u4F20\u7ED3\u6784\u5316\u5BF9\u8C61\uFF08\u5982 {exhausted:false, question:"...", options:{A:"...",B:"..."}, ...}\uFF09'
          )
        }),
        async execute(rawArgs) {
          const output = extractOutput(rawArgs);
          const e = engine(dir);
          const r = await e.submit(output);
          if (r.passed) {
            const s = await e.status();
            return `\u2705 \u901A\u8FC7\uFF0C\u5DF2\u63A8\u8FDB\u3002\u5F53\u524D phase=${s.phase} current_task=${s.current_task ?? "-"}`;
          }
          if ((await e.status()).phase === "FROZEN")
            return "\u2744\uFE0F \u8FDE\u7EED\u5931\u8D25\u8FBE\u4E0A\u9650\uFF0C\u6D41\u7A0B\u5DF2\u51BB\u7ED3\uFF0C\u9700\u4EBA\u5DE5\u89E3\u51BB\uFF08\u7F16\u8F91 .adocs/flow/state.json\uFF09";
          return {
            title: "\u6821\u9A8C\u672A\u901A\u8FC7",
            output: `\u274C \u6821\u9A8C\u672A\u901A\u8FC7\uFF0C\u8BF7\u91CD\u5199\u5B8C\u6574\u4EA7\u51FA\u3002\u7EA0\u9519\u5305\uFF1A
${JSON.stringify(r.result.correctionBag, null, 2)}

\u91CD\u8BD5\u6307\u4EE4\u5305\u5DF2\u5C31\u7EEA\uFF0C\u91CD\u65B0\u8F93\u51FA\u3002`
          };
        }
      }),
      flow_answer: tool({
        description: "\u8BB0\u5F55\u7528\u6237\u5BF9\u4E0A\u4E00\u8F6E P0 \u95EE\u9898\u7684\u3010\u771F\u5B9E\u56DE\u7B54\u3011\uFF08\u4EC5\u5728 flow_submit \u63D0\u4EA4\u95EE\u9898\u63D0\u6848\u3001\u5F15\u64CE\u8FDB\u5165\u300C\u7B49\u5F85\u7528\u6237\u56DE\u7B54\u300D\u72B6\u6001\u540E\u8C03\u7528\uFF09\u3002\u3010\u6D41\u7A0B\u3011\u628A\u95EE\u9898\u539F\u6837\u5448\u73B0\u7ED9\u7528\u6237 \u2192 \u505C\u6B62\uFF08finish: stop\uFF09\u7B49\u5F85\u7528\u6237\u771F\u5B9E\u56DE\u590D \u2192 \u7528\u6237\u56DE\u590D\u540E\u8C03\u7528\u672C\u5DE5\u5177\u8BB0\u5F55\u3002\u5F15\u64CE\u4F1A\u81EA\u52A8\u8BFB\u53D6\u4F1A\u8BDD\u4E2D\u95EE\u9898\u63D0\u51FA\u540E\u7684\u7528\u6237\u6D88\u606F\u539F\u6587\uFF08R-Q8 \u6821\u9A8C\uFF09\uFF1A\u82E5\u5C1A\u672A\u68C0\u6D4B\u5230\u7528\u6237\u56DE\u590D\uFF0C\u672C\u5DE5\u5177\u4F1A\u62D2\u7EDD\u5E76\u63D0\u793A\u7EE7\u7EED\u7B49\u5F85\uFF1B\u82E5\u7528\u6237\u56DE\u590D\u4E3A A/B \u5219\u81EA\u52A8\u843D\u8D26\u5BF9\u5E94\u9009\u9879\uFF0C\u82E5\u4E3A\u81EA\u7531\u6587\u672C\u5219\u6309\u81EA\u7531\u6587\u672C\u843D\u8D26\uFF08\u65E0\u9700\u3001\u4E5F\u4E0D\u5E94\u7F16\u9020 choice\uFF09\u3002choice \u53C2\u6570\u53EF\u9009\uFF0C\u4EC5\u4F9B\u65E0\u6CD5\u8BFB\u53D6\u4F1A\u8BDD\u7684\u964D\u7EA7\u573A\u666F\u4F7F\u7528\uFF1Bcomment \u4E3A\u6A21\u578B\u53EF\u9009\u7684\u8865\u5145\u8BF4\u660E\u3002\u4E25\u7981\u66FF\u7528\u6237\u4F5C\u7B54\u3001\u7F16\u9020\u7528\u6237\u7B54\u6848\u6216\u81EA\u884C\u63A8\u8FDB\u3002",
        args: external_exports.object({
          choice: external_exports.enum(["A", "B"]).optional().describe("\uFF08\u53EF\u9009\uFF09\u7528\u6237\u9009\u9879\u952E A/B\uFF1B\u6B63\u5E38\u573A\u666F\u5F15\u64CE\u4F1A\u4ECE\u4F1A\u8BDD\u4E2D\u7528\u6237\u6D88\u606F\u539F\u6587\u81EA\u52A8\u63A8\u5BFC\uFF0C\u65E0\u9700\u4F20\u5165"),
          comment: external_exports.string().optional().describe("\uFF08\u53EF\u9009\uFF09\u6A21\u578B\u8865\u5145\u8BF4\u660E\uFF1B\u5F15\u64CE\u4EE5\u4F1A\u8BDD\u4E2D\u7528\u6237\u539F\u8BDD\u4E3A\u51C6")
        }),
        async execute(rawArgs, context) {
          const { choice, comment } = unwrapArgs(rawArgs);
          const e = engine(dir);
          const sessionID = context?.sessionID;
          const verifyUserReply = client && sessionID ? async (since) => {
            const r2 = await lastUserReplySince(client, sessionID, since);
            return r2 && r2.text ? r2 : null;
          } : void 0;
          const r = await e.answer(choice, comment, { verifyUserReply });
          if (!r.ok) return { title: "\u65E0\u6CD5\u8BB0\u5F55\u56DE\u7B54", output: r.error };
          if (r.advancedSpecgen) return "\u2705 \u5DF2\u786E\u8BA4\u9700\u6C42\u7A77\u5C3D\uFF0C\u8FDB\u5165\u89C4\u683C\u751F\u6210\uFF08specgen\uFF09\u9636\u6BB5\u3002";
          const shown = r.user_choice ? `\u7B2C ${r.round} \u8F6E \u2192 ${r.user_choice}` : `\u7B2C ${r.round} \u8F6E \u2192 \u81EA\u7531\u6587\u672C\u56DE\u7B54`;
          return `\u2705 \u5DF2\u8BB0\u5F55\u7528\u6237\u56DE\u7B54\uFF08${shown}\uFF09\u3002\u53EF\u7EE7\u7EED\u4E0B\u4E00\u8F6E\u63D0\u95EE\uFF08flow_next\uFF09\u3002`;
        }
      }),
      flow_dispatch: tool({
        description: "\u5C06\u5F53\u524D\u6307\u4EE4\u5305\u6D3E\u53D1\u81F3\u4E00\u6B21\u6027\u5B50\u4F1A\u8BDD\u6267\u884C\u5E76\u8D70\u5B8C\u6574\u6821\u9A8C\u94FE\uFF0C\u4EC5\u8FD4\u56DE\u4E00\u884C\u88C1\u51B3\u6458\u8981\uFF08D-10 \u4E3B\u6848\uFF1ASDK \u5B50\u4F1A\u8BDD\uFF09\u3002\u6CE8\u610F\uFF1AP0 \u8BBF\u8C08\u9636\u6BB5\u9700\u8981\u771F\u5B9E\u7528\u6237\u4EA4\u4E92\uFF0C\u8BF7\u52FF\u6D3E\u53D1\uFF08\u5E94\u5185\u8054\u5448\u73B0\u95EE\u9898\u5E76\u7B49\u7528\u6237\u56DE\u7B54\u540E flow_answer\uFF09\u3002\u3010\u8C03\u7528\u7EA6\u5B9A\u3011\u53C2\u6570\u540D\u4E3A `baseUrl`/`model`/`whitelist_edit`/`whitelist_bash`\uFF0C\u76F4\u63A5\u4F20\u5165\uFF0C\u4E0D\u8981\u5305\u6210 `def={...}`\uFF08\u5F15\u64CE\u5DF2\u517C\u5BB9\u4E24\u79CD\u5199\u6CD5\uFF09\u3002",
        args: external_exports.object({
          baseUrl: external_exports.string().optional().describe("opencode serve \u5730\u5740\uFF1B\u9ED8\u8BA4\u8BFB OPENCODE_API_URL / OC_TEST_URL"),
          model: external_exports.string().optional().describe("\u6A21\u578B id\uFF1B\u9ED8\u8BA4 hy3-free"),
          whitelist_edit: external_exports.array(external_exports.string()).optional().describe("P-b \u8303\u56F4\u653E\u884C\uFF1A\u5141\u8BB8\u81EA\u52A8\u6279\u51C6\u5199\u6587\u4EF6\u7684\u8DEF\u5F84\u524D\u7F00"),
          whitelist_bash: external_exports.array(external_exports.string()).optional().describe("P-b \u8303\u56F4\u653E\u884C\uFF1A\u5141\u8BB8\u81EA\u52A8\u6279\u51C6\u6267\u884C\u7684 bash \u547D\u4EE4\u524D\u7F00")
        }),
        async execute(rawArgs) {
          const { baseUrl, model, whitelist_edit, whitelist_bash } = unwrapArgs(rawArgs);
          const e = engine(dir);
          const env = await e.next();
          const models = model ? [{ id: model, providerID: "opencode" }] : void 0;
          const permissionWhitelist = {
            editPrefixes: whitelist_edit ?? [dir],
            bashPrefixes: whitelist_bash ?? ["git", "npm", "npx", "node", "python3", "pytest", "pip"]
          };
          const disp = new FlowDispatcher({
            directory: dir,
            baseUrl: baseUrl ?? process.env.OPENCODE_API_URL ?? process.env.OC_TEST_URL,
            models,
            permissionWhitelist
          });
          const r = await disp.dispatch(env);
          const sub = await e.submit(r.parsed);
          return `\u6D3E\u53D1\u6A21\u578B=${r.model.id}\uFF1B\u5B50\u4F1A\u8BDD\u4EA7\u51FA\u6821\u9A8C\uFF1A${sub.passed ? "\u901A\u8FC7" : "\u672A\u901A\u8FC7\uFF08\u89C1\u4E3B\u6D41\u7A0B\u7EA0\u9519\u5FAA\u73AF\uFF09"}`;
        }
      }),
      flow_regression: tool({
        description: "\u6267\u884C\u5168\u91CF\u56DE\u5F52\uFF1A\u8FD0\u884C\u9879\u76EE tests/regression/ \u4E0B\u6240\u6709\u5386\u53F2\u4EFB\u52A1\u6C89\u6DC0\u7684\u56DE\u5F52\u811A\u672C\uFF08\u7531 P3 \u901A\u8FC7\u65F6\u673A\u68B0\u843D\u76D8\uFF09\uFF0C\u6C47\u603B\u901A\u8FC7/\u5931\u8D25\u3002\u53C2\u6570 task_id \u53EF\u6307\u5B9A\u53EA\u56DE\u5F52\u67D0\u4E2A\u4EFB\u52A1\u3002",
        args: external_exports.object({ task_id: external_exports.string().optional().describe("\u53EF\u9009\uFF1A\u4EC5\u56DE\u5F52\u6307\u5B9A\u4EFB\u52A1\uFF0C\u5982 T-001") }),
        async execute(rawArgs) {
          const { task_id } = unwrapArgs(rawArgs);
          const { execSync: execSync2 } = await import("node:child_process");
          const { readRegressionIndex: readRegressionIndex2 } = await Promise.resolve().then(() => (init_test(), test_exports));
          const layout = adocsLayout(dir);
          const idx = await readRegressionIndex2(layout);
          if (!idx || !idx.tasks.length) return "\uFF08\u6682\u65E0\u5DF2\u6C89\u6DC0\u7684\u56DE\u5F52\u811A\u672C\uFF1A\u5C1A\u65E0 P3 \u5168\u7EFF\u4EFB\u52A1\uFF09";
          const tasks = task_id ? idx.tasks.filter((t) => t.task_id === task_id) : idx.tasks;
          if (task_id && !tasks.length) return `\u672A\u627E\u5230\u4EFB\u52A1 ${task_id} \u7684\u56DE\u5F52\u811A\u672C`;
          const out = [];
          for (const t of tasks) {
            const fails = [];
            const passed = [];
            for (const rel of t.scripts) {
              const p = join6(dir, rel);
              try {
                execSync2(`bash ${JSON.stringify(p)}`, { cwd: dir, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
                passed.push(rel);
              } catch {
                fails.push(rel);
              }
            }
            out.push({ task_id: t.task_id, scripts: t.scripts.length, passed: passed.length, failed: fails.length, fails });
          }
          return JSON.stringify({ module: idx.module, summary: out }, null, 2);
        }
      }),
      flow_docs_check: tool({
        description: "\u4FDD\u9C9C\u6838\u5BF9\uFF1A\u6BD4\u5BF9\u4EE3\u7801 git \u6539\u52A8\u4E0E\u5404\u6587\u6863\u6700\u540E\u6838\u5BF9\u63D0\u4EA4\u70B9\uFF0C\u62A5\u544A\u8131\u8282\u6A21\u5757\u3002\u53EF\u6307\u5B9A task_id \u4EC5\u6838\u5BF9\u8BE5\u4EFB\u52A1\u5173\u8054\u5206\u5377\u3002\u5728 P2 \u5F00\u53D1\u5B8C\u6210\u3001P4 \u4EA4\u4ED8\u524D\u7531\u6D41\u7A0B\u5F3A\u5236\u8C03\u7528\uFF0C\u4E5F\u652F\u6301\u968F\u65F6\u624B\u52A8\u8C03\u7528\u3002",
        args: external_exports.object({
          task_id: external_exports.string().optional().describe("\u53EF\u9009\uFF1A\u4EC5\u6838\u5BF9\u6307\u5B9A\u4EFB\u52A1\u5173\u8054\u5206\u5377\uFF0C\u5982 T-001")
        }),
        async execute(rawArgs) {
          const { task_id } = unwrapArgs(rawArgs);
          const { execSync: execSync3 } = await import("node:child_process");
          const indexJson = join6(dir, ".adocs", "specs", "index.json");
          let specs = [];
          try {
            const raw = await import("node:fs").then((fs5) => fs5.promises.readFile(indexJson, "utf8"));
            const idx = JSON.parse(raw);
            specs = idx.specs ?? [];
          } catch {
            return "\u672A\u627E\u5230 specs/index.json\uFF0C\u8BF7\u5148\u751F\u6210\u673A\u5668\u7D22\u5F16";
          }
          if (task_id) {
            specs = specs.filter((s) => {
              const deps = s.depends_on ?? [];
              return deps.includes(task_id) || s.name?.includes(task_id);
            });
            if (!specs.length) return `\u672A\u627E\u5230\u4EFB\u52A1 ${task_id} \u5173\u8054\u7684\u5206\u5377`;
          }
          const results = [];
          for (const s of specs) {
            const commit = s.last_reviewed_commit;
            if (!commit) {
              results.push({ name: s.name, contract_id: s.contract_id, status: "no-commit", changes: [] });
              continue;
            }
            try {
              const log = execSync3(
                `git log --oneline ${commit}..HEAD -- ${JSON.stringify(s.doc_path)}`,
                { cwd: dir, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }
              ).trim();
              if (log) {
                const lines = log.split("\n").filter(Boolean);
                results.push({ name: s.name, contract_id: s.contract_id, status: "stale", behind: lines.length, recent: lines.slice(0, 3) });
              } else {
                results.push({ name: s.name, contract_id: s.contract_id, status: "fresh" });
              }
            } catch {
              results.push({ name: s.name, contract_id: s.contract_id, status: "check-error" });
            }
          }
          const stale = results.filter((r) => r.status === "stale");
          const noCommit = results.filter((r) => r.status === "no-commit");
          const fresh = results.filter((r) => r.status === "fresh");
          const errors = results.filter((r) => r.status === "check-error");
          const summary = `\u6838\u5BF9\u5B8C\u6210\uFF1A${results.length} \u4EFD\u5206\u5377\uFF0C\u5176\u4E2D\u65B0\u9C9C ${fresh.length}\u3001\u8131\u8282 ${stale.length}\u3001\u65E0\u63D0\u4EA4\u70B9 ${noCommit.length}\u3001\u9519\u8BEF ${errors.length}`;
          if (stale.length) {
            return JSON.stringify({ summary, stale: stale.map((r) => ({ name: r.name, contract_id: r.contract_id, behind: r.behind, recent: r.recent })), no_commit: noCommit.map((r) => r.name), errors: errors.map((r) => r.name) }, null, 2);
          }
          return summary + (noCommit.length ? `\n\u65E0\u63D0\u4EA4\u70B9\uFF1A${noCommit.map((r) => r.name).join(", ")}` : "");
        }
      }),
      flow_reset: tool({
        description: '\u5168\u91CF\u8F6F\u91CD\u7F6E\uFF1A\u5F52\u6863\u73B0\u6709 .adocs/ \u540E\u6309\u9501\u5B9A\u6A21\u677F\u7EC4\u91CD\u5EFA\u9AA8\u67B6\uFF08\u5951\u7EA6\u4FDD\u62A4\u4F8B\u5916\u653E\u884C\uFF09\u3002\u3010\u8C03\u7528\u7EA6\u5B9A\u3011\u53C2\u6570\u540D\u4E3A `module`\uFF0C\u76F4\u63A5 `flow_reset(module="calc")` \u4F20\u5165\uFF0C\u4E0D\u8981\u5305\u6210 `def={...}`\uFF08\u5F15\u64CE\u5DF2\u517C\u5BB9\u4E24\u79CD\u5199\u6CD5\uFF09\u3002',
        args: external_exports.object({ module: external_exports.string() }),
        async execute(rawArgs) {
          const { module } = unwrapArgs(rawArgs);
          const e = engine(dir);
          await e.reset(module);
          return "\u5DF2\u91CD\u7F6E\u56DE P0_ALIGN";
        }
      }),
      flow_freeze: tool({
        description: "\u663E\u5F0F\u51BB\u7ED3\u6D41\u7A0B\uFF08\u4EC5\u4EBA\u5DE5\u53EF\u89E3\u51BB\uFF09\u3002\u3010\u8C03\u7528\u7EA6\u5B9A\u3011\u53C2\u6570\u540D\u4E3A `reason`\uFF0C\u76F4\u63A5\u4F20\u5165\uFF0C\u4E0D\u8981\u5305\u6210 `def={...}`\uFF08\u5F15\u64CE\u5DF2\u517C\u5BB9\u4E24\u79CD\u5199\u6CD5\uFF09\u3002",
        args: external_exports.object({ reason: external_exports.string().optional() }),
        async execute(rawArgs) {
          const { reason } = unwrapArgs(rawArgs);
          const e = engine(dir);
          await e.freeze(reason ?? "\u7528\u6237\u663E\u5F0F\u51BB\u7ED3");
          return "\u2744\uFE0F \u6D41\u7A0B\u5DF2\u51BB\u7ED3";
        }
      })
    },
    // 契约保护 + 冻结封印（§5.5）
    "tool.execute.before": async (input2, _output) => {
      const name = input2?.tool ?? "";
      const phase = (await engine(dir).status().catch(() => null))?.phase;
      if (phase === "FROZEN" && FREEZE_BLOCKED.has(name)) {
        throw new Error("\u6D41\u7A0B\u5DF2\u51BB\u7ED3\uFF08FROZEN\uFF09\uFF0C\u62D2\u7EDD\u4E00\u5207 edit/write/bash");
      }
      const argStr = JSON.stringify(input2?.args ?? {});
      if ((name === "edit" || name === "write" || name === "bash") && CONTRACT_PROTECT.test(argStr) && name !== "flow_submit") {
        throw new Error("\u62D2\u7EDD\u6539\u52A8 .adocs/contracts \u6216 .adocs/tasks\uFF08\u5951\u7EA6\u4FDD\u62A4\u62E6\u622A\u5668\uFF09\uFF1B\u5982\u9700\u53D8\u66F4\u8BF7\u7528 flow \u4FEE\u8BA2\u534F\u8BAE");
      }
    },
    // 上下文锚定（§5.5）：压缩时注入状态摘要
    "experimental.session.compacting": async (_input, output) => {
      const e = engine(dir);
      const s = await e.status().catch(() => null);
      if (s) {
        const head = `flow \u72B6\u6001\uFF1Aphase=${s.phase} task=${s.current_task ?? "-"} streak=${s.task_fail_streak}`;
        output.context = [`# flow \u7EED\u8DD1\u951A\u70B9
${head}`];
      }
    }
  };
}
var plugin_default = arFlowPlugin;
export {
  arFlowPlugin,
  plugin_default as default
};
