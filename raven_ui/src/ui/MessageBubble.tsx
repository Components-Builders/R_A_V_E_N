import React from 'react'
import { memo, useState } from 'react';
import Markdown from 'react-markdown';
import { Message } from 'src/useRaven';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';



const MessageBubble = memo(function MessageBubble({
    m, disabled, onResend, onEdit,
}: {
    m: Message;
    disabled?: boolean; // a request is in flight -- resend/edit would race it (mirrors Composer's own busy-guard)
    onResend?: (text: string) => void; // re-sends the exact text as a new message, unmodified
    onEdit?: (text: string) => void; // loads the text into the composer for the user to change before sending
}) {
    const isUser = m.role === 'user';
    // Transient "Copied" label instead of a toast -- the button itself is the
    // only feedback needed for a one-off, low-stakes action like this.
    const [copied, setCopied] = useState(false);

    const copy = async () => {
        const text = m.text ?? '';
        if (!text) return;
        try {
            // Routed through main.ts via preload's IPC bridge (see
            // preload.ts) rather than calling navigator.clipboard directly:
            // Electron denies the clipboard-write permission by default for
            // web content, and only main-process code is guaranteed access
            // to the native clipboard module regardless of sandboxing.
            await window.electronClipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch (err) {
            console.error('Copy failed:', err);
            // Nothing else to fall back to -- failing silently beats
            // crashing the chat over a copy click.
        }
    };


    return (
        <div className={['group flex flex-col gap-1', isUser ? 'items-end' : 'items-start'].join(' ')}>
            <div
                className={[
                    'max-w-[78%] px-4 py-3 text-[0.92rem] leading-normal wrap-anywhere',
                    isUser ? 'bg-strong whitespace-pre-wrap text-onstrong' : 'markdown',
                ].join(' ')}
            >
                {m.role === 'raven' ? (
                    // No rehype-raw: raw HTML in a reply stays inert text, never live markup.
                    <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                        {m.text}
                    </Markdown>
                ) : (
                    m.text
                )}
            </div>
            {/* Hidden (not just faded) while not hovered, so it never reserves
                layout space -- same reveal-on-hover pattern the sidebar's
                per-chat delete button already uses. */}
            <div className="opacity-0 flex gap-3 text-[0.72rem] text-ink-dim group-hover:opacity-100 transition-opacity duration-150">
                <button onClick={copy} aria-label="Copy message" className="cursor-pointer hover:text-ink">
                    {copied ? 'Copied' : 'Copy'}
                </button>
                {isUser && onEdit && (
                    <button
                        onClick={() => onEdit(m.text)}
                        disabled={disabled}
                        aria-label="Edit prompt"
                        className="cursor-pointer hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        Edit
                    </button>
                )}
                {isUser && onResend && (
                    <button
                        onClick={() => onResend(m.text)}
                        disabled={disabled}
                        aria-label="Resend prompt"
                        className="cursor-pointer hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        Resend
                    </button>
                )}
            </div>
        </div>
    );
});

export default MessageBubble
