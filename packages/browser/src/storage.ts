/**
 * Records IndexedDB and Origin Private File System operations.
 * Values and file contents are never sent: only the store or path, the
 * operation, and a byte count when the platform already knows one.
 * Safe to call from a worker. Sync file handles exist only there.
 */

export type StorageRecord = (detail: {
  backend: "indexedDB" | "opfs";
  operation: string;
  name: string;
  bytes?: number;
  key?: string;
}) => void;

type StoreLike = {
  get?: (...args: unknown[]) => unknown;
  getAll?: (...args: unknown[]) => unknown;
  put?: (...args: unknown[]) => unknown;
  add?: (...args: unknown[]) => unknown;
  delete?: (...args: unknown[]) => unknown;
  clear?: (...args: unknown[]) => unknown;
  count?: (...args: unknown[]) => unknown;
};

const STORE_METHODS = [
  "get",
  "getAll",
  "put",
  "add",
  "delete",
  "clear",
  "count",
] as const;
const WRITE_METHODS = new Set(["put", "add"]);

let installed = false;

/** Patch storage APIs in this realm. No effect when they are absent. */
export function installStorage(record: StorageRecord): void {
  if (installed) {
    return;
  }
  installed = true;
  patchIndexedDb(record);
  patchOpfs(record);
}

function patchIndexedDb(record: StorageRecord): void {
  const factory = globalThis.indexedDB;
  if (!factory) {
    return;
  }
  const original = factory.open.bind(factory);
  factory.open = (name: string, version?: number) => {
    record({ backend: "indexedDB", operation: "open", name });
    const request = original(name, version);
    request.addEventListener("success", () => {
      watchDatabase(request.result, record);
    });
    return request;
  };
}

function watchDatabase(database: IDBDatabase, record: StorageRecord): void {
  const original = database.transaction.bind(database);
  database.transaction = (storeNames, mode, options) => {
    const transaction = original(storeNames, mode, options);
    const names = Array.isArray(storeNames) ? storeNames : [storeNames];
    for (const name of names) {
      try {
        watchObjectStore(transaction.objectStore(name), String(name), record);
      } catch {
        // A missing store is the application's error, not ours.
      }
    }
    return transaction;
  };
}

/** Wrap one object store so each call is recorded before it runs. */
export function watchObjectStore(
  store: StoreLike,
  name: string,
  record: StorageRecord,
): void {
  for (const method of STORE_METHODS) {
    const original = store[method];
    if (typeof original !== "function") {
      continue;
    }
    store[method] = (...args: unknown[]) => {
      const written = WRITE_METHODS.has(method);
      record({
        backend: "indexedDB",
        operation: method,
        name,
        key: keyText(written ? args[1] : args[0]),
        bytes: written ? byteLength(args[0]) : undefined,
      });
      return original.apply(store, args);
    };
  }
}

function patchOpfs(record: StorageRecord): void {
  const storage = globalThis.navigator?.storage;
  if (!storage || typeof storage.getDirectory !== "function") {
    return;
  }
  const original = storage.getDirectory.bind(storage);
  storage.getDirectory = async () =>
    watchDirectory(await original(), "", record);
}

function watchDirectory(
  directory: FileSystemDirectoryHandle,
  path: string,
  record: StorageRecord,
): FileSystemDirectoryHandle {
  const getFile = directory.getFileHandle.bind(directory);
  directory.getFileHandle = async (name, options) => {
    const child = `${path}/${name}`.replace(/^\//, "");
    record({ backend: "opfs", operation: "open", name: child });
    return watchFile(await getFile(name, options), child, record);
  };
  const getDirectory = directory.getDirectoryHandle.bind(directory);
  directory.getDirectoryHandle = async (name, options) => {
    const child = `${path}/${name}`.replace(/^\//, "");
    return watchDirectory(await getDirectory(name, options), child, record);
  };
  return directory;
}

function watchFile(
  handle: FileSystemFileHandle,
  path: string,
  record: StorageRecord,
): FileSystemFileHandle {
  const getFile = handle.getFile.bind(handle);
  handle.getFile = async () => {
    const file = await getFile();
    record({
      backend: "opfs",
      operation: "read",
      name: path,
      bytes: file.size,
    });
    return file;
  };
  if (typeof handle.createSyncAccessHandle === "function") {
    const createSync = handle.createSyncAccessHandle.bind(handle);
    handle.createSyncAccessHandle = async () =>
      watchSync(await createSync(), path, record);
  }
  if (typeof handle.createWritable === "function") {
    const createWritable = handle.createWritable.bind(handle);
    handle.createWritable = async (options) => {
      const writable = await createWritable(options);
      const write = writable.write.bind(writable);
      writable.write = async (data) => {
        record({
          backend: "opfs",
          operation: "write",
          name: path,
          bytes: byteLength(data),
        });
        await write(data);
      };
      return writable;
    };
  }
  return handle;
}

function watchSync(
  access: FileSystemSyncAccessHandle,
  path: string,
  record: StorageRecord,
): FileSystemSyncAccessHandle {
  const read = access.read.bind(access);
  const write = access.write.bind(access);
  access.read = (buffer, options) => {
    const count = read(buffer, options);
    record({ backend: "opfs", operation: "read", name: path, bytes: count });
    return count;
  };
  access.write = (buffer, options) => {
    const count = write(buffer, options);
    record({ backend: "opfs", operation: "write", name: path, bytes: count });
    return count;
  };
  return access;
}

function keyText(value: unknown): string | undefined {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return undefined;
}

/** Byte length of a string, blob or buffer. Objects are skipped so their fields are never read. */
export function byteLength(value: unknown): number | undefined {
  if (typeof value === "string") {
    return value.length;
  }
  if (value instanceof ArrayBuffer) {
    return value.byteLength;
  }
  if (ArrayBuffer.isView(value)) {
    return value.byteLength;
  }
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return value.size;
  }
  return undefined;
}
