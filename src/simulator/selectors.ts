import type { Episode, EpisodeStep, Message, Principal } from '../types/episode'

export const getStep = (episode: Episode, index: number): EpisodeStep => episode.steps[index]
export const getPrincipal = (episode: Episode, id: string): Principal | undefined => episode.principals.find(p => p.id === id)
export const getMessage = (step: EpisodeStep, id: string): Message | undefined => step.messages.find(m => m.id === id)

export function receivedBy(step: EpisodeStep, principalId: string) {
  return step.messages.filter(m => m.to === principalId && ['delivered', 'historical'].includes(m.status))
}

export function sentBy(step: EpisodeStep, principalId: string) {
  return step.messages.filter(m => m.from === principalId)
}

export function localStatus(step: EpisodeStep, principalId: string, resourceId: string) {
  return step.localViews[principalId]?.resources[resourceId]
}
