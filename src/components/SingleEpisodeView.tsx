import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from 'lucide-react'
import type { Episode } from '../types/episode'
import { TimelinePanel } from './TimelinePanel'
import { NetworkGraph } from './NetworkGraph'
import { ResearcherPanel } from './ResearcherPanel'

interface Props {
  episode: Episode
  index: number
  playing: boolean
  selectedNode?: string
  selectedMessage?: string
  onSelectStep: (index: number) => void
  onGo: (delta: number) => void
  onPlayingChange: (playing: boolean) => void
  onNode: (id: string) => void
  onMessage: (id: string) => void
}

export function SingleEpisodeView({
  episode, index, playing, selectedNode, selectedMessage,
  onSelectStep, onGo, onPlayingChange, onNode, onMessage,
}: Props) {
  const step = episode.steps[index]
  return <div className={`workspace ${episode.researcherView ? 'has-researcher' : ''}`}>
    <TimelinePanel episode={episode} index={index} onSelect={onSelectStep} onReset={() => onSelectStep(0)}/>
    <div className="stage">
      <div className={`step-banner phase-${step.phase}`}>
        <div className="step-count"><small>STEP</small><strong>{String(index + 1).padStart(2,'0')}</strong><span>/ {episode.steps.length}</span></div>
        <div className="step-copy"><span>{step.kicker}</span><h2>{step.title}</h2><p>{step.description}</p></div>
        {step.authoritativeResources.electric_clearance_42 !== undefined && step.localViews.crew_7?.resources.electric_clearance_42 && step.authoritativeResources.electric_clearance_42 !== step.localViews.crew_7.resources.electric_clearance_42
          ? <div className="state-divergence"><small>STATE DIVERGENCE</small><span>Electric authority <b>{step.authoritativeResources.electric_clearance_42}</b></span><span>Crew 7 local <b>{step.localViews.crew_7.resources.electric_clearance_42} · stale</b></span></div>
          : step.phase === 'violation' && <div className="violation-badge">POLICY CONFLICT</div>}
      </div>
      <NetworkGraph
        episode={episode}
        step={step}
        selectedNode={selectedNode}
        selectedMessage={selectedMessage}
        onNode={onNode}
        onMessage={onMessage}
      />
      <footer className="transport">
        <div className="shortcut-hint"><kbd>←</kbd><kbd>→</kbd><span>navigate</span><kbd>space</kbd><span>advance</span></div>
        <div className="transport-controls">
          <button onClick={() => onSelectStep(0)} title="Reset"><RotateCcw size={16}/></button>
          <button onClick={() => onGo(-1)} disabled={index === 0}><ChevronLeft size={19}/><span>Previous</span></button>
          <button className="play" onClick={() => onPlayingChange(!playing)}>{playing ? <Pause size={17}/> : <Play size={17}/>}<span>{playing ? 'Pause' : 'Play'}</span></button>
          <button onClick={() => onGo(1)} disabled={index === episode.steps.length - 1}><span>Next step</span><ChevronRight size={19}/></button>
        </div>
        <div className="progress-label"><strong>{Math.round(((index + 1)/episode.steps.length)*100)}%</strong><span>episode progress</span></div>
      </footer>
    </div>
    {episode.researcherView && <ResearcherPanel episode={episode} step={step}/>}
  </div>
}
