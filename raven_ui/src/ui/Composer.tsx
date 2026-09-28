import { useEffect, useRef, useState } from 'react';

const MAX_HEIGHT_PX = 200; // ~8 lines before it scrolls internally instead of growing forever

function Composer({
    connected, busy, blocked, onSend,
}: {
    connected: boolean;
    busy: boolean;
    blocked: boolean; // an approval is pending
    onSend: (text: string) => void;
}) {
    const [input, setInput] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const send = () => {
        if (!input.trim() || busy) return;
        onSend(input);
        setInput('');
    };

    // Auto-grow with content instead of scrolling sideways, capped at
    // MAX_HEIGHT_PX (a textarea's scrollHeight already accounts for wrapped
    // lines, so this alone handles both "more text" and "wraps to a new line").
    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
    }, [input]);

    return (
        <div className="flex items-end gap-2.5 border-t border-line-soft py-3.5 noScrollbar">
            <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                    // Enter sends; Shift+Enter inserts a newline instead (the textarea's own default).
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                    }
                }}
                placeholder={!connected ? 'Waiting for R.A.V.E.N...' : busy ? 'R.A.V.E.N is working...' : 'Message R.A.V.E.N (Shift+Enter for a new line)'}
                disabled={!connected || blocked}
                autoFocus
                rows={1}
                className="max-h-[200px] flex-1 resize-none noScrollbar overflow-y-auto border border-line px-3.5 py-2.5 text-[0.92rem] leading-normal outline-none focus:border-ink disabled:cursor-not-allowed disabled:opacity-45"
            />
            <button
                onClick={send}
                disabled={!connected || busy || blocked || !input.trim()}
                className="cursor-pointer bg-strong px-6 py-2.5 text-[0.85rem] font-semibold text-onstrong disabled:cursor-not-allowed disabled:opacity-45"
            >
                Send
            </button>
        </div>
    );
}

export default Composer
