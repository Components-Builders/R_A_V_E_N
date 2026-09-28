import { useEffect, useRef } from 'react';
import logo from '../../src/assets/logo.png'
import Composer from '../../src/ui/Composer';
import MessageBubble from '../../src/ui/MessageBubble';
import { Message, PendingConfirm } from 'src/useRaven';

interface ChatStageProps {
    messages: Message[];
    busy: boolean;
    statusText: string | null;
    error: string | null;
    connected: boolean;
    pendingConfirm: PendingConfirm | null;
    onSend: (text: string) => void;
    onDismissError: () => void;
}

const ChatStage = ({
    messages, busy, statusText, error, connected, pendingConfirm, onSend, onDismissError,
}: ChatStageProps) => {
    const endRef = useRef<HTMLDivElement>(null);

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
                    messages.map((m, i) => <MessageBubble key={i} m={m} />)
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

            <Composer connected={connected} busy={busy} blocked={!!pendingConfirm} onSend={onSend} />
        </main>
    )
}

export default ChatStage
