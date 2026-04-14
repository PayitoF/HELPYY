/**
 * Chat renderer — shared markdown rendering for chat messages.
 *
 * Used by both the web widget and the React app mockup.
 * Supports basic markdown: bold, italic, links, lists.
 */

/**
 * Render a chat message string with basic markdown formatting.
 * @param {string} text - Raw message text
 * @returns {string} HTML string
 */
export function renderMessage(text) {
  // TODO: parse basic markdown (bold, italic, links, lists)
  // TODO: sanitize HTML to prevent XSS
  return text;
}
