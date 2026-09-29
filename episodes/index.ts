import heatRevocationEpisode from './heat-revocation/episode'
import budgetCompartmentEpisode from './budget-compartment/episode'
import type { Episode } from '../src/types/episode'

export interface EpisodeCatalogItem {
  id: string
  number: string
  label: string
  shortLabel?: string
  episode?: Episode
}

// Add a future episode import and its `episode` field here. The simulator UI does
// not need any changes; selection, reset, playback, graph and inspectors are generic.
export const episodeCatalog: EpisodeCatalogItem[] = [
  { id: heatRevocationEpisode.id, number: '01', label: heatRevocationEpisode.title, shortLabel: 'Underground', episode: heatRevocationEpisode },
  { id: budgetCompartmentEpisode.id, number: '02', label: budgetCompartmentEpisode.title, shortLabel: 'Budget Audit', episode: budgetCompartmentEpisode },
  { id: 'episode-slot-03', number: '03', label: 'Episode slot ready' },
]

export const availableEpisodes = episodeCatalog.filter((item): item is EpisodeCatalogItem & { episode: Episode } => Boolean(item.episode))
