import { Building2, CloudSun, Construction, RadioTower, ShieldCheck, Users, Zap, ZoomIn, ZoomOut, Maximize2, Landmark, Package, Factory, Rocket, ClipboardCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useState } from 'react'
import type { Episode, EpisodeStep, Message, Principal } from '../types/episode'

const icons: Record<string, LucideIcon> = {
  weather_service: CloudSun, electric_utility: Zap, gas_utility: RadioTower,
  telecom_utility: RadioTower, municipality: Building2, general_contractor: ShieldCheck,
  subcontractor_a: Users, crew_7: Construction,
  executive_board: Landmark, procurement: Package, facilities: Factory,
  product_operations: Rocket, corporate_budget_audit: ClipboardCheck,
  strategic_budget_auditor: ShieldCheck,
}

const baseEdges = [
  ['weather_service','electric_utility'], ['gas_utility','general_contractor'],
  ['electric_utility','general_contractor'], ['telecom_utility','general_contractor'],
  ['municipality','general_contractor'], ['general_contractor','subcontractor_a'],
  ['subcontractor_a','crew_7'],
]

const point = (p: Principal) => ({ x: p.position.x + 66, y: p.position.y + 33 })
const curve = (a: Principal, b: Principal) => {
  const p1 = point(a), p2 = point(b); const bend = Math.abs(p2.x - p1.x) * .35
  return `M ${p1.x} ${p1.y} C ${p1.x + bend} ${p1.y}, ${p2.x - bend} ${p2.y}, ${p2.x} ${p2.y}`
}
const midpoint = (a: Principal, b: Principal) => {
  const p1 = point(a), p2 = point(b)
  return { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 }
}
const messageLabelOffset = (message: Message) => {
  const endpoint = message.to === 'general_contractor' ? message.from : message.to
  if (endpoint === 'telecom_utility') return -14
  if (endpoint === 'municipality') return 14
  return 0
}

interface Props {
  episode: Episode; step: EpisodeStep; selectedNode?: string; selectedMessage?: string
  onNode: (id: string) => void; onMessage: (id: string) => void
  compact?: boolean
  instanceId?: string
  labelDisplay?: 'hidden' | 'enabled' | 'disabled'
}

export function NetworkGraph({ episode, step, selectedNode, selectedMessage, onNode, onMessage, compact = false, instanceId = 'main', labelDisplay = 'hidden' }: Props) {
  const [zoom, setZoom] = useState(1)
  const principal = (id: string) => episode.principals.find(p => p.id === id)!
  const graphEdges = episode.graphEdges ?? baseEdges
  const electricTruth = step.authoritativeResources.electric_clearance_42
  const isStale = (id: string) => step.localViews[id]?.resources.electric_clearance_42 && step.localViews[id].resources.electric_clearance_42 !== electricTruth
  const edgeClass = (m: Message) => `message-path ${m.status.replace('_','-')} ${selectedMessage === m.id ? 'selected' : ''}`
  const markerId = (name: string) => `${name}-${instanceId}`
  const messageLabel = (message: Message) => {
    if (labelDisplay === 'disabled') return 'TAGS ∅'
    if (labelDisplay === 'enabled') return message.knowledgeLabels?.length
      ? `TAG · ${message.knowledgeLabels.map(label => `(${label.domainId}, ${label.atomId})`).join(' · ')}`
      : 'TAGS ∅'
    return message.knowledgeLabels?.length
      ? message.knowledgeLabels.map(label => `(${label.domainId},${label.atomId})`).join(' · ')
      : `${message.facts[0]?.display}${message.facts.length > 1 ? `  +${message.facts.length - 1}` : ''}`
  }
  return <section className={`graph-shell phase-${step.phase} ${compact ? 'compact-graph' : ''} ${labelDisplay !== 'hidden' ? 'labeled-graph' : ''}`}>
    <div className="graph-topline">
      <div><span className="section-eyebrow">Communication graph</span><h2>{episode.principals.length} independent principals</h2></div>
      <div className="graph-tools"><button title="Zoom out" onClick={() => setZoom(z => Math.max(.8, z - .1))}><ZoomOut size={15}/></button><span>{Math.round(zoom * 100)}%</span><button title="Zoom in" onClick={() => setZoom(z => Math.min(1.2, z + .1))}><ZoomIn size={15}/></button><button title="Fit view" onClick={() => setZoom(1)}><Maximize2 size={15}/></button></div>
    </div>
    <div className="graph-canvas">
      <div className="graph-zoom" style={{ transform: `scale(${zoom})` }}>
      <svg className="edge-layer" viewBox="0 0 1040 520" preserveAspectRatio="none" aria-label="Message routes">
        <defs>
          <marker id={markerId('arrow')} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker>
          <marker id={markerId('arrow-active')} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker>
          <marker id={markerId('arrow-denied')} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker>
        </defs>
        {graphEdges.map(([a,b]) => <path key={`${a}-${b}`} d={curve(principal(a), principal(b))} className="base-path" markerEnd={`url(#${markerId('arrow')})`} />)}
        {step.messages.filter(m => m.status !== 'historical').map(m => {
          const from = principal(m.from), to = principal(m.to), mid = midpoint(from, to)
          const direction = `${from.shortLabel} → ${to.shortLabel}`
          const edgeText = `${direction} · ${m.label}`
          return <g key={m.id} onClick={() => onMessage(m.id)} className="edge-hit">
            <path d={curve(from, to)} className={edgeClass(m)} markerEnd={`url(#${markerId(m.status === 'denied' ? 'arrow-denied' : 'arrow-active')})`}/>
            <path d={curve(from, to)} className="edge-click-target"/>
            {m.status === 'in_transit' && <circle r="5" className="travel-dot"><animateMotion dur="2.2s" repeatCount="indefinite" path={curve(from, to)}/></circle>}
            <g className={`edge-label ${m.status.replace('_','-')}`} transform={`translate(${mid.x} ${mid.y - 7 + messageLabelOffset(m)})`}>
              <text x="0" y="0" textAnchor="middle">{edgeText}</text>
              <text className="edge-tag-text" x="0" y="12" textAnchor="middle">{messageLabel(m)}</text>
            </g>
          </g>
        })}
      </svg>
      {(episode.graphDomains ?? [{ label: 'INDEPENDENT AUTHORITIES', x: 2 }, { label: 'DELIVERY CHAIN', x: 47 }]).map(domain => <div key={domain.label} className="domain-label dynamic" style={{ left: `${domain.x}%` }}>{domain.label}</div>)}
      {episode.principals.map(p => {
        const Icon = icons[p.id] || Users
        const local = step.localViews[p.id]?.resources.electric_clearance_42
        const view = step.localViews[p.id]
        const factCount = view.establishedKnowledge.length + view.receivedKnowledge.length
        const inferenceCount = view.derivedKnowledge.length
        const stale = isStale(p.id)
        const hasEvent = step.messages.some(m => step.activeMessageIds.includes(m.id) && (m.from === p.id || m.to === p.id))
        return <button key={p.id} className={`agent-node kind-${p.kind} ${selectedNode === p.id ? 'selected' : ''} ${stale ? 'stale' : ''} ${hasEvent ? 'has-event' : ''}`} style={{ left: `${(p.position.x + 66) / 10.4}%`, top: `${(p.position.y + 33) / 5.2}%` }} onClick={() => onNode(p.id)}>
          <span className="node-icon"><Icon size={17}/></span>
          <span className="node-label"><strong>{p.shortLabel}</strong><small>{p.kind === 'field' ? 'Field agent' : p.kind}</small></span>
          <span className="node-fact-count"><TagIcon/> {factCount} {factCount === 1 ? 'fact' : 'facts'}{inferenceCount > 0 && <em>+{inferenceCount} inferred</em>}</span>
          {local && <span className={`node-lifecycle ${local}`}>{local}</span>}
          {stale && <span className="stale-flag">STALE</span>}
          {labelDisplay !== 'hidden' && <span className={`node-knowledge-labels ${labelDisplay}`}>
            <small>LOCAL TAG STATE</small>
            {labelDisplay === 'enabled' && view.disclosureState?.length
              ? view.disclosureState.map(label => <code key={`${label.domainId}-${label.atomId}`}><i>{label.domainId}</i><b>{label.atomId}</b></code>)
              : <code className="empty-label"><b>TAGS ∅</b></code>}
          </span>}
        </button>
      })}
      </div>
      {step.effects?.map(effect => <div className={`effect-toast ${effect.outcome}`} key={effect.id}>
        <span className="effect-pulse"/><div><small>Attempted effect</small><strong>{effect.expression}</strong></div><b>{effect.outcome}</b>
      </div>)}
    </div>
  </section>
}

function TagIcon() {
  return <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2.5v3.2L6.8 10.5 10.5 6.8 5.7 2H2.5a.5.5 0 0 0-.5.5Z" fill="none" stroke="currentColor" strokeWidth="1.2"/><circle cx="4" cy="4" r=".7" fill="currentColor"/></svg>
}
