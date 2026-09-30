import { useRef, useState, useEffect } from 'react';
import { CustomThinkingOrb } from '../ui/ThinkingOrb';
import { PushToTalkRecorder } from '../lib/pushToTalk';
import { useEffectiveTheme, useSettings } from '../useSettings';

type Phase = 'idle' | 'opening' | 'recording' | 'transcribing' | 'review' | 'error';

interface VoiceStageProps {
  connected: boolean;
  busy: boolean; // an ask() is already in flight
  requestTranscribe: (audioBase64: string) => Promise<string>;
  onSend: (text: string) => void;
}

/**
 * Push-to-talk: hold Shift to record, release to stop. What happens next
 * depends on "Send automatically" (persisted in localStorage, off by
 * default -- same "never auto-submit what it hears" posture as the CLI's
 * own Ctrl+V, see raven/voice.py's docstring):
 *   - off: the transcript is shown for the user to edit and explicitly
 *     send or discard.
 *   - on: the transcript is sent straight to the model on release.
 *
 * Recording only ever runs while this component is mounted (i.e. the Voice
 * mode tab is open) -- App.tsx only renders it then, so the window
 * key listeners here never compete with typing in the Chat stage's Composer.
 */
function VoiceStage({ connected, busy, requestTranscribe, onSend }: VoiceStageProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [transcript, setTranscript] = useState('');
  const [message, setMessage] = useState<string | null>(null); // error / hint text
  // "Send automatically" now lives in Settings (SettingsPanel.tsx), not as an
  // inline checkbox here -- useSettings() keeps this in sync with it.
  const { voiceAutoSend, reduceMotion } = useSettings();
  const effectiveTheme = useEffectiveTheme();
  const recorderRef = useRef<PushToTalkRecorder | null>(null);
  if (!recorderRef.current) recorderRef.current = new PushToTalkRecorder();
  // Tracks whether Shift is physically down right now, independent of `phase` --
  // opening the mic (getUserMedia + AudioContext) is async and can easily take
  // longer than a quick tap-and-release, so the keyup handler alone can't be
  // trusted to see the recorder already started. See the keydown handler below.
  const shiftHeldRef = useRef(false);

  const disabled = !connected || busy;

  const finishRecording = async () => {
    const audio = recorderRef.current!.stop();
    if (!audio) {
      setPhase('idle');
      return;
    }
    setPhase('transcribing');
    try {
      const text = await requestTranscribe(audio);
      if (!text.trim()) {
        setMessage("Didn't catch anything -- try holding Shift a little longer.");
        setPhase('idle');
        return;
      }
      if (voiceAutoSend) {
        onSend(text);
        setPhase('idle');
      } else {
        setTranscript(text);
        setPhase('review');
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Transcription failed.');
      setPhase('error');
    }
  };

  useEffect(() => {
    // NON_TEXT_INPUT_TYPES: an <input> of one of these doesn't accept text, so
    // it has no legitimate use for Shift (the auto-send checkbox is exactly
    // this case -- focusing it must never silently block push-to-talk).
    const NON_TEXT_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'range', 'color', 'file']);
    const isEditable = (el: EventTarget | null) => {
      if (!(el instanceof HTMLElement)) return false;
      if (el.isContentEditable) return true;
      if (el.tagName === 'TEXTAREA') return true;
      if (el.tagName === 'INPUT') return !NON_TEXT_INPUT_TYPES.has((el as HTMLInputElement).type);
      return false;
    };

    const onKeyDown = (e: KeyboardEvent) => {
      // Editing the reviewed transcript needs Shift for its ordinary job
      // (capitals, Shift+Home, ...) -- never hijack it there.
      if (e.key !== 'Shift' || e.repeat || isEditable(e.target)) return;
      if (disabled || phase !== 'idle') return;
      setMessage(null);
      shiftHeldRef.current = true;
      setPhase('opening');
      recorderRef.current!.start()
        .then(() => {
          // Shift may already have been released while the mic was still
          // opening (a quick tap) -- if so, stop immediately instead of
          // getting stuck "recording" forever with no keyup left to catch it.
          if (shiftHeldRef.current) setPhase('recording');
          else void finishRecording();
        })
        .catch((err: unknown) => {
          setMessage(
            err instanceof Error && err.name === 'NotAllowedError'
              ? 'Microphone access was denied. Allow it for R.A.V.E.N and try again.'
              : `Could not access the microphone: ${err instanceof Error ? err.message : err}`,
          );
          setPhase('error');
        });
    };

    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key !== 'Shift') return;
      shiftHeldRef.current = false;
      // If the mic is still mid-open, the pending start().then() above will
      // notice shiftHeldRef is now false and stop as soon as it resolves.
      if (recorderRef.current!.isRecording) void finishRecording();
    };

    // The mic must never be left open if focus leaves the app entirely
    // (e.g. alt-tab) while Shift is still physically held down.
    const onBlur = () => {
      shiftHeldRef.current = false;
      if (recorderRef.current!.isRecording) void finishRecording();
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', onBlur);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
      // NOT recorderRef.current!.stop() here: this cleanup also runs on every
      // ordinary phase/disabled/autoSend change (to pick up fresh closures),
      // not just on unmount -- stopping the recorder here too would cut off
      // an in-progress recording the instant its own phase transition (e.g.
      // 'opening' -> 'recording') re-ran this effect. The unmount-only stop
      // is the separate effect below.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- finishRecording closes over
    // state that would otherwise re-subscribe these listeners on every keystroke of the review textarea
  }, [disabled, phase, voiceAutoSend]);

  // Runs its cleanup ONLY on true unmount ([] deps) -- leaving the Voice tab
  // (switching modes) or the component going away for any other reason must
  // never leave the microphone open behind it.
  useEffect(() => () => { recorderRef.current!.stop(); }, []);

  const send = () => {
    if (!transcript.trim()) return;
    onSend(transcript);
    setTranscript('');
    setPhase('idle');
  };

  const discard = () => {
    setTranscript('');
    setPhase('idle');
  };

  // Canvas fillStyle needs a real CSS color, not a Tailwind token name -- these
  // match index.css's @theme --color-ink/--color-danger VALUES for each theme
  // (a <canvas> can't read a CSS variable the way a utility class does, so
  // useEffectiveTheme() resolves 'system' to an actual light/dark literal).
  const COLORS = {
    light: { still: '#6d6e72', danger: '#8a1c1c', recording: '#05080f' },
    dark: { still: '#eef0f3', danger: '#e2685f', recording: '' },
  } as const;
  const palette = COLORS[effectiveTheme];
  const orbColor = phase === 'recording' ? palette.recording : phase === 'error' ? palette.danger : palette.still;
  // "Reduce motion" (Settings): a static frame instead of a continuous spin.
  const orbSpeed = reduceMotion ? 0 : phase === 'recording' ? 2.2 : phase === 'transcribing' || phase === 'opening' ? 1.4 : 0.6;

  return (
    <main className="flex min-h-0 flex-col items-center justify-center gap-8 border-y border-line-soft px-6">
      {phase === 'review' ? (
        <div className="flex w-full max-w-lg flex-col gap-3">
          <div className="text-[0.85rem] text-ink-dim">Here's what R.A.V.E.N heard -- edit if needed, then send.</div>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            autoFocus
            rows={4}
            className="w-full resize-none border border-line bg-panel px-3.5 py-2.5 text-[0.92rem] outline-none focus:border-ink"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={discard}
              className="cursor-pointer border border-ink px-5 py-2 text-[0.8rem] font-semibold text-ink"
            >
              Discard
            </button>
            <button
              onClick={send}
              disabled={!transcript.trim()}
              className="cursor-pointer bg-strong px-6 py-2 text-[0.8rem] font-semibold text-onstrong disabled:cursor-not-allowed disabled:opacity-45"
            >
              Send
            </button>
          </div>
        </div>
      ) : (
        <>
          <CustomThinkingOrb
            size={220}
            color={orbColor}
            shapeSize={2.2}
            speed={orbSpeed}
            rotation={phase === 'recording' ? 'pulse' : 'dualAxis'}
          />
          <span className="text-center text-[0.95rem] tracking-wide text-ink-dim">
            {disabled ? (
              !connected ? (
                'Waiting for R.A.V.E.N...'
              ) : (
                'R.A.V.E.N is working -- wait for it to finish.'
              )
            ) : phase === 'opening' ? (
              'Opening the microphone...'
            ) : phase === 'recording' ? (
              <strong className="text-ink">Listening... release [ Shift ] to stop</strong>
            ) : phase === 'transcribing' ? (
              'Transcribing...'
            ) : (
              <>
                Hold <strong className="text-ink">[ Shift ]</strong> to talk, release to stop recording.
              </>
            )}
          </span>
          {message && (
            <div role="alert" className="max-w-md border border-danger px-3 py-2 text-center text-[0.82rem] text-danger">
              {message}
            </div>
          )}
        </>
      )}
    </main>
  );
}

export default VoiceStage;
