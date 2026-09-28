/**
 * Browser-side audio capture for push-to-talk voice input (VoiceStage.tsx).
 * Captures raw PCM at raven/voice.py's SAMPLE_RATE (16000 Hz) so the audio
 * can go straight into the existing offline faster-whisper pipeline
 * server-side -- no compressed format, no ffmpeg, the same shape
 * Recorder.stop() already hands transcribe() on the CLI's own Ctrl+V path
 * (raven/voice.py). Mirrors that Recorder's start()/stop() shape.
 */
const SAMPLE_RATE = 16000; // must match raven.voice.SAMPLE_RATE

export class PushToTalkRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];

  get isRecording(): boolean {
    return this.stream !== null;
  }

  /** Opens the mic and starts buffering. Idempotent, like Recorder.start() --
   * a second call while already recording is a no-op, not an error. Throws
   * (rejects) if permission is denied or there's no input device. */
  async start(): Promise<void> {
    if (this.stream) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Requesting the rate directly lets Chromium do any resampling itself,
    // instead of writing that math in JS.
    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    const source = context.createMediaStreamSource(stream);
    // ScriptProcessorNode is deprecated in favour of AudioWorklet, but still
    // broadly supported and far simpler here: a worklet needs its own module
    // file loaded into the audio thread, real overkill for a short-lived
    // push-to-talk capture with one onaudioprocess callback.
    const processor = context.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    processor.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    // Some browsers only fire onaudioprocess once the node reaches a
    // destination; a zero-gain node keeps the mic silent instead of echoing
    // it back through the speakers.
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(processor);
    processor.connect(mute);
    mute.connect(context.destination);

    this.stream = stream;
    this.context = context;
    this.processor = processor;
  }

  /** Stops capture and releases the mic. Returns the audio as base64-encoded
   * 16-bit PCM (mono, SAMPLE_RATE), or null if nothing was captured --
   * start() was never called, still pending, or stopped with no audio yet
   * buffered (e.g. an instant tap). */
  stop(): string | null {
    if (!this.stream) return null;
    this.processor?.disconnect();
    void this.context?.close();
    this.stream.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.context = null;
    this.processor = null;

    if (!this.chunks.length) return null;
    const length = this.chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(length);
    let offset = 0;
    for (const chunk of this.chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    this.chunks = [];
    if (length === 0) return null;

    const pcm = new Int16Array(merged.length);
    for (let i = 0; i < merged.length; i++) {
      const s = Math.max(-1, Math.min(1, merged[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return int16ToBase64(pcm);
  }
}

function int16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = '';
  const chunkSize = 0x8000; // avoid a huge single String.fromCharCode(...bytes) call on a long recording
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}
