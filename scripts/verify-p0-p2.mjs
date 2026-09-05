/*
 * P0–P2 transport acceptance — isolated two-client table.
 *
 * This is intentionally black-box: it talks to the same HTTP/WS origin that
 * the browser uses, creates a unique table, and never touches a seeded table.
 * It verifies the transport contract; visual scene and teammate homepage
 * acceptance stay in their own lanes.
 */

const baseUrl = (process.env.P0_P2_BASE_URL ?? 'http://127.0.0.1:5174').replace(/\/+$/, '')
const wsBaseUrl = baseUrl.replace(/^http/, 'ws')
const tableId = `p0-p2-e2e-${Date.now()}`
const ownerId = `${tableId}-owner`
const peerId = `${tableId}-peer`

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function requestJson(path, init = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init.headers ?? {}) },
  })
  const text = await response.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  return { response, body }
}

function participant(participantId, displayName, role) {
  return {
    participant_id: participantId,
    display_name: displayName,
    role,
    declared_position: `为 P0–P2 验收提供 ${role} 视角`,
    relevant_experience: [{
      text: `我做过一次 ${role} 相关的真实实践。`,
      source_ref: `test:${tableId}:${participantId}`,
    }],
  }
}

function waitForOpen(socket) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('WebSocket open timeout')), 6000)
    socket.addEventListener('open', () => {
      clearTimeout(timer)
      resolve()
    }, { once: true })
    socket.addEventListener('error', () => {
      clearTimeout(timer)
      reject(new Error('WebSocket open failed'))
    }, { once: true })
  })
}

function waitForFrame(socket, predicate, label = 'WebSocket frame') {
  const seen = []
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.removeEventListener('message', onMessage)
      reject(new Error(`${label} timeout; last frames: ${JSON.stringify(seen.slice(-4))}`))
    }, 7000)
    const onMessage = (event) => {
      let payload
      try {
        payload = JSON.parse(String(event.data))
      } catch {
        return
      }
      seen.push(payload)
      if (!predicate(payload)) return
      clearTimeout(timer)
      socket.removeEventListener('message', onMessage)
      resolve(payload)
    }
    socket.addEventListener('message', onMessage)
  })
}

function trackStateVersions(socket) {
  const versions = []
  socket.addEventListener('message', (event) => {
    try {
      const payload = JSON.parse(String(event.data))
      const version = payload.type === 'table_state_changed'
        ? payload.state?.version
        : payload.type === 'safety_enforced'
          ? payload.state?.version
          : undefined
      if (Number.isInteger(version)) versions.push(version)
    } catch {
      // A malformed frame is handled by the client boundary; it is not part
      // of this transport acceptance assertion.
    }
  })
  return versions
}

async function connect(participantId) {
  const socket = new WebSocket(`${wsBaseUrl}/ws/tables/${encodeURIComponent(tableId)}?participant_id=${encodeURIComponent(participantId)}`)
  await waitForOpen(socket)
  const versions = trackStateVersions(socket)
  return { socket, versions }
}

function close(socket) {
  if (!socket) return
  if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close(1000, 'p0-p2 acceptance complete')
}

async function main() {
  const created = await requestJson('/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      table_id: tableId,
      core_question: '断线重连是否保持同一条表达？',
      participants: [participant(ownerId, '验收成员 A', '实践者')],
    }),
  })
  assert(created.response.status === 201, `create table failed: ${created.response.status}`)

  const joined = await requestJson(`/tables/${encodeURIComponent(tableId)}/participants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(participant(peerId, '验收成员 B', '处境者')),
  })
  assert(joined.response.ok, `second participant failed: ${joined.response.status}`)

  let owner
  let peer
  let reconnectedOwner
  try {
    owner = await connect(ownerId)
    peer = await connect(peerId)

    const messageId = `${tableId}-message-1`
    const payload = {
      type: 'human_message',
      message_id: messageId,
      participant_id: ownerId,
      text: '我会保留同一个 message_id，验证断线后的可靠回执。',
      client_ts: Date.now(),
    }
    const ownerMessage = waitForFrame(owner.socket, (frame) => frame.type === 'message_committed' && frame.message?.message_id === messageId, 'owner message')
    const peerMessage = waitForFrame(peer.socket, (frame) => frame.type === 'message_committed' && frame.message?.message_id === messageId, 'peer message')
    owner.socket.send(JSON.stringify(payload))
    await Promise.all([ownerMessage, peerMessage])

    const afterCommit = await requestJson(`/tables/${encodeURIComponent(tableId)}/state?participant_id=${encodeURIComponent(ownerId)}`)
    assert(afterCommit.response.ok, `state after commit failed: ${afterCommit.response.status}`)
    const committedVersion = afterCommit.body.version

    const duplicateError = waitForFrame(owner.socket, (frame) => frame.type === 'error' && frame.code === 'duplicate_message' && frame.message_id === messageId, 'duplicate error')
    owner.socket.send(JSON.stringify(payload))
    await duplicateError

    const replay = await requestJson(`/tables/${encodeURIComponent(tableId)}/replay?participant_id=${encodeURIComponent(ownerId)}`)
    assert(replay.response.ok, `replay failed: ${replay.response.status}`)
    const matchingMessages = replay.body.messages.filter((message) => message.message_id === messageId)
    assert(matchingMessages.length === 1, `duplicate message was persisted (${matchingMessages.length})`)

    close(owner.socket)
    await new Promise((resolve) => setTimeout(resolve, 150))
    reconnectedOwner = await connect(ownerId)
    const recovered = await requestJson(`/tables/${encodeURIComponent(tableId)}/state?participant_id=${encodeURIComponent(ownerId)}`)
    assert(recovered.response.ok, `state after reconnect failed: ${recovered.response.status}`)
    assert(recovered.body.version === committedVersion, 'reconnect changed the state version')
    assert(Object.keys(recovered.body.participants).sort().join(',') === [ownerId, peerId].sort().join(','), 'reconnect duplicated or lost a participant')

    const versions = [...owner.versions, ...peer.versions, ...reconnectedOwner.versions]
    assert(versions.every((version, index) => index === 0 || version >= versions[index - 1]), `state versions regressed: ${versions.join(', ')}`)

    console.log(JSON.stringify({
      ok: true,
      table_id: tableId,
      two_clients: true,
      duplicate_message_rejected: true,
      replay_message_count: matchingMessages.length,
      reconnect_preserved_version: recovered.body.version,
      participant_ids: Object.keys(recovered.body.participants).sort(),
      observed_state_versions: versions,
    }, null, 2))
  } finally {
    close(owner?.socket)
    close(peer?.socket)
    close(reconnectedOwner?.socket)
  }
}

main().catch((error) => {
  console.error(`P0–P2 acceptance failed: ${error instanceof Error ? error.message : String(error)}`)
  process.exitCode = 1
})
