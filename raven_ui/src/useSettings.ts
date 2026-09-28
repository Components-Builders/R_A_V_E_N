import { useEffect, useState } from 'react';

/**
 * App-wide UI settings (theme, voice, motion, stats visibility), persisted to
 * localStorage and shared across every component via a tiny module-level
 * pub/sub -- there's exactly one browser window here (this is the desktop
 * app's renderer, not a multi-tab web app), so a full Context provider would
 * be more ceremony than the problem needs. Any component calling
 * useSettings() re-renders when any setting changes, same as if it were
 * lifted into a top-level context.
 */

export type Theme = 'light' | 'dark' | 'system';

export interface Settings {
  theme: Theme;
  voiceAutoSend: boolean; // moved into Settings from VoiceStage's own inline checkbox
  reduceMotion: boolean; // stops the ThinkingOrb's continuous animation
  showStats: boolean; // show the "Model & Stats" block in the right rail
}

const KEYS: Record<keyof Settings, string> = {
  theme: 'raven.settings.theme',
  // Unchanged key name from before this settings panel existed, so an
  // already-saved preference on a real install carries over untouched.
  voiceAutoSend: 'raven.voice.autoSend',
  reduceMotion: 'raven.settings.reduceMotion',
  showStats: 'raven.settings.showStats',
};

const DEFAULTS: Settings = { theme: 'system', voiceAutoSend: false, reduceMotion: false, showStats: true };

function readBool(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v === 'true';
  } catch {
    return fallback; // storage disabled/unavailable -- fall back silently, per-viewer convenience only
  }
}

function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEYS.theme);
    return v === 'light' || v === 'dark' || v === 'system' ? v : DEFAULTS.theme;
  } catch {
    return DEFAULTS.theme;
  }
}

function writeValue(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // per-viewer convenience only -- fine if it can't be remembered
  }
}

let state: Settings = {
  theme: readTheme(),
  voiceAutoSend: readBool(KEYS.voiceAutoSend, DEFAULTS.voiceAutoSend),
  reduceMotion: readBool(KEYS.reduceMotion, DEFAULTS.reduceMotion),
  showStats: readBool(KEYS.showStats, DEFAULTS.showStats),
};

type Listener = () => void;
const listeners = new Set<Listener>();

function setSetting<K extends keyof Settings>(key: K, value: Settings[K]): void {
  state = { ...state, [key]: value };
  writeValue(KEYS[key], String(value));
  listeners.forEach((l) => l());
}

export function useSettings() {
  const [, bump] = useState(0);
  useEffect(() => {
    const listener = () => bump((n) => n + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return {
    ...state,
    setTheme: (t: Theme) => setSetting('theme', t),
    setVoiceAutoSend: (v: boolean) => setSetting('voiceAutoSend', v),
    setReduceMotion: (v: boolean) => setSetting('reduceMotion', v),
    setShowStats: (v: boolean) => setSetting('showStats', v),
  };
}

/** Applies `theme` to <html> as `data-theme` so index.css's theme blocks take
 * effect ('system' removes the attribute, so the OS-preference @media query
 * decides instead). Call this exactly ONCE near the app root (App.tsx) --
 * every useSettings() consumer would otherwise fight over the same attribute. */
export function useApplyTheme(theme: Theme): void {
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
  }, [theme]);
}

/** Resolves 'system' to the OS's actual current preference, for the rare
 * spot (e.g. a <canvas> orb) that needs a real light/dark color literal
 * rather than a CSS variable. */
export function useEffectiveTheme(): 'light' | 'dark' {
  const { theme } = useSettings();
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;
}
