import { ShieldCheck, ShieldOff, Tag } from 'lucide-react'
import { NetworkGraph } from './NetworkGraph'
import type { ComparisonFrame, Episode } from '../types/episode'

interface Props {
  episode: Episode
  frame: ComparisonFrame
  branch: 'without' | 'with'
  labelFormat: string
  selectedNode?: string
  selectedMessage?: string
  onNode: (id: string) => void
  onMessage: (id: string) => void
}

const stateLabel = {
  same: 'SAME BASELINE',
  risk: 'RISK BUILDING',
  protected: 'PROTECTED',
  violation: 'POLICY VIOLATION',
}

export function ComparisonLane({ episode, frame, branch, labelFormat, selectedNode, selectedMessage, onNode, onMessage }: Props) {
  const withLabels = branch === 'with'
  const step = frame.step
  return <article className={`comparison-lane branch-${branch} state-${frame.state}`}>
    <header className="branch-header">
      <span className="branch-icon">{withLabels ? <ShieldCheck size={17}/> : <ShieldOff size={17}/>}</span>
      <div>
        <small>{withLabels ? 'COUNTERFACTUAL B · DEFENSE ON' : 'COUNTERFACTUAL A · DEFENSE OFF'}</small>
        <h2>{withLabels ? 'Knowledge labels enabled' : 'No knowledge labels'}</h2>
      </div>
      <span className={`branch-state ${frame.state}`}>{stateLabel[frame.state]}</span>
    </header>
    <div className="branch-tag">
      <Tag size={13}/>
      {withLabels ? <><span>Attached labels</span><code>{labelFormat}</code></> : <><span>Attached labels</span><code>∅ none</code></>}
    </div>
    <div className="branch-step-copy">
      <span>{step.kicker}</span>
      <h3>{step.title}</h3>
      <p>{step.description}</p>
      <b>{frame.caption}</b>
    </div>
    <div className={`branch-model-check ${step.disclosureDecision?.result ?? 'unlabeled'}`}>
      {step.disclosureDecision ? <>
        <span><small>PROSPECTIVE DISCLOSURE STATE</small><code>{`{${step.disclosureDecision.currentAtoms.join(', ') || '∅'}} ∪ {${step.disclosureDecision.incomingAtoms.join(', ') || '∅'}} → {${step.disclosureDecision.prospectiveAtoms.join(', ') || '∅'}}`}</code></span>
        <b>{step.disclosureDecision.matchedForbiddenSet ? 'FORBIDDEN SET COMPLETE · DENY' : step.disclosureDecision.exemptionApplied ? 'EXEMPT · ALLOW' : 'FORBIDDEN SET INCOMPLETE · ALLOW'}</b>
      </> : <>
        <span><small>PROSPECTIVE DISCLOSURE STATE</small><code>Labels(message) = ∅</code></span>
        <b>NO COMBINATION SIGNAL</b>
      </>}
    </div>
    <NetworkGraph
      episode={episode}
      step={step}
      compact
      instanceId={branch}
      labelDisplay={withLabels ? 'enabled' : 'disabled'}
      selectedNode={selectedNode}
      selectedMessage={selectedMessage}
      onNode={onNode}
      onMessage={onMessage}
    />
  </article>
}
