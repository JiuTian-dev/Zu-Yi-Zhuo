/*
 * Homepage integration contract acceptance.
 *
 * This is intentionally REST-only: it simulates the teammate-owned homepage
 * without implementing homepage UI. It verifies the backend semantics that
 * the homepage must rely on before handing the real table_id to OpenTableContext.
 */

const baseUrl = (process.env.HOME_CONTRACT_BASE_URL ?? 'http://127.0.0.1:5174').replace(/\/+$/, '')
const tableId = `home-contract-${Date.now()}`
const ownerId = `${tableId}-owner`
const candidateId = `${tableId}-candidate`

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
    declared_position: `为首页合同验收提供 ${role} 视角`,
    relevant_experience: [{
      text: `我做过一次 ${role} 相关的真实实践。`,
      source_ref: `test:${tableId}:${participantId}`,
    }],
  }
}

async function main() {
  const owner = participant(ownerId, '首页发起人', '实践者')
  const candidate = participant(candidateId, '首页受邀人', '研究者')

  const created = await requestJson('/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      table_id: tableId,
      core_question: '首页手动建桌如何保持真实成员边界？',
      participants: [owner],
    }),
  })
  assert(created.response.status === 201, `create table failed: ${created.response.status}`)
  assert(created.body.table_id === tableId, 'create table did not return the requested table_id')
  assert(Object.keys(created.body.participants).length === 1, 'creator was not the only initial member')

  const duplicate = await requestJson('/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      table_id: tableId,
      core_question: '首页手动建桌如何保持真实成员边界？',
      participants: [owner],
    }),
  })
  assert(duplicate.response.status === 409, `duplicate create was not rejected: ${duplicate.response.status}`)

  const invited = await requestJson(`/tables/${encodeURIComponent(tableId)}/invitations?inviter_id=${encodeURIComponent(ownerId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate, reason: '补充研究视角' }),
  })
  assert(invited.response.status === 201, `create invitation failed: ${invited.response.status}`)
  assert(invited.body.status === 'pending', 'new invitation was not pending')

  const beforeAccept = await requestJson(`/tables/${encodeURIComponent(tableId)}/state?participant_id=${encodeURIComponent(ownerId)}`)
  assert(beforeAccept.response.ok, `state before accept failed: ${beforeAccept.response.status}`)
  assert(!beforeAccept.body.participants[candidateId], 'pending invitation consumed a seat before acceptance')

  const inbox = await requestJson(`/participants/${encodeURIComponent(candidateId)}/invitations?viewer_id=${encodeURIComponent(candidateId)}`)
  assert(inbox.response.ok, `invitation inbox failed: ${inbox.response.status}`)
  assert(inbox.body.total === 1, `invitation inbox returned ${inbox.body.total} invitations`)
  assert(inbox.body.items[0].can_respond === true, 'pending invitation was not actionable')

  const accepted = await requestJson(
    `/tables/${encodeURIComponent(tableId)}/invitations/${encodeURIComponent(invited.body.invitation_id)}/respond?participant_id=${encodeURIComponent(candidateId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accept: true }),
    },
  )
  assert(accepted.response.ok, `accept invitation failed: ${accepted.response.status}`)
  assert(accepted.body.invitation.status === 'accepted', 'accepted invitation did not change status')
  assert(accepted.body.state?.participants?.[candidateId], 'accepted invitation did not add the candidate')

  const afterAccept = await requestJson(`/tables/${encodeURIComponent(tableId)}/state?participant_id=${encodeURIComponent(ownerId)}`)
  assert(afterAccept.response.ok, `state after accept failed: ${afterAccept.response.status}`)
  assert(Object.keys(afterAccept.body.participants).sort().join(',') === [ownerId, candidateId].sort().join(','), 'final member set is incorrect')
  assert(afterAccept.body.version > beforeAccept.body.version, 'acceptance did not advance table state')

  console.log(JSON.stringify({
    ok: true,
    table_id: tableId,
    initial_members: 1,
    pending_invitation_kept_membership: true,
    accepted_members: 2,
    duplicate_create_rejected: true,
    final_state_version: afterAccept.body.version,
  }, null, 2))
}

main().catch((error) => {
  console.error(`Homepage contract acceptance failed: ${error instanceof Error ? error.message : String(error)}`)
  process.exitCode = 1
})
