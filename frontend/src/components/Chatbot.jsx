import { useState, useRef, useEffect } from "react";
import axios from "axios";

export const Chatbot = ({ shipmentId, onOpenChange }) => {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hello! I am your ColdChain AI Copilot. Ask me about consignment spoilage risks, Arrhenius kinetic exposures, LSTM forecasts, packaging integrity, or mitigation recommendations.",
    },
  ]);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (open) {
      scrollToBottom();
    }
  }, [messages, open]);

  const setPanelOpen = (next) => {
    setOpen(next);
    onOpenChange?.(next);
  };

  const send = async (e, customText) => {
    e?.preventDefault?.();
    const text = (customText || input).trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text }]);
    setBusy(true);

    try {
      const body = { message: text };
      if (shipmentId != null) body.shipment_id = shipmentId;
      const res = await axios.post("/api/chat", body, { timeout: 30000 });
      const reply = res.data?.reply || "No reply was returned from the AI assistant.";
      setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err.message ||
        "Chat request failed";
      setError(detail);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `I encountered an issue processing your request: ${detail}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const quickPrompts = shipmentId != null
    ? [
        `What is the risk assessment for Shipment #${shipmentId}?`,
        "Are there any active temperature excursions?",
        "What are the top SHAP contributing factors?",
      ]
    : [
        "Summarize current high-risk consignments.",
        "What are standard safe temperature bounds for biologics?",
        "How is the spoilage risk score calculated?",
      ];

  return (
    <div className={`modern-chatbot-widget ${open ? "is-open" : ""}`}>
      {!open ? (
        <button
          className="chatbot-launcher-btn"
          type="button"
          onClick={() => setPanelOpen(true)}
          title="Open ColdChain AI Assistant"
        >
          <div className="launcher-icon-wrap">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="launcher-pulse-dot" />
          </div>
          <span className="launcher-text">AI Assistant</span>
        </button>
      ) : (
        <div className="chatbot-floating-panel">
          {/* Header */}
          <div className="chatbot-panel-header">
            <div className="chat-header-title-wrap">
              <div className="chat-avatar-icon">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
                  <rect x="4" y="8" width="16" height="12" rx="2" />
                  <circle cx="9" cy="13" r="1" />
                  <circle cx="15" cy="13" r="1" />
                  <path d="M9 17h6" />
                </svg>
              </div>
              <div>
                <div className="chat-assistant-name">ColdChain AI Copilot</div>
                <div className="chat-context-badge">
                  <span className="online-indicator-dot" />
                  <span>
                    {shipmentId != null ? `Shipment #${shipmentId} Active` : "Fleet Global Context"}
                  </span>
                </div>
              </div>
            </div>

            <button
              className="chat-close-btn"
              type="button"
              onClick={() => setPanelOpen(false)}
              title="Close Chat"
            >
              ×
            </button>
          </div>

          {/* Quick Prompts */}
          {messages.length <= 1 && (
            <div className="quick-prompts-bar">
              <span className="prompts-label">Suggested Inquiries:</span>
              <div className="prompts-list">
                {quickPrompts.map((promptText, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="prompt-chip"
                    onClick={(e) => send(e, promptText)}
                  >
                    {promptText}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages list */}
          <div className="chatbot-messages-scroll">
            {messages.map((m, i) => (
              <div key={i} className={`chat-message-row role-${m.role}`}>
                {m.role === "assistant" && (
                  <div className="bubble-avatar-tag">AI</div>
                )}
                <div className={`chat-bubble-bubble bubble-${m.role}`}>
                  {m.text}
                </div>
              </div>
            ))}

            {busy && (
              <div className="chat-message-row role-assistant">
                <div className="bubble-avatar-tag">AI</div>
                <div className="chat-bubble-bubble bubble-assistant thinking-bubble">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {error && <div className="chat-error-banner">{error}</div>}

          {/* Input form */}
          <form className="chatbot-input-form" onSubmit={send}>
            <input
              type="text"
              className="chat-text-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                shipmentId != null
                  ? `Ask about Shipment #${shipmentId}...`
                  : "Ask about fleet conditions, risk..."
              }
              disabled={busy}
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={busy || !input.trim()}
              title="Send message"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
