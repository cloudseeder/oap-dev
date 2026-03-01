import { createContext, useContext, type MutableRefObject } from 'react'

export interface AvatarState {
  recording: boolean
  streaming: boolean
  persona: string
  audioLevelRef?: MutableRefObject<number>
}

const DEFAULT: AvatarState = { recording: false, streaming: false, persona: '' }

export const AvatarStateContext = createContext<{
  state: AvatarState
  update: (patch: Partial<AvatarState>) => void
}>({ state: DEFAULT, update: () => {} })

export function useAvatarState() {
  return useContext(AvatarStateContext)
}
