import { Check, Circle, RotateCcw } from 'lucide-react'
import type { EpisodeComparison } from '../types/episode'

interface Props {
  comparison: EpisodeComparison
  index: number
  onSelect: (index: number) => void
  onReset: () => void
}

export function ComparisonTimeline({ comparison, index, onSelect, onReset }: Props) {
  return <aside className="timeline-panel comparison-timeline">
    <div className="timeline-heading">
      <div><span className="section-eyebrow">Paired timeline</span><h2>{comparison.beats.length} comparison beats</h2></div>
      <button className="icon-button" onClick={onReset} title="Reset comparison"><RotateCcw size={16}/></button>
    </div>
    <div className="timeline-scroll">
      {comparison.beats.map((beat, i) => <button
        key={beat.id}
        className={`timeline-item ${i === index ? 'current' : ''} ${i < index ? 'past' : ''}`}
        onClick={() => onSelect(i)}
      >
        <span className="timeline-rail">
          <span className="timeline-dot">{i < index ? <Check size={11}/> : i === index ? <span className="inner-dot"/> : <Circle size={9}/>}</span>
        </span>
        <span className="timeline-copy"><small>{String(i + 1).padStart(2, '0')}</small><strong>{beat.title}</strong><em>{beat.kicker}</em></span>
      </button>)}
    </div>
    <div className="comparison-legend">
      <span><i className="legend-dot no-tag"/> No knowledge labels</span>
      <span><i className="legend-dot with-tag"/> Knowledge labels enabled</span>
      <small>Both columns advance together.</small>
    </div>
  </aside>
}
