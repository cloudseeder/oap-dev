export interface PersonaStyle {
  shape: 'circle' | 'ellipse' | 'pentagon' | 'hexagon' | 'triangle'
  primary: string
  secondary: string
  bgGlow: string
  idleSpeed: number
  speakIntensity: number
  quirk: 'none' | 'droop' | 'wobble' | 'tilt' | 'rotate'
}

// Primary colors are the original iMac G3 "flavors" (1998) — homage to Steve Jobs.
export const PERSONA_STYLES: Record<string, PersonaStyle> = {
  kai:    { shape: 'circle',   primary: '#00A1B0', secondary: '#4DD8E0', bgGlow: 'rgba(0,161,176,0.15)',   idleSpeed: 1.0, speakIntensity: 0.8, quirk: 'none' },     // Bondi Blue
  marvin: { shape: 'ellipse',  primary: '#6B3FA0', secondary: '#9B7AC7', bgGlow: 'rgba(107,63,160,0.12)',  idleSpeed: 0.5, speakIntensity: 0.5, quirk: 'droop' },    // Grape
  robbie: { shape: 'pentagon', primary: '#FF3B6B', secondary: '#FF7FA0', bgGlow: 'rgba(255,59,107,0.15)',  idleSpeed: 1.2, speakIntensity: 1.0, quirk: 'wobble' },   // Strawberry
  hal:    { shape: 'circle',   primary: '#4169E1', secondary: '#dc2626', bgGlow: 'rgba(65,105,225,0.18)',  idleSpeed: 0.3, speakIntensity: 0.5, quirk: 'none' },     // Blueberry (red eye inner)
  jarvis: { shape: 'hexagon',  primary: '#FF9500', secondary: '#FFB84D', bgGlow: 'rgba(255,149,0,0.12)',   idleSpeed: 0.8, speakIntensity: 0.6, quirk: 'rotate' },   // Tangerine
  glados: { shape: 'triangle', primary: '#83D932', secondary: '#B8F060', bgGlow: 'rgba(131,217,50,0.15)',  idleSpeed: 0.7, speakIntensity: 0.9, quirk: 'tilt' },     // Lime
}

export const DEFAULT_STYLE: PersonaStyle = {
  shape: 'circle', primary: '#2D5F8A', secondary: '#60a5fa', bgGlow: 'rgba(45,95,138,0.15)',
  idleSpeed: 1.0, speakIntensity: 0.6, quirk: 'none',
}

export function getPersonaStyle(name: string): PersonaStyle {
  return PERSONA_STYLES[name.toLowerCase()] ?? DEFAULT_STYLE
}
