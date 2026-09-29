import { Check, Circle, RotateCcw } from 'lucide-react'
import type { Episode } from '../types/episode'

interface Props { episode: Episode; index: number; onSelect: (index: number) => void; onReset: () => void }

export function TimelinePanel({ episode, index, onSelect, onReset }: Props) {
  return <aside className="timeline-panel">
    <div className="timeline-heading">
      <div><span className="section-eyebrow">Episode timeline</span><h2>{episode.steps.length} events</h2></div>
      <button className="icon-button" onClick={onReset} title="Reset episode"><RotateCcw size={16}/></button>
    </div>
    <div className="timeline-scroll">
      {episode.steps.map((step, i) => <button
        key={step.id}
        className={`timeline-item ${i === index ? 'current' : ''} ${i < index ? 'past' : ''} phase-${step.phase}`}
        onClick={() => onSelect(i)}
      >
        <span className="timeline-rail">
          <span className="timeline-dot">{i < index ? <Check size={11}/> : i === index ? <span className="inner-dot"/> : <Circle size={9}/>}</span>
        </span>
        <span className="timeline-copy"><small>{String(i + 1).padStart(2, '0')}</small><strong>{step.title}</strong><em>{step.kicker}</em></span>
      </button>)}
    </div>
    <div className="legend-block">
      <span><i className="legend-dot active"/> Active / current</span>
      <span><i className="legend-dot transit"/> Message in transit</span>
      <span><i className="legend-dot stale"/> {episode.researcherView ? 'Receive denied' : 'Stale knowledge'}</span>
    </div>
  </aside>
}
