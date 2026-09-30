import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * WebSocket client for raven/server.py's /ws protocol. Mirrors the message
 * shapes defined there exactly -- see server.py's own docstring for the
 * server-side half of this contract (Session.handle_message /
 * Session._confirm_run / Session._on_tool_call).
 */

export type Message = { role: 'user' | 'raven'; text: string };
export type ChatSession = { id: number; title: string; updated_at: number };
export type PendingConfirm = { id: string; prompt: string };
export type ToolEvent = { id: number; label: string };

type ServerMessage =
  | { type: 'history'; session: number; items: { role: 'user' | 'assistant'; text: string }[] }
  | { type: 'sessions'; current: number; items: ChatSession[] }
  | { type: 'reply'; text: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'confirm_request'; id: string; prompt: string }
  | { type: 'error'; message: string }
  | { type: 'stats'; segments: { name: string; text: string }[] }
  | { type: 'transcript'; id: string; text: string }
  | { type: 'transcript_error'; id: string; message: string }
  | { type: 'model_config'; provider: string; name: string }
  | { type: 'models'; provider: string; items: string[] }
  | { type: 'models_error'; provider: string; message: string }
  | { type: 'cancel_requested' }
  | { type: 'cancelled' };

export type StatSegment = { name: string; text: string };
export type ModelConfig = { provider: string; name: string };


const SERVER_URL = 'ws://127.0.0.1:8756/ws';
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 10000;

const THINKING_WORDS = [
  "Working on it...",
  "Thinking...",
  "Ravening...",
  "Swimming...",
  "Calculating...",
  "Casting...",
  "Mogging...",
  "Smoking...",
  "Pasting...",
  "Burning...",
  "Evaporating...",
  "Hallucinating...",
  "Demotivating...",
  "Catastrophing...",
  "Ctrl+C-ing...",
  "Ctrl+V-ing...",
  "Whispering...",
  "Traveling...",
  "Cooking...",
  "Eating...",
  "Combusting...",
  "Vibe coding...",
  "Crushing...",

]

export function useRaven() {
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false); // an ask is in flight
  // True from the moment cancel_ask is sent until the server confirms the
  // turn actually settled ("cancelled") -- the underlying call can't be
  // forcibly stopped (raven/server.py's _AskToken), so it keeps running in
  // the background for however long it takes; this just distinguishes
  // "waiting for a reply" from "waiting for a cancelled reply to be discarded"
  // in the UI. busy stays true the whole time either way -- see cancelAsk().
  const [cancelling, setCancelling] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [stats, setStats] = useState<StatSegment[]>([]);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<number | null>(null);
  const [toolLog, setToolLog] = useState<ToolEvent[]>([]); // tool calls of the current/last turn
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, string[]>>({});
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const toolId = useRef(0);
  // Pending push-to-talk transcriptions: id -> the promise's resolve/reject,
  // so requestTranscribe() can be awaited from VoiceStage even though the
  // answer arrives later as an ordinary, id-tagged websocket message.
  const pendingTranscriptions = useRef(new Map<string, { resolve: (text: string) => void; reject: (err: Error) => void }>());

  // for randomly switching between thinking words
  useEffect(() => {
    if (!busy) {
      setStatusText(null);
      return;
    }
    if (cancelling) {
      setStatusText('Cancelling...');
      return;
    }
    if (toolStatus) {
      setStatusText(toolStatus);
      return;
    }
    const pick = () => THINKING_WORDS[Math.floor(Math.random() * THINKING_WORDS.length)];
    setStatusText(pick());
    const id = setInterval(() => setStatusText(pick()), 5000);
    return () => clearInterval(id);
  }, [busy, toolStatus, cancelling]);

  useEffect(() => {
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let delay = RECONNECT_MIN_MS;

    const connect = () => {
      const ws = new WebSocket(SERVER_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        delay = RECONNECT_MIN_MS;
        setConnected(true);
        setError(null);
        ws.send(JSON.stringify({ type: 'get_history' }));
        ws.send(JSON.stringify({ type: 'list_sessions' }));
      };

      ws.onclose = () => {
        setConnected(false);
        // Whatever was in flight can never complete on a dead socket -- don't leave the UI "thinking" forever.
        setBusy(false);
        setCancelling(false);
        setToolStatus(null);
        setPendingConfirm(null);
        setStats([]);
        // A dead socket can never deliver these -- fail every push-to-talk
        // still awaiting a transcript instead of leaving it hanging forever.
        pendingTranscriptions.current.forEach(({ reject }) => reject(new Error('Connection lost while transcribing.')));
        pendingTranscriptions.current.clear();
        if (disposed) return;
        retryTimer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
      };

      // onerror is always followed by onclose, which owns the retry; just say what's wrong.
      ws.onerror = () => setError('Cannot reach R.A.V.E.N -- start it with: python -m raven.server (retrying...)');

      ws.onmessage = (event) => {
        let data: ServerMessage;
        try {
          data = JSON.parse(event.data);
        } catch {
          setError('Received an unreadable message from the server.');
          return;
        }
        switch (data.type) {
          case 'history':
            // The server's open chat: replaces what's shown (also on reconnect and when switching chats).
            setMessages(data.items.map((it) => ({ role: it.role === 'user' ? 'user' : 'raven', text: it.text })));
            setCurrentSession(data.session);
            setToolLog([]);
            setError(null);
            break;
          case 'sessions':
            setSessions(data.items);
            setCurrentSession(data.current);
            break;
          case 'reply':
            setBusy(false);
            setCancelling(false);
            setToolStatus(null);
            setMessages((m) => [...m, { role: 'raven', text: data.text }]);
            break;
          case 'tool_call': {
            const label = toolStatusText(data.name, data.args);
            setToolStatus(label);
            setToolLog((log) => [...log, { id: ++toolId.current, label }]);
            break;
          }
          case 'stats':
            setStats(data.segments);
            break;
          case 'transcript': {
            const pending = pendingTranscriptions.current.get(data.id);
            pendingTranscriptions.current.delete(data.id);
            pending?.resolve(data.text);
            break;
          }
          case 'transcript_error': {
            const pending = pendingTranscriptions.current.get(data.id);
            pendingTranscriptions.current.delete(data.id);
            pending?.reject(new Error(data.message));
            break;
          }
          case 'model_config':
            setModelConfig({ provider: data.provider, name: data.name });
            break;
          case 'models':
            setModelsLoading(false);
            setModelsError(null);
            setModelsByProvider((m) => ({ ...m, [data.provider]: data.items }));
            break;
          case 'models_error':
            setModelsLoading(false);
            setModelsError(data.message);
            break;
          case 'confirm_request':
            setPendingConfirm({ id: data.id, prompt: data.prompt });
            break;
          case 'cancel_requested':
            setCancelling(true);
            break;
          case 'cancelled':
            setBusy(false);
            setCancelling(false);
            setToolStatus(null);
            break;
          case 'error':
            setBusy(false);
            setCancelling(false);
            setToolStatus(null);
            setError(data.message);
            break;
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  const ask = useCallback((text: string) => {
    if (!text.trim()) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError('Not connected to R.A.V.E.N -- your message was not sent.');
      return;
    }
    setError(null);
    setToolLog([]);
    setToolStatus(null)
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    // setStatusText('Thinking');
    ws.send(JSON.stringify({ type: 'ask', text }));
  }, []);

  const respondToConfirm = useCallback(
    (approved: boolean) => {
      const ws = wsRef.current;
      if (!pendingConfirm || !ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: 'confirm_response', id: pendingConfirm.id, approved }));
      setPendingConfirm(null);
    },
    [pendingConfirm],
  );

  const dismissError = useCallback(() => setError(null), []);

  /**
   * Cancel the in-flight ask(), if any. The underlying call can't actually be
   * stopped (see server.py's _AskToken) -- this just tells the server to
   * discard whatever it eventually returns, and switches the UI from
   * "Thinking" to "Cancelling..." until that settles ("cancelled" comes
   * back). Composer stays disabled the whole time: allowing a new message
   * before the old one truly settles would risk two turns mutating history
   * at once.
   */
  const cancelAsk = useCallback(() => {
    const ws = wsRef.current;
    if (!busy || cancelling || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'cancel_ask' }));
  }, [busy, cancelling]);

  /**
   * Send captured audio (16-bit PCM, little-endian, mono, base64-encoded --
   * see VoiceStage.tsx for the capture side) for transcription and resolve
   * with the resulting text. Deliberately NOT surfaced through the shared
   * `error` banner -- a failed push-to-talk (mic denied, model not
   * downloaded) is VoiceStage's own concern, not something that should
   * interrupt whatever's shown in the Chat stage.
   */
  const requestTranscribe = useCallback((audioBase64: string): Promise<string> => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Not connected to R.A.V.E.N.'));
    }
    const id = `t${++toolId.current}-${Date.now()}`;
    return new Promise<string>((resolve, reject) => {
      pendingTranscriptions.current.set(id, { resolve, reject });
      ws.send(JSON.stringify({ type: 'transcribe', audio: audioBase64, id }));
    });
  }, []);

  const sendControl = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError('Not connected to R.A.V.E.N.');
      return;
    }
    ws.send(JSON.stringify(payload));
  }, []);
  const newSession = useCallback(() => sendControl({ type: 'new_session' }), [sendControl]);
  const openSession = useCallback((id: number) => sendControl({ type: 'open_session', id }), [sendControl]);
  const deleteSession = useCallback((id: number) => sendControl({ type: 'delete_session', id }), [sendControl]);

  // Model provider/name (SettingsPanel.tsx): current config, the NVIDIA
  // catalog for a given API key, and switching. Plain request/state (not a
  // promise, unlike requestTranscribe) -- Settings is a view, not something
  // driven imperatively from a single call site.
  const getModelConfig = useCallback(() => sendControl({ type: 'get_model_config' }), [sendControl]);
  const listModels = useCallback(
    (provider: string) => {
      setModelsLoading(true);
      setModelsError(null);
      sendControl({ type: 'list_models', provider });
    },
    [sendControl],
  );
  const setModel = useCallback(
    (provider: string, name: string) => sendControl({ type: 'set_model', provider, name }),
    [sendControl],
  );

  return {
    connected, messages, busy, cancelling, statusText, toolLog, pendingConfirm, error, sessions, currentSession, stats,
    modelConfig, modelsByProvider, modelsLoading, modelsError,
    ask, cancelAsk, respondToConfirm, dismissError, newSession, openSession, deleteSession, requestTranscribe,
    getModelConfig, listModels, setModel,
  };
}

// Same spirit as cli.py's TOOL_STATUS -- a short, human phrase per tool,
// falling back to a generic one for anything not explicitly listed here.
function toolStatusText(name: string, args: Record<string, unknown>): string {
  const path = typeof args.path === 'string' ? args.path : undefined;
  switch (name) {
    case 'read_file':
      return `Reading ${path ?? 'a file'}`;
    case 'write_file':
      return `Writing ${path ?? 'a file'}`;
    case 'edit_file':
      return `Editing ${path ?? 'a file'}`;
    case 'grep':
      return `Searching "${args.pattern ?? ''}"`;
    case 'run_command':
      return `Running ${args.command ?? 'a command'}`;
    case 'load_skill':
      return `Loading skill ${args.name ?? ''}`;
    default:
      return name.replace(/_/g, ' ');
  }
}
