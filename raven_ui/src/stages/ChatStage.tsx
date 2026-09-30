import { useCallback, useEffect, useRef, useState } from 'react';
import logo from '../../src/assets/logo.png'
import Composer from '../../src/ui/Composer';
import MessageBubble from '../../src/ui/MessageBubble';
import { Message, PendingConfirm } from 'src/useRaven';

interface ChatStageProps {
    messages: Message[];
    busy: boolean;
    cancelling: boolean;
    statusText: string | null;
    error: string | null;
    connected: boolean;
    pendingConfirm: PendingConfirm | null;
    onSend: (text: string) => void;
    onCancel: () => void;
    onDismissError: () => void;
}

const ChatStage = ({
    messages, busy, cancelling, statusText, error, connected, pendingConfirm, onSend, onCancel, onDismissError,
}: ChatStageProps) => {
    const endRef = useRef<HTMLDivElement>(null);
    // A message bubble's "Edit" click loads its text here; Composer applies
    // it via its `prefill` prop. Local to this stage -- nothing outside the
    // composer needs to know a prompt is being edited.
    const [draft, setDraft] = useState<{ text: string; token: number } | null>(null);
    const draftToken = useRef(0);
    const editPrompt = useCallback((text: string) => {
        setDraft({ text, token: ++draftToken.current });
    }, []);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, busy, statusText]);

    return (
        <main className="flex min-h-0 flex-col border-y border-line-soft">
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-1.5 py-5 noScrollbar">
                {messages.length === 0 ? (
                    <div className="m-auto flex flex-col items-center gap-[1.1rem] text-[0.95rem] tracking-wide text-ink-dim">
                        <img className="raven-logo w-36 opacity-85" src={logo} alt="R.A.V.E.N" />
                        <span>Ask anything.</span>
                    </div>
                ) : (
                    messages.map((m, i) => (
                        <MessageBubble key={i} m={m} disabled={busy} onResend={onSend} onEdit={editPrompt} />
                    ))
                )}
                {busy && statusText && <div className="self-start text-[0.82rem] text-ink-dim">{statusText}</div>}
                {error && (
                    <div role="alert" className="flex justify-between gap-4 self-stretch border border-danger px-3 py-2 text-[0.85rem] text-danger">
                        <span>{error}</span>
                        <button onClick={onDismissError} aria-label="Dismiss error" className="cursor-pointer text-[1.1rem] leading-none">
                            ×
                        </button>
                    </div>
                )}
                <div ref={endRef} />
            </div>

            <Composer
                connected={connected}
                busy={busy}
                cancelling={cancelling}
                blocked={!!pendingConfirm}
                prefill={draft}
                onSend={onSend}
                onCancel={onCancel}
            />
        </main>
    )
}

export default ChatStage
