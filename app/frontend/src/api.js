const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

export function imageUrl(imageId) {
  return `${API_BASE}/api/item-images/${imageId}`;
}

export const api = {
  health: () => request("/api/health"),
  catalogSummary: () => request("/api/catalog/summary"),
  listItems: (type = "all") => request(`/api/items?type=${encodeURIComponent(type)}`),
  getItem: (itemId) => request(`/api/items/${encodeURIComponent(itemId)}`),
  updateItem: (itemId, changes) =>
    request(`/api/items/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  deleteItem: (itemId) =>
    request(`/api/items/${encodeURIComponent(itemId)}`, {
      method: "DELETE",
    }),
  listConversations: () => request("/api/conversations"),
  createConversation: (title = "New chat") =>
    request("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  listMessages: (conversationId) => request(`/api/conversations/${conversationId}/messages`),
  sendMessage: (conversationId, content) =>
    request(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  listSavedOutfits: () => request("/api/saved-outfits"),
  saveOutfit: ({ outfit, sourceConversationId, sourceMessageId }) =>
    request("/api/saved-outfits", {
      method: "POST",
      body: JSON.stringify({
        outfit,
        source_conversation_id: sourceConversationId,
        source_message_id: sourceMessageId,
      }),
    }),
  deleteSavedOutfit: (savedOutfitId) =>
    request(`/api/saved-outfits/${encodeURIComponent(savedOutfitId)}`, {
      method: "DELETE",
    }),
};
