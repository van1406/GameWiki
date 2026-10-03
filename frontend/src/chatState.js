/**
 * chatState.js — pure helpers for the per-game chat history.
 *
 * Shape:  { gta5: [message, ...], minecraft: [message, ...] }
 *
 * Each game keeps its own independent conversation: switching the game
 * selector only changes which conversation is displayed, and Clear chat
 * empties only the currently selected game's list.
 */

/** Return the messages of one game (empty list if it has no conversation yet). */
export function messagesFor(history, gameId) {
  return history[gameId] || []
}

/** Return a new history with `message` appended to `gameId`'s conversation. */
export function appendMessage(history, gameId, message) {
  return { ...history, [gameId]: [...messagesFor(history, gameId), message] }
}

/** Return a new history where only `gameId`'s conversation is cleared. */
export function clearGame(history, gameId) {
  return { ...history, [gameId]: [] }
}
