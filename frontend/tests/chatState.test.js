/**
 * chatState.test.js — verifies per-game chat separation.
 *
 * Run:  npm test          (from frontend/)
 *   or: node --test tests/
 *
 * Mirrors the manual UI checklist:
 *  1. GTA 5 selected -> ask a question
 *  2. switch to Minecraft -> empty (new) chat
 *  3. ask in Minecraft
 *  4. switch back to GTA 5 -> original conversation restored
 *  5. switch to Minecraft -> its conversation restored
 *  6. clear while Minecraft selected -> only Minecraft cleared
 *  7. GTA 5 conversation still intact
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { appendMessage, clearGame, messagesFor } from '../src/chatState.js'

const gtaMsg = { id: 1, role: 'user', text: 'How do I remove 5 stars?' }
const gtaAns = { id: 2, role: 'assistant', text: 'Break line of sight...' }
const mcMsg = { id: 3, role: 'user', text: 'How do I find diamonds?' }
const mcAns = { id: 4, role: 'assistant', text: 'Mine below y -58...' }

test('a game with no conversation shows a new empty chat', () => {
  assert.deepEqual(messagesFor({}, 'minecraft'), [])
})

test('asking in GTA 5 only fills the GTA 5 conversation', () => {
  let history = {}
  history = appendMessage(history, 'gta5', gtaMsg)
  history = appendMessage(history, 'gta5', gtaAns)
  assert.deepEqual(messagesFor(history, 'gta5'), [gtaMsg, gtaAns])
  assert.deepEqual(messagesFor(history, 'minecraft'), [])
})

test('switching to Minecraft starts a chat; both stay independent', () => {
  let history = {}
  history = appendMessage(history, 'gta5', gtaMsg)
  history = appendMessage(history, 'gta5', gtaAns)
  // user switches to Minecraft -> nothing there yet
  assert.deepEqual(messagesFor(history, 'minecraft'), [])
  // asks in Minecraft
  history = appendMessage(history, 'minecraft', mcMsg)
  history = appendMessage(history, 'minecraft', mcAns)
  // switching back restores the GTA 5 conversation exactly
  assert.deepEqual(messagesFor(history, 'gta5'), [gtaMsg, gtaAns])
  // and Minecraft keeps its own
  assert.deepEqual(messagesFor(history, 'minecraft'), [mcMsg, mcAns])
})

test('switching games never copies messages between conversations', () => {
  let history = {}
  history = appendMessage(history, 'gta5', gtaMsg)
  history = appendMessage(history, 'minecraft', mcMsg)
  assert.equal(messagesFor(history, 'minecraft').includes(gtaMsg), false)
  assert.equal(messagesFor(history, 'gta5').includes(mcMsg), false)
  assert.deepEqual(Object.keys(history).sort(), ['gta5', 'minecraft'])
})

test('clear chat while Minecraft selected clears Minecraft only', () => {
  let history = {}
  history = appendMessage(history, 'gta5', gtaMsg)
  history = appendMessage(history, 'gta5', gtaAns)
  history = appendMessage(history, 'minecraft', mcMsg)
  history = appendMessage(history, 'minecraft', mcAns)

  history = clearGame(history, 'minecraft')

  assert.deepEqual(messagesFor(history, 'minecraft'), [])
  assert.deepEqual(messagesFor(history, 'gta5'), [gtaMsg, gtaAns])
})

test('clear chat while GTA 5 selected clears GTA 5 only', () => {
  let history = {}
  history = appendMessage(history, 'gta5', gtaMsg)
  history = appendMessage(history, 'minecraft', mcMsg)

  history = clearGame(history, 'gta5')

  assert.deepEqual(messagesFor(history, 'gta5'), [])
  assert.deepEqual(messagesFor(history, 'minecraft'), [mcMsg])
})

test('message ids stay unique across games', () => {
  let history = {}
  history = appendMessage(history, 'gta5', { id: 1, role: 'user', text: 'a' })
  history = appendMessage(history, 'minecraft', { id: 2, role: 'user', text: 'b' })
  const ids = [
    ...messagesFor(history, 'gta5').map((m) => m.id),
    ...messagesFor(history, 'minecraft').map((m) => m.id),
  ]
  assert.equal(new Set(ids).size, ids.length)
})
