import { useState, useCallback, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_URL = `${API_BASE}/api/v1/chat`;

/**
 * Connection states for UI feedback.
 * @type {'idle'|'connecting'|'connected'|'disconnected'|'error'}
 */

export default function useChat(sessionId, { isBanked = true, onMetadata } = {}) {
  const [messages, setMessages] = useState([]);
  const [connectionState, setConnectionState] = useState('idle');
  const [currentAgent, setCurrentAgent] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const streamBufRef = useRef(null);

  const isConnected = connectionState === 'connected';

  /* ─── WebSocket connect with exponential backoff ─── */
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    setConnectionState('connecting');

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsHost = API_BASE ? new URL(API_BASE).host : location.host;
    const ws = new WebSocket(`${proto}://${wsHost}/api/v1/ws/chat/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      // Don't set connected yet — wait for the server's "connected" event
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (evt) => {
      let data;
      try {
        data = JSON.parse(evt.data);
      } catch {
        return;
      }

      switch (data.type) {
        case 'connected':
          setConnectionState('connected');
          break;

        case 'token':
          setIsStreaming(true);
          if (data.agent) setCurrentAgent(data.agent);
          streamBufRef.current = (streamBufRef.current || '') + data.content;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), { ...last, content: streamBufRef.current }];
            }
            return [...prev, {
              role: 'assistant',
              content: streamBufRef.current,
              agent: data.agent,
              _streaming: true,
            }];
          });
          break;

        case 'done':
          setIsStreaming(false);
          if (data.agent) setCurrentAgent(data.agent);
          // Capture the buffer BEFORE nulling it — the setMessages callback closes over this ref.
          // Explicit fallback chain: ref buffer → existing last.content → empty string.
          // This prevents content loss when the spread alone isn't enough.
          // eslint-disable-next-line no-case-declarations
          const _doneContent = streamBufRef.current;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), {
                ...last,
                content: _doneContent || last.content || '',
                _streaming: false,
                suggestedActions: data.suggested_actions || [],
                handoffTo: data.handoff_to,
              }];
            }
            return prev;
          });
          streamBufRef.current = null;
          if (data.metadata && (data.metadata.account_id || data.metadata.display_name)) {
            onMetadata?.(data.metadata);
          }
          break;

        case 'agent_change':
          setCurrentAgent(data.to);
          streamBufRef.current = null; // Reset buffer for new agent
          setMessages((prev) => [...prev, {
            role: 'system',
            content: _agentChangeLabel(data.from, data.to),
            agentFrom: data.from,
            agentTo: data.to,
          }]);
          break;

        case 'error':
          setIsStreaming(false);
          streamBufRef.current = null;
          setMessages((prev) => [...prev, {
            role: 'assistant',
            content: data.content || 'Hubo un error. Intenta de nuevo.',
            isError: true,
          }]);
          break;
      }
    };

    ws.onclose = () => {
      setConnectionState('disconnected');
      setIsStreaming(false);
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last._streaming) {
          return [...prev.slice(0, -1), { ...last, _streaming: false }];
        }
        return prev;
      });
      streamBufRef.current = null;
      wsRef.current = null;
      // Auto-reconnect with exponential backoff (max 30s)
      const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000);
      reconnectAttempts.current += 1;
      reconnectRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      setConnectionState('error');
      ws.close();
    };
  }, [sessionId]);

  /* ─── Send via WebSocket or HTTP SSE fallback ─── */
  const sendMessage = useCallback(async (content) => {
    const trimmed = content.trim();
    if (!trimmed) return;

    streamBufRef.current = null; // reset for new message
    // Add user message immediately
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }]);

    // Try WebSocket first
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'message',
        content: trimmed,
        is_banked: isBanked,
      }));
      return;
    }

    // ── HTTP SSE fallback ──
    setIsStreaming(true);
    try {
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId,
          stream: true,
          is_banked: isBanked,
        }),
      });

      if (!resp.ok) {
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: 'Lo siento, hubo un error. Intenta de nuevo.',
          isError: true,
        }]);
        setIsStreaming(false);
        return;
      }

      const contentType = resp.headers.get('content-type') || '';
      if (contentType.includes('text/event-stream') || contentType.includes('stream')) {
        await _handleSSE(resp, setMessages, setCurrentAgent, onMetadata);
      } else {
        // JSON fallback (non-streaming)
        const data = await resp.json();
        if (data.agent_name) setCurrentAgent(data.agent_name);
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: data.content,
          agent: data.agent_name,
          suggestedActions: data.suggested_actions || [],
          handoffTo: data.handoff_to,
          metadata: data.metadata || {},
        }]);
      }
    } catch {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: 'No se pudo conectar con el servidor.',
        isError: true,
      }]);
    } finally {
      setIsStreaming(false);
    }
  }, [sessionId, isBanked]);

  /* Cleanup on unmount */
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, []);

  return {
    messages,
    isConnected,
    connectionState,
    currentAgent,
    isStreaming,
    connect,
    sendMessage,
    setMessages,
  };
}


/* ─── SSE stream handler (HTTP fallback) ─── */

async function _handleSSE(resp, setMessages, setCurrentAgent, onMetadata) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith('data: ')) continue;
      const payload = trimmed.slice(6);
      if (payload === '[DONE]') continue;

      try {
        const parsed = JSON.parse(payload);

        // Agent change event
        if (parsed.agent_change) {
          setCurrentAgent(parsed.to);
          setMessages((prev) => [...prev, {
            role: 'system',
            content: _agentChangeLabel(parsed.from, parsed.to),
          }]);
          fullText = ''; // Reset for new agent's response
          continue;
        }

        // Token event
        const token = parsed.token || parsed.content || '';
        if (token) {
          fullText += token;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), { ...last, content: fullText }];
            }
            return [...prev, {
              role: 'assistant',
              content: fullText,
              agent: parsed.agent,
              _streaming: true,
            }];
          });
        }

        // Done event
        if (parsed.done) {
          if (parsed.agent_name) setCurrentAgent(parsed.agent_name);
          const _sseDoneContent = fullText; // capture before possible reset
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last._streaming) {
              return [...prev.slice(0, -1), {
                ...last,
                content: _sseDoneContent || last.content || '',
                _streaming: false,
                agent: parsed.agent_name,
                suggestedActions: parsed.suggested_actions || [],
                handoffTo: parsed.handoff_to,
                metadata: parsed.metadata || {},
              }];
            }
            return prev;
          });
          if (parsed.metadata && (parsed.metadata.account_id || parsed.metadata.display_name)) {
            onMetadata?.(parsed.metadata);
          }
          fullText = ''; // Reset in case handoff follows
        }
      } catch { /* skip malformed lines */ }
    }
  }
}


/* ─── Human-readable agent change labels ─── */

const AGENT_LABELS = {
  helpyy_general: 'Helpyy Hand',
  credit_evaluator: 'Evaluador de Credito',
  financial_advisor: 'Asesor Financiero',
  onboarding: 'Bienvenida',
};

function _agentChangeLabel(from, to) {
  const toLabel = AGENT_LABELS[to] || to;
  return `Conectandote con ${toLabel}...`;
}
