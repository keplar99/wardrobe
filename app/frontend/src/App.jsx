import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bookmark,
  ChevronDown,
  ChevronRight,
  Images,
  List,
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  Pencil,
  Save,
  Send,
  Shirt,
  Trash2,
  X,
} from "lucide-react";
import { api, imageUrl } from "./api";

const starterPrompts = [
  "Office outfit for today, all-day comfort",
  "Evening date night outfit for a restaurant",
  "Casual boys night outfit with a little edge",
];

const routes = ["/chat", "/catalog", "/saved"];

const typeFilters = [
  ["all", "All"],
  ["top", "Tops"],
  ["bottom", "Bottoms"],
  ["shoe", "Shoes"],
];

const fieldGroups = [
  {
    title: "Identity",
    fields: ["category", "sub_category", "brand", "color_primary", "color_secondary", "pattern"],
  },
  {
    title: "Shape & Fit",
    fields: ["fit", "rise", "length", "silhouette", "neckline", "drape_notes", "fit_source"],
  },
  {
    title: "Material & Feel",
    fields: ["fabric", "weight", "stretch", "breathability", "surface_texture"],
  },
  {
    title: "Style & Occasion",
    fields: ["formality", "vibe_tags", "occasion_tags", "layering_position"],
  },
  {
    title: "Seasonality",
    fields: ["season", "max_comfortable_temp_c"],
  },
  {
    title: "Condition & Usage",
    fields: ["condition", "wear_frequency_estimate"],
  },
  {
    title: "Color Science",
    fields: ["color_temperature", "skin_tone_interaction", "skin_tone_caution_flag", "contrast_level"],
  },
  {
    title: "Pairing Utility",
    fields: ["versatility_score", "role_in_outfit", "volume_visual_weight"],
  },
  {
    title: "Shoes Only",
    fields: ["shoe_type", "sole_profile", "aesthetic_range", "top_compatibility_note"],
  },
  {
    title: "Client Notes",
    fields: ["client_notes"],
  },
];

const numberFields = new Set(["formality", "versatility_score"]);
const longFields = new Set([
  "drape_notes",
  "fit_source",
  "vibe_tags",
  "occasion_tags",
  "skin_tone_interaction",
  "aesthetic_range",
  "top_compatibility_note",
  "client_notes",
]);

function cleanRoute(pathname) {
  return routes.includes(pathname) ? pathname : "/chat";
}

function fieldLabel(field) {
  return field
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function itemSummary(item) {
  return [item.color_primary, item.sub_category].filter(Boolean).join(" ");
}

export function App() {
  const [route, setRoute] = useState(() => cleanRoute(window.location.pathname));
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [savedOutfits, setSavedOutfits] = useState([]);
  const [catalogSummary, setCatalogSummary] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const [status, setStatus] = useState("");
  const streamRef = useRef(null);

  useEffect(() => {
    if (!routes.includes(window.location.pathname)) {
      window.history.replaceState({}, "", "/chat");
    }
    const onPopState = () => setRoute(cleanRoute(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    boot();
  }, []);

  useEffect(() => {
    if (conversationId) {
      api.listMessages(conversationId).then((data) => setMessages(data.messages));
    }
  }, [conversationId]);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  function navigate(nextRoute) {
    if (nextRoute === route) return;
    window.history.pushState({}, "", nextRoute);
    setRoute(nextRoute);
    setStatus("");
  }

  async function boot() {
    try {
      const [summary, conversationData, savedData] = await Promise.all([
        api.catalogSummary(),
        api.listConversations(),
        api.listSavedOutfits(),
      ]);
      setCatalogSummary(summary);
      setConversations(conversationData.conversations);
      setSavedOutfits(savedData.saved_outfits);
      if (conversationData.conversations[0]) {
        setConversationId(conversationData.conversations[0].id);
      } else {
        const created = await api.createConversation("Wardrobe chat");
        setConversationId(created.conversation_id);
        const refreshed = await api.listConversations();
        setConversations(refreshed.conversations);
      }
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function newConversation() {
    const created = await api.createConversation("Wardrobe chat");
    setConversationId(created.conversation_id);
    setMessages([]);
    const refreshed = await api.listConversations();
    setConversations(refreshed.conversations);
    navigate("/chat");
  }

  async function sendMessage(content = input) {
    const trimmed = content.trim();
    if (!trimmed || loading || !conversationId) return;
    setInput("");
    setLoading(true);
    setStatus("");
    setMessages((current) => [
      ...current,
      { id: `local-${Date.now()}`, role: "user", content: trimmed, structured_payload: null },
    ]);
    try {
      const data = await api.sendMessage(conversationId, trimmed);
      setMessages((current) => [...current, data.message]);
      const refreshed = await api.listConversations();
      setConversations(refreshed.conversations);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: `error-${Date.now()}`, role: "error", content: error.message, structured_payload: null },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function saveOutfit(outfit, messageId) {
    try {
      await api.saveOutfit({
        outfit,
        sourceConversationId: conversationId,
        sourceMessageId: messageId,
      });
      const saved = await api.listSavedOutfits();
      setSavedOutfits(saved.saved_outfits);
      setStatus("Outfit saved.");
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function removeSavedOutfit(savedOutfitId) {
    try {
      await api.deleteSavedOutfit(savedOutfitId);
      setSavedOutfits((current) => current.filter((outfit) => outfit.id !== savedOutfitId));
      setStatus("Saved outfit removed.");
    } catch (error) {
      setStatus(error.message);
      throw error;
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        route={route}
        navigate={navigate}
        catalogSummary={catalogSummary}
        conversations={conversations}
        conversationId={conversationId}
        setConversationId={setConversationId}
        newConversation={newConversation}
      />

      {route === "/catalog" ? (
        <CatalogPage status={status} setStatus={setStatus} navigate={navigate} onPreviewImage={setPreviewImage} />
      ) : route === "/saved" ? (
        <SavedPage
          outfits={savedOutfits}
          status={status}
          navigate={navigate}
          onRemove={removeSavedOutfit}
          onPreviewImage={setPreviewImage}
        />
      ) : (
        <ChatPage
          messages={messages}
          input={input}
          setInput={setInput}
          loading={loading}
          status={status}
          streamRef={streamRef}
          sendMessage={sendMessage}
          saveOutfit={saveOutfit}
          navigate={navigate}
          onPreviewImage={setPreviewImage}
        />
      )}

      {previewImage && <ImageModal image={previewImage} onClose={() => setPreviewImage(null)} />}
    </div>
  );
}

function Sidebar({
  route,
  navigate,
  catalogSummary,
  conversations,
  conversationId,
  setConversationId,
  newConversation,
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><Shirt size={20} /></div>
        <div>
          <h1>Wardrobe Stylist</h1>
          <p>{catalogSummary ? `${catalogSummary.items} items, ${catalogSummary.images} images` : "Local catalog"}</p>
        </div>
      </div>

      <nav className="app-nav">
        <button className={route === "/chat" ? "active" : ""} onClick={() => navigate("/chat")}>
          <MessageSquare size={17} />
          Chat
        </button>
        <button className={route === "/catalog" ? "active" : ""} onClick={() => navigate("/catalog")}>
          <List size={17} />
          Catalog
        </button>
        <button className={route === "/saved" ? "active" : ""} onClick={() => navigate("/saved")}>
          <Bookmark size={17} />
          Saved
        </button>
      </nav>

      {route === "/chat" ? (
        <>
          <button className="tool-button primary" onClick={newConversation}>
            <MessageSquarePlus size={17} />
            New Chat
          </button>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                className={conversation.id === conversationId ? "conversation active" : "conversation"}
                onClick={() => setConversationId(conversation.id)}
              >
                <span>{conversation.title}</span>
                <small>{conversation.updated_at?.slice(0, 10)}</small>
              </button>
            ))}
          </div>
        </>
      ) : route === "/catalog" ? (
        <div className="sidebar-note">
          <strong>Catalog editor</strong>
          <p>Edit live SQLite item metadata. CSV files are not updated.</p>
        </div>
      ) : (
        <div className="sidebar-note">
          <strong>Saved outfits</strong>
          <p>Saved recommendation cards are preserved as historical snapshots.</p>
        </div>
      )}
    </aside>
  );
}

function MobileNav({ route, navigate }) {
  return (
    <nav className="mobile-nav">
      <button className={route === "/chat" ? "active" : ""} onClick={() => navigate("/chat")}>
        <MessageSquare size={17} />
        Chat
      </button>
      <button className={route === "/catalog" ? "active" : ""} onClick={() => navigate("/catalog")}>
        <List size={17} />
        Catalog
      </button>
      <button className={route === "/saved" ? "active" : ""} onClick={() => navigate("/saved")}>
        <Bookmark size={17} />
        Saved
      </button>
    </nav>
  );
}

function ChatPage({
  messages,
  input,
  setInput,
  loading,
  status,
  streamRef,
  sendMessage,
  saveOutfit,
  navigate,
  onPreviewImage,
}) {
  return (
    <main className="chat-panel">
      <header className="topbar">
        <div>
          <p className="eyebrow">Single-stream stylist</p>
          <h2>Ask for a complete outfit from your wardrobe.</h2>
        </div>
        <div className="topbar-actions">
          <MobileNav route="/chat" navigate={navigate} />
          <button className="icon-text" onClick={() => navigate("/saved")}>
            <Bookmark size={18} />
            Saved
          </button>
        </div>
      </header>

      <section className="message-stream" ref={streamRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <h3>What are we dressing for?</h3>
            <p>Each recommendation must cite real catalog items and include top, bottom, and shoes.</p>
            <div className="starter-grid">
              {starterPrompts.map((prompt) => (
                <button key={prompt} onClick={() => sendMessage(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onSave={(outfit) => saveOutfit(outfit, message.id)}
            onPreviewImage={onPreviewImage}
          />
        ))}
        {loading && (
          <div className="assistant-loading">
            <Loader2 className="spin" size={18} />
            Building outfit options from catalog...
          </div>
        )}
      </section>

      {status && <div className="status-line">{status}</div>}

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          sendMessage();
        }}
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask for office, date night, boys night, restaurant, travel, brunch..."
          rows={2}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              sendMessage();
            }
          }}
        />
        <button className="send-button" disabled={loading || !input.trim()}>
          <Send size={18} />
        </button>
      </form>
    </main>
  );
}

function CatalogPage({ status, setStatus, navigate, onPreviewImage }) {
  const [filter, setFilter] = useState("all");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingItem, setEditingItem] = useState(null);
  const [editorLoading, setEditorLoading] = useState(false);

  useEffect(() => {
    loadItems(filter);
  }, [filter]);

  async function loadItems(nextFilter) {
    setLoading(true);
    setStatus("");
    try {
      const data = await api.listItems(nextFilter);
      setItems(data.items);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function openEditor(itemId) {
    setEditorLoading(true);
    setStatus("");
    try {
      const data = await api.getItem(itemId);
      setEditingItem(data.item);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setEditorLoading(false);
    }
  }

  function applyUpdatedItem(item) {
    setItems((current) => current.map((existing) => (existing.item_id === item.item_id ? item : existing)));
    setEditingItem(null);
    setStatus(`${item.item_id} saved.`);
  }

  function applyDeletedItem(itemId) {
    setItems((current) => current.filter((existing) => existing.item_id !== itemId));
    setEditingItem(null);
    setStatus(`${itemId} deleted.`);
  }

  return (
    <main className="catalog-panel">
      <header className="topbar catalog-topbar">
        <div>
          <p className="eyebrow">Catalog management</p>
          <h2>Edit live wardrobe item metadata.</h2>
        </div>
        <MobileNav route="/catalog" navigate={navigate} />
      </header>

      <section className="catalog-content">
        <div className="catalog-toolbar">
          <div className="segmented-control" aria-label="Filter item type">
            {typeFilters.map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="muted">{loading ? "Loading items..." : `${items.length} shown`}</p>
        </div>

        {status && <div className="status-line catalog-status">{status}</div>}

        <div className="item-table-shell">
          <table className="item-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Type</th>
                <th>Category</th>
                <th>Brand</th>
                <th>Color</th>
                <th>Fit</th>
                <th>Condition</th>
                <th>Vers.</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={10} className="empty-cell">No items for this filter.</td>
                </tr>
              )}
              {items.map((item) => (
                <tr key={item.item_id}>
                  <td>
                    <div className="item-id-cell">
                      {item.representative_image ? (
                        <ImageThumb
                          image={item.representative_image}
                          alt={`${item.item_id} representative`}
                          title={`Open ${item.item_id} image`}
                          onPreviewImage={onPreviewImage}
                        />
                      ) : (
                        <div className="image-placeholder"><Shirt size={18} /></div>
                      )}
                      <div>
                        <strong>{item.item_id}</strong>
                        <small>{itemSummary(item)}</small>
                      </div>
                    </div>
                  </td>
                  <td><span className="type-pill">{item.type}</span></td>
                  <td>{item.category}<small>{item.sub_category}</small></td>
                  <td>{item.brand}</td>
                  <td>{item.color_primary}</td>
                  <td>{item.fit}</td>
                  <td>{item.condition}</td>
                  <td>{item.versatility_score ?? ""}</td>
                  <td className="notes-preview">{item.client_notes}</td>
                  <td>
                    <button className="icon-button" onClick={() => openEditor(item.item_id)} title={`Edit ${item.item_id}`}>
                      <Pencil size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {editorLoading && (
        <div className="editor-loading">
          <Loader2 className="spin" size={18} />
          Loading item...
        </div>
      )}
      {editingItem && (
        <ItemEditorModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSaved={applyUpdatedItem}
          onDeleted={applyDeletedItem}
          onPreviewImage={onPreviewImage}
        />
      )}
    </main>
  );
}

function SavedPage({ outfits, status, navigate, onRemove, onPreviewImage }) {
  return (
    <main className="catalog-panel saved-panel">
      <header className="topbar">
        <div>
          <p className="eyebrow">Saved outfits</p>
          <h2>Review saved recommendation cards.</h2>
        </div>
        <MobileNav route="/saved" navigate={navigate} />
      </header>

      <section className="saved-content">
        <div className="catalog-toolbar">
          <p className="muted">{outfits.length === 1 ? "1 saved outfit" : `${outfits.length} saved outfits`}</p>
        </div>

        {status && <div className="status-line catalog-status">{status}</div>}

        {outfits.length === 0 ? (
          <div className="empty-state saved-empty">
            <h3>No saved outfits yet.</h3>
            <p>Save an outfit from chat and it will appear here as the same full recommendation card.</p>
            <button className="tool-button primary" onClick={() => navigate("/chat")}>
              <MessageSquare size={17} />
              Open Chat
            </button>
          </div>
        ) : (
          <div className="outfit-grid saved-outfit-grid">
            {outfits.map((outfit) => (
              <OutfitCard
                key={outfit.id}
                outfit={outfit}
                onRemove={() => onRemove(outfit.id)}
                onPreviewImage={onPreviewImage}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function ItemEditorModal({ item, onClose, onSaved, onDeleted, onPreviewImage }) {
  const initialForm = useMemo(() => {
    const next = {};
    fieldGroups.forEach((group) => {
      group.fields.forEach((field) => {
        next[field] = item[field] ?? "";
      });
    });
    return next;
  }, [item]);

  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm(initialForm);
  }, [initialForm]);

  function setField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function saveChanges(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const data = await api.updateItem(item.item_id, form);
      onSaved(data.item);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      setError("");
      return;
    }
    setDeleting(true);
    setError("");
    try {
      await api.deleteItem(item.item_id);
      onDeleted(item.item_id);
    } catch (deleteError) {
      setError(deleteError.message);
      setConfirmingDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="item-editor" onClick={(event) => event.stopPropagation()}>
        <header className="editor-header">
          <div className="editor-title">
            {item.representative_image && (
              <ImageThumb
                image={item.representative_image}
                alt={`${item.item_id} representative`}
                title={`Open ${item.item_id} representative image`}
                onPreviewImage={onPreviewImage}
              />
            )}
            <div>
              <p className="eyebrow">Editing item</p>
              <h2>{item.item_id}</h2>
              <p>{itemSummary(item)}</p>
            </div>
          </div>
          <button className="icon-button" onClick={onClose} title="Close editor">
            <X size={18} />
          </button>
        </header>

        <div className="editor-images">
          {item.images?.map((image) => (
            <figure key={image.id}>
              <ImageThumb
                image={image}
                alt={`${item.item_id} reference`}
                title={`Open ${item.item_id} reference image`}
                onPreviewImage={onPreviewImage}
              />
              {image.image_reference && <figcaption>{image.image_reference}</figcaption>}
            </figure>
          ))}
        </div>

        <form className="editor-form" onSubmit={saveChanges}>
          {fieldGroups.map((group) => (
            <fieldset key={group.title}>
              <legend>{group.title}</legend>
              <div className="field-grid">
                {group.fields.map((field) => (
                  <label key={field} className={longFields.has(field) ? "field wide" : "field"}>
                    <span>{fieldLabel(field)}</span>
                    {longFields.has(field) ? (
                      <textarea
                        value={form[field]}
                        onChange={(event) => setField(field, event.target.value)}
                        rows={field === "client_notes" ? 4 : 3}
                      />
                    ) : (
                      <input
                        type={numberFields.has(field) ? "number" : "text"}
                        value={form[field]}
                        onChange={(event) => setField(field, event.target.value)}
                        min={numberFields.has(field) ? 1 : undefined}
                        max={numberFields.has(field) ? 5 : undefined}
                      />
                    )}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          {error && <div className="error-line">{error}</div>}

          <footer className="editor-actions">
            <button
              type="button"
              className={confirmingDelete ? "danger-button confirm" : "danger-button"}
              onClick={deleteItem}
              disabled={deleting || saving}
            >
              {deleting ? <Loader2 className="spin" size={17} /> : <Trash2 size={17} />}
              {confirmingDelete ? "Confirm delete" : "Delete item"}
            </button>
            <button type="button" className="icon-text" onClick={onClose}>
              <X size={17} />
              Cancel
            </button>
            <button className="tool-button primary" disabled={saving}>
              {saving ? <Loader2 className="spin" size={17} /> : <Save size={17} />}
              Save
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function MessageBubble({ message, onSave, onPreviewImage }) {
  const payload = message.structured_payload;
  if (payload?.outfits?.length) {
    return (
      <article className="message assistant">
        <p className="assistant-summary">{payload.assistant_summary}</p>
        <div className="outfit-grid">
          {payload.outfits.map((outfit, index) => (
            <OutfitCard
              key={`${outfit.title}-${index}`}
              outfit={outfit}
              onSave={() => onSave(outfit)}
              onPreviewImage={onPreviewImage}
            />
          ))}
        </div>
      </article>
    );
  }
  return (
    <article className={`message ${message.role}`}>
      <p>{message.content}</p>
    </article>
  );
}

function OutfitCard({ outfit, onSave, onRemove, onPreviewImage }) {
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [removing, setRemoving] = useState(false);

  useEffect(() => {
    setConfirmingRemove(false);
    setRemoving(false);
  }, [outfit.id]);

  async function removeOutfit() {
    if (!confirmingRemove) {
      setConfirmingRemove(true);
      return;
    }
    setRemoving(true);
    try {
      await onRemove();
    } catch {
      setConfirmingRemove(false);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <section className="outfit-card">
      <div className="outfit-header">
        <div>
          <h3>{outfit.title}</h3>
          <div className="labels">
            <span>{outfit.time_of_day}</span>
            <span>{outfit.occasion}</span>
          </div>
        </div>
        {onRemove ? (
          <button
            className={confirmingRemove ? "save-button remove-button confirm" : "save-button remove-button"}
            onClick={removeOutfit}
            title={confirmingRemove ? "Confirm remove saved outfit" : "Remove saved outfit"}
            disabled={removing}
          >
            {removing ? <Loader2 className="spin" size={17} /> : <Trash2 size={17} />}
          </button>
        ) : (
          <button className="save-button" onClick={onSave} title="Save outfit">
            <Bookmark size={17} />
          </button>
        )}
      </div>
      <p className="stylist-notes">{outfit.stylist_notes}</p>
      <div className="note-pair">
        {outfit.why_it_works && <p><strong>Why:</strong> {outfit.why_it_works}</p>}
        {outfit.wearing_notes && <p><strong>Wear:</strong> {outfit.wearing_notes}</p>}
        {outfit.cautions && <p><strong>Watch:</strong> {outfit.cautions}</p>}
      </div>
      <div className="item-citations">
        {outfit.items?.map((outfitItem) => (
          <CitationItem
            key={outfitItem.item_id}
            item={outfitItem}
            role={outfit.item_roles?.[outfitItem.item_id]}
            onPreviewImage={onPreviewImage}
          />
        ))}
      </div>
    </section>
  );
}

function CitationItem({ item, role, onPreviewImage }) {
  const [expanded, setExpanded] = useState(false);
  const representative = item.images?.find((image) => image.is_representative) || item.images?.[0];
  const extraImages = item.images?.filter((image) => image.id !== representative?.id) || [];
  const removed = Boolean(item.deleted_at);
  return (
    <div className={removed ? "citation-item removed" : "citation-item"}>
      {representative && (
        <ImageThumb
          image={representative}
          alt={`${item.item_id} representative`}
          title={`Open ${item.item_id} representative image`}
          onPreviewImage={onPreviewImage}
        />
      )}
      <div className="citation-copy">
        <div className="citation-title">
          <strong>{item.item_id}</strong>
          <span className={removed ? "removed-label" : ""}>{removed ? "Removed from catalog" : role || item.category}</span>
        </div>
        <p>{item.color_primary} {item.sub_category}</p>
        {extraImages.length > 0 && (
          <>
            <button className="expand-link" onClick={() => setExpanded(!expanded)}>
              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              <Images size={15} />
              {extraImages.length} more
            </button>
            {expanded && (
              <div className="extra-images">
                {extraImages.map((image) => (
                  <ImageThumb
                    key={image.id}
                    image={image}
                    alt={`${item.item_id} citation`}
                    title={`Open ${item.item_id} citation image`}
                    onPreviewImage={onPreviewImage}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ImageThumb({ image, alt, title, onPreviewImage }) {
  return (
    <button
      type="button"
      className="image-thumb"
      onClick={() => onPreviewImage({ ...image, alt })}
      title={title || "Open image"}
    >
      <img src={imageUrl(image.id)} alt={alt} />
    </button>
  );
}

function ImageModal({ image, onClose }) {
  return (
    <div className="image-modal-backdrop" onClick={onClose}>
      <section className="image-modal" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <h2>{image.image_reference || image.alt || "Wardrobe image"}</h2>
          </div>
          <button className="modal-close" onClick={onClose} title="Close image">
            <X size={18} />
          </button>
        </header>
        <div className="modal-image-frame">
          <img src={imageUrl(image.id)} alt={image.alt || "Wardrobe item image"} />
        </div>
      </section>
    </div>
  );
}
