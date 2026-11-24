const DB_NAME = 'edustacked-offline-attendance'
const DB_VERSION = 1
const RECORDS_STORE = 'encrypted-records'
const KEYS_STORE = 'device-keys'
const REGISTER_PREFIX = 'attendance:'
const AUTH_SNAPSHOT_ID = 'auth-snapshot'
const LOCAL_RETENTION_MS = 30 * 24 * 60 * 60 * 1000
let keyInFlight = null

export class OfflineSyncPendingError extends Error {
  constructor(message) {
    super(message)
    this.name = 'OfflineSyncPendingError'
  }
}

export function supportsEncryptedOfflineStorage() {
  return typeof indexedDB !== 'undefined' && Boolean(globalThis.crypto?.subtle)
}

function openDatabase() {
  if (!supportsEncryptedOfflineStorage()) {
    throw new Error('This browser does not support encrypted offline storage. Use an up-to-date browser over HTTPS.')
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(RECORDS_STORE)) database.createObjectStore(RECORDS_STORE, { keyPath: 'id' })
      if (!database.objectStoreNames.contains(KEYS_STORE)) database.createObjectStore(KEYS_STORE, { keyPath: 'id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Could not open secure offline storage.'))
  })
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Could not read offline storage.'))
  })
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = resolve
    transaction.onerror = () => reject(transaction.error || new Error('Could not save offline data.'))
    transaction.onabort = () => reject(transaction.error || new Error('Offline storage was interrupted.'))
  })
}

async function deviceKey(database) {
  const readTransaction = database.transaction(KEYS_STORE, 'readonly')
  const done = transactionDone(readTransaction)
  const stored = await requestResult(readTransaction.objectStore(KEYS_STORE).get('attendance-key'))
  await done
  if (stored?.key) return stored.key
  if (!keyInFlight) {
    keyInFlight = (async () => {
      const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
      const writeTransaction = database.transaction(KEYS_STORE, 'readwrite')
      writeTransaction.objectStore(KEYS_STORE).put({ id: 'attendance-key', key })
      await transactionDone(writeTransaction)
      return key
    })().finally(() => { keyInFlight = null })
  }
  return keyInFlight
}

async function writeEncrypted(database, id, value, expiresAt) {
  const key = await deviceKey(database)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const plaintext = new TextEncoder().encode(JSON.stringify(value))
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext)
  const transaction = database.transaction(RECORDS_STORE, 'readwrite')
  transaction.objectStore(RECORDS_STORE).put({ id, iv: iv.buffer, ciphertext, expiresAt })
  await transactionDone(transaction)
}

async function readEncrypted(database, id) {
  const transaction = database.transaction(RECORDS_STORE, 'readonly')
  const done = transactionDone(transaction)
  const stored = await requestResult(transaction.objectStore(RECORDS_STORE).get(id))
  await done
  if (!stored) return null
  if (!stored.expiresAt || new Date(stored.expiresAt).getTime() <= Date.now()) {
    await deleteRecord(database, id)
    return null
  }
  const key = await deviceKey(database)
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: stored.iv }, key, stored.ciphertext)
  return JSON.parse(new TextDecoder().decode(plaintext))
}

async function deleteRecord(database, id) {
  const transaction = database.transaction(RECORDS_STORE, 'readwrite')
  transaction.objectStore(RECORDS_STORE).delete(id)
  await transactionDone(transaction)
}

async function registerId(userId, schoolId, registerId) {
  return `${REGISTER_PREFIX}${userId}:${schoolId}:${registerId}`
}

export async function prepareOfflineAttendance({ user, selectedSchool, register, roster, options, token, expiresAt }) {
  const database = await openDatabase()
  try {
    const id = await registerId(user.id, selectedSchool.school_id, register.id)
    const existing = await readEncrypted(database, id).catch(() => null)
    if (existing?.pending) throw new OfflineSyncPendingError('This register has saved marks waiting to sync. Refresh offline access without replacing those marks.')
    const storageExpiresAt = new Date(Date.now() + LOCAL_RETENTION_MS).toISOString()
    await writeEncrypted(database, id, {
      userId: user.id,
      user,
      schoolId: selectedSchool.school_id,
      selectedSchool,
      register,
      roster,
      options,
      token,
      expiresAt,
      storageExpiresAt,
      pending: null,
    }, storageExpiresAt)
    await writeEncrypted(database, AUTH_SNAPSHOT_ID, {
      user,
      selectedSchool,
      expiresAt,
    }, expiresAt)
    return { id, expiresAt }
  } finally {
    database.close()
  }
}

export async function renewOfflineAttendanceGrant({ userId, schoolId, user, selectedSchool, register, token, expiresAt }) {
  const database = await openDatabase()
  try {
    const id = await registerId(userId, schoolId, register.id)
    const data = await readEncrypted(database, id)
    if (!data) throw new Error('The saved offline register is no longer on this device. Reopen it online before preparing it again.')
    data.user = user
    data.selectedSchool = selectedSchool
    data.token = token
    data.expiresAt = expiresAt
    if (!data.pending) data.register = register
    await writeEncrypted(database, id, data, data.storageExpiresAt || new Date(Date.now() + LOCAL_RETENTION_MS).toISOString())
    await writeEncrypted(database, AUTH_SNAPSHOT_ID, {
      user: data.user,
      selectedSchool: data.selectedSchool,
      expiresAt,
    }, expiresAt)
    return data
  } finally {
    database.close()
  }
}

export async function getOfflineAttendanceRegister(userId, schoolId, id) {
  const database = await openDatabase()
  try {
    return readEncrypted(database, await registerId(userId, schoolId, id))
  } finally {
    database.close()
  }
}

export async function listOfflineAttendanceRegisters(userId, schoolId) {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(RECORDS_STORE, 'readonly')
    const records = await requestResult(transaction.objectStore(RECORDS_STORE).getAll())
    const prefix = `${REGISTER_PREFIX}${userId}:${schoolId}:`
    const results = []
    for (const record of records.filter((item) => item.id.startsWith(prefix))) {
      try {
        const data = await readEncrypted(database, record.id)
        if (data) results.push(data)
      } catch {
        await deleteRecord(database, record.id)
      }
    }
    return results.sort((a, b) => String(b.register.attendance_date).localeCompare(String(a.register.attendance_date)))
  } finally {
    database.close()
  }
}

export async function saveOfflineAttendanceDraft({ userId, schoolId, registerId: id, register, roster }) {
  const database = await openDatabase()
  try {
    const key = await registerId(userId, schoolId, id)
    const data = await readEncrypted(database, key)
    if (!data?.token) throw new Error('Prepare this register for offline use before saving attendance offline.')
    if (data.pending && data.pending.state !== 'pending') {
      throw new OfflineSyncPendingError('A previous offline save may already have reached the server. Reconnect and sync it before making further offline changes.')
    }
    const syncId = crypto.randomUUID()
    const records = roster.filter((row) => Boolean(row.status)).map((row) => ({
      student_id: Number(row.student_id),
      status: row.status,
      note: row.note || '',
      reason: row.reason || '',
    }))
    data.register = register
    data.roster = roster
    data.pending = {
      syncId,
      version: register.version,
      records,
      state: 'pending',
      message: '',
    }
    await writeEncrypted(database, key, data, data.storageExpiresAt || data.expiresAt)
    return data.pending
  } finally {
    database.close()
  }
}

export async function markOfflineAttendanceSyncStarted(userId, schoolId, id, syncId) {
  return updatePending(userId, schoolId, id, syncId, (pending) => ({ ...pending, state: 'inflight', message: '' }))
}

export async function markOfflineAttendanceSyncError(userId, schoolId, id, syncId, message, conflict = false) {
  return updatePending(userId, schoolId, id, syncId, (pending) => ({
    ...pending,
    state: conflict ? 'conflict' : 'inflight',
    message,
  }))
}

async function updatePending(userId, schoolId, id, syncId, updater) {
  const database = await openDatabase()
  try {
    const key = await registerId(userId, schoolId, id)
    const data = await readEncrypted(database, key)
    if (!data?.pending || data.pending.syncId !== syncId) return data
    data.pending = updater(data.pending)
    await writeEncrypted(database, key, data, data.storageExpiresAt || data.expiresAt)
    return data
  } finally {
    database.close()
  }
}

export async function finishOfflineAttendanceSync(userId, schoolId, id, syncId, register) {
  const database = await openDatabase()
  try {
    const key = await registerId(userId, schoolId, id)
    const data = await readEncrypted(database, key)
    if (!data?.pending || data.pending.syncId !== syncId) return data
    data.register = register
    data.roster = register.records.map((row) => ({
      ...row,
      student_id: row.student,
      id: row.student,
      original_status: row.status,
      reason: '',
    }))
    data.pending = null
    await writeEncrypted(database, key, data, data.storageExpiresAt || data.expiresAt)
    return data
  } finally {
    database.close()
  }
}

export async function loadOfflineAuthSnapshot() {
  if (typeof indexedDB === 'undefined' || !globalThis.crypto?.subtle) return null
  const database = await openDatabase()
  try {
    return await readEncrypted(database, AUTH_SNAPSHOT_ID)
  } catch {
    return null
  } finally {
    database.close()
  }
}

export async function clearOfflineAuthSnapshot() {
  if (typeof indexedDB === 'undefined') return
  const database = await openDatabase()
  try {
    await deleteRecord(database, AUTH_SNAPSHOT_ID)
  } finally {
    database.close()
  }
}
