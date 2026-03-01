export interface PersonaStyle {
  shape: 'circle' | 'ellipse' | 'pentagon' | 'hexagon' | 'triangle'
  primary: string
  secondary: string
  bgGlow: string
  idleSpeed: number
  speakIntensity: number
  quirk: 'none' | 'droop' | 'wobble' | 'tilt' | 'rotate'
}

export const PERSONA_STYLES: Record<string, PersonaStyle> = {
  kai:    { shape: 'circle',   primary: '#14b8a6', secondary: '#06b6d4', bgGlow: 'rgba(20,184,166,0.15)',  idleSpeed: 1.0, speakIntensity: 0.8, quirk: 'none' },
  marvin: { shape: 'ellipse',  primary: '#6b7280', secondary: '#475569', bgGlow: 'rgba(107,114,128,0.1)', idleSpeed: 0.5, speakIntensity: 0.3, quirk: 'droop' },
  robbie: { shape: 'pentagon', primary: '#ef4444', secondary: '#f97316', bgGlow: 'rgba(239,68,68,0.15)',   idleSpeed: 1.2, speakIntensity: 1.0, quirk: 'wobble' },
  hal:    { shape: 'circle',   primary: '#dc2626', secondary: '#000000', bgGlow: 'rgba(220,38,38,0.2)',    idleSpeed: 0.3, speakIntensity: 0.2, quirk: 'none' },
  jarvis: { shape: 'hexagon',  primary: '#d97706', secondary: '#2563eb', bgGlow: 'rgba(217,119,6,0.12)',   idleSpeed: 0.8, speakIntensity: 0.6, quirk: 'rotate' },
  glados: { shape: 'triangle', primary: '#ea580c', secondary: '#eab308', bgGlow: 'rgba(234,88,12,0.15)',   idleSpeed: 0.7, speakIntensity: 0.9, quirk: 'tilt' },
}

export const DEFAULT_STYLE: PersonaStyle = {
  shape: 'circle', primary: '#2D5F8A', secondary: '#60a5fa', bgGlow: 'rgba(45,95,138,0.15)',
  idleSpeed: 1.0, speakIntensity: 0.6, quirk: 'none',
}

export function getPersonaStyle(name: string): PersonaStyle {
  return PERSONA_STYLES[name.toLowerCase()] ?? DEFAULT_STYLE
}
