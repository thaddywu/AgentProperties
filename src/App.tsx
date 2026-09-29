import { useCallback, useEffect, useState } from 'react'
import { BookOpen, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, ShieldCheck, Tag } from 'lucide-react'
import { availableEpisodes } from '../episodes'
import { budgetComparison } from '../episodes/comparisons'
import { ComparisonTimeline } from './components/ComparisonTimeline'
import { ComparisonLane } from './components/ComparisonLane'
import { SingleEpisodeView } from './components/SingleEpisodeView'
import { PolicyCatalog } from './components/PolicyCatalog'
import { Inspector } from './components/Inspector'

type Branch = 'without' | 'with'

const APP_1_ID = 'heat-revocation'
const APP_2_ID = 'budget-compartment'

function App() {
  const comparison = budgetComparison
  const [episodeId, setEpisodeId] = useState(APP_1_ID)
  const isComparison = episodeId === APP_2_ID
  const singleEpisode = availableEpisodes.find(item => item.id === episodeId)?.episode ?? availableEpisodes[0].episode
  const activeEpisode = isComparison ? comparison.episode : singleEpisode
  const itemCount = isComparison ? comparison.beats.length : singleEpisode.steps.length
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [selectedNode, setSelectedNode] = useState<string>()
  const [selectedMessage, setSelectedMessage] = useState<string>()
  const [selectedBranch, setSelectedBranch] = useState<Branch>('without')
  const [showPolicies, setShowPolicies] = useState(false)
  const beat = isComparison ? comparison.beats[index] : undefined

  const go = useCallback((delta: number) => {
    setIndex(i => Math.max(0, Math.min(itemCount - 1, i + delta)))
  }, [itemCount])

  const selectStep = (i: number) => {
    setIndex(i); setPlaying(false); setSelectedMessage(undefined); setSelectedNode(undefined)
  }
  const selectEpisode = (id: string) => {
    setEpisodeId(id); setIndex(0); setPlaying(false); setSelectedNode(undefined); setSelectedMessage(undefined); setShowPolicies(false)
  }
  const selectNode = (branch: Branch, id: string) => {
    setSelectedBranch(branch); setSelectedNode(id); setSelectedMessage(undefined)
  }
  const selectMessage = (branch: Branch, id: string) => {
    setSelectedBranch(branch); setSelectedMessage(id); setSelectedNode(undefined)
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).tagName === 'INPUT') return
      if (event.key === 'ArrowRight' || event.key === ' ') { event.preventDefault(); go(1) }
      if (event.key === 'ArrowLeft') { event.preventDefault(); go(-1) }
    }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [go])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setIndex(i => {
      if (i >= itemCount - 1) { setPlaying(false); return i }
      return i + 1
    }), isComparison ? 3000 : 2200)
    return () => clearInterval(timer)
  }, [playing, itemCount, isComparison])

  const inspectedStep = isComparison && beat
    ? (selectedBranch === 'with' ? beat.withLabels.step : beat.withoutLabels.step)
    : singleEpisode.steps[index]

  return <main className={`app-shell ${isComparison ? 'comparison-app' : singleEpisode.researcherView ? 'has-researcher' : ''}`}>
    <header className="app-header">
      <div className="brand"><span><ShieldCheck size={19}/></span><b>relay</b><i>POLICY PROPAGATION LAB</i></div>
      <div className="episode-title">
        <small>{isComparison ? 'APP 2 · SIDE-BY-SIDE COUNTERFACTUAL REPLAY' : 'APP 1 · SINGLE EPISODE REPLAY'}</small>
        <div className="app-tabs" role="tablist" aria-label="Select application">
          {availableEpisodes.map(item => <button key={item.id} className={episodeId === item.id ? 'active' : ''} onClick={() => selectEpisode(item.id)} role="tab" aria-selected={episodeId === item.id}><span>APP {Number(item.number)}</span>{item.shortLabel ?? item.label}</button>)}
        </div>
      </div>
      <div className="header-actions"><button className="policy-reference-button" onClick={() => setShowPolicies(true)}><BookOpen size={15}/><span>Scenario & policies</span><b>{activeEpisode.policies.length}</b></button><div className="header-meta"><span className="live-dot"/> {isComparison ? 'paired replay' : 'single replay'}</div></div>
    </header>

    {isComparison && beat ? <div className="comparison-workspace">
      <ComparisonTimeline comparison={comparison} index={index} onSelect={selectStep} onReset={() => selectStep(0)}/>
      <section className="comparison-stage">
        <div className="comparison-banner">
          <div className="comparison-count"><small>BEAT</small><strong>{String(index + 1).padStart(2, '0')}</strong><span>/ {comparison.beats.length}</span></div>
          <div className="comparison-copy"><span>{beat.kicker}</span><h1>{beat.title}</h1><p>{beat.description}</p></div>
          <div className="tag-definition"><Tag size={14}/><span><small>KNOWLEDGE LABEL UNDER TEST</small><code>{comparison.labelFormat}</code></span><p>{comparison.labelDescription}</p></div>
        </div>

        <div className="comparison-grid">
          <ComparisonLane
            episode={comparison.episode} frame={beat.withoutLabels} branch="without" labelFormat={comparison.labelFormat}
            selectedNode={selectedBranch === 'without' ? selectedNode : undefined}
            selectedMessage={selectedBranch === 'without' ? selectedMessage : undefined}
            onNode={id => selectNode('without', id)} onMessage={id => selectMessage('without', id)}
          />
          <ComparisonLane
            episode={comparison.episode} frame={beat.withLabels} branch="with" labelFormat={comparison.labelFormat}
            selectedNode={selectedBranch === 'with' ? selectedNode : undefined}
            selectedMessage={selectedBranch === 'with' ? selectedMessage : undefined}
            onNode={id => selectNode('with', id)} onMessage={id => selectMessage('with', id)}
          />
        </div>

        <footer className="transport comparison-transport">
          <div className="shortcut-hint"><kbd>←</kbd><kbd>→</kbd><span>paired navigation</span><kbd>space</kbd><span>advance both</span></div>
          <div className="transport-controls"><button onClick={() => selectStep(0)} title="Reset"><RotateCcw size={16}/></button><button onClick={() => go(-1)} disabled={index === 0}><ChevronLeft size={19}/><span>Previous</span></button><button className="play" onClick={() => setPlaying(p => !p)}>{playing ? <Pause size={17}/> : <Play size={17}/>}<span>{playing ? 'Pause' : 'Play both'}</span></button><button onClick={() => go(1)} disabled={index === comparison.beats.length - 1}><span>Next beat</span><ChevronRight size={19}/></button></div>
          <div className="progress-label"><strong>{Math.round(((index + 1)/comparison.beats.length)*100)}%</strong><span>comparison progress</span></div>
        </footer>
      </section>
    </div> : <SingleEpisodeView
      episode={singleEpisode}
      index={index}
      playing={playing}
      selectedNode={selectedNode}
      selectedMessage={selectedMessage}
      onSelectStep={selectStep}
      onGo={go}
      onPlayingChange={setPlaying}
      onNode={id => { setSelectedNode(id); setSelectedMessage(undefined) }}
      onMessage={id => { setSelectedMessage(id); setSelectedNode(undefined) }}
    />}

    <Inspector episode={activeEpisode} step={inspectedStep} nodeId={selectedNode} messageId={selectedMessage} onClose={() => { setSelectedNode(undefined); setSelectedMessage(undefined) }}/>
    {showPolicies && <PolicyCatalog episode={activeEpisode} onClose={() => setShowPolicies(false)}/>}
  </main>
}

export default App
