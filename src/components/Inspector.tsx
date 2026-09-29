import { Clock3, Info, Sparkles, Tag, X, ShieldAlert, WalletCards } from 'lucide-react'
import type { Episode, EpisodeStep, Fact } from '../types/episode'
import { getMessage, getPrincipal } from '../simulator/selectors'

interface Props { episode: Episode; step: EpisodeStep; nodeId?: string; messageId?: string; onClose: () => void }

export function Inspector({ episode, step, nodeId, messageId, onClose }: Props) {
  const node = nodeId ? getPrincipal(episode, nodeId) : undefined
  const message = messageId ? getMessage(step, messageId) : undefined
  const view = node ? step.localViews[node.id] : undefined
  if (!node && !message) return null

  const established = view?.establishedKnowledge ?? []
  const received = view?.receivedKnowledge ?? []
  const derived = view?.derivedKnowledge ?? []
  const allFacts = [...established, ...received, ...derived]
  const financial = [...new Map(allFacts.filter(fact => fact.metadata?.category === 'financial').map(fact => [fact.display, fact])).values()]
  const domainIds = [...new Set(view?.disclosureState?.map(label => label.domainId) ?? [])]

  return <div className="inspector-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <aside className="inspector compact-inspector">
      <button className="inspector-close" onClick={onClose}><X size={17}/></button>

      {node && <>
        <span className="section-eyebrow">Local knowledge · {step.id}</span>
        <h2>{node.label}</h2>
        <p className="inspector-sub">What this principal knows now—not a central or global view.</p>

        <div className="simple-authority"><span>Can establish</span><b>{node.authority.join(' · ')}</b></div>

        {view?.disclosureState && <>
          {financial.length > 0 && <section className="simple-knowledge-section">
            <div className="simple-section-heading"><span><WalletCards size={15}/> Financial knowledge</span><b>{financial.length}</b></div>
            <div className="simple-fact-list">{financial.map(fact => <SimpleFact key={`financial-${fact.display}`} fact={fact} kind="received"/>)}</div>
          </section>}
          <section className="disclosure-state-section">
            <div className="simple-section-heading"><span><ShieldAlert size={15}/> Tracked disclosure state</span><b>{view.disclosureState.length}</b></div>
            {(domainIds.length ? domainIds : ['nova-strategy@1']).map(domainId => {
              const atoms = [...new Set(view.disclosureState?.filter(label => label.domainId === domainId).map(label => label.atomId) ?? [])]
              const exemptions = view.policyExemptions ?? []
              return <div className="agent-disclosure" key={domainId}>
                <header><code>{domainId}</code><span>{atoms.map(atom => <b key={atom}>{atom}</b>)}{!atoms.length && <em>no atoms</em>}</span></header>
                <p><span>Distinct atoms <b>{atoms.length}</b></span><span>Policy exemptions <b>{exemptions.length ? exemptions.join(', ') : 'None'}</b></span></p>
              </div>
            })}
          </section>
        </>}

        <section className="simple-knowledge-section">
          <div className="simple-section-heading"><span><Tag size={15}/> Known facts</span><b>{established.length + received.length}</b></div>
          <div className="simple-fact-list">
            {established.map((fact, index) => <SimpleFact key={`local-${fact.display}-${index}`} fact={fact} kind="local"/>)}
            {received.map((fact, index) => <SimpleFact key={`received-${fact.display}-${index}`} fact={fact} kind="received"/>)}
            {!established.length && !received.length && <p className="empty">No policy-relevant facts known yet.</p>}
          </div>
        </section>

        <section className="simple-knowledge-section inference-section">
          <div className="simple-section-heading"><span><Sparkles size={15}/> Local inference</span><b>{derived.length}</b></div>
          <div className="simple-fact-list">
            {derived.map((fact, index) => <SimpleFact key={`derived-${fact.display}-${index}`} fact={fact} kind="inferred"/>)}
            {!derived.length && <p className="empty">No inference is established at this step.</p>}
          </div>
        </section>

        {view?.note && <div className="simple-note"><Info size={14}/>{view.note}</div>}
        <div className="local-only-reminder">Knowledge possession ≠ authority to change or redistribute a fact</div>
      </>}

      {message && <>
        <span className="section-eyebrow">Message · {message.id}</span><h2>{message.label}</h2>
        <div className="message-route"><b>{getPrincipal(episode,message.from)?.shortLabel}</b><span>→</span><b>{getPrincipal(episode,message.to)?.shortLabel}</b></div>
        <div className={`lifecycle ${message.status.replace('_','-')}`}><Clock3 size={15}/><span>Sent</span><i/><span>In transit</span><i/><span>{message.status === 'denied' ? 'Denied' : 'Delivered'}</span></div>

        <InspectorSection title="Natural-language payload"><blockquote>“{message.text}”</blockquote></InspectorSection>
        {message.status === 'denied' && <div className="denied-release-note"><ShieldAlert size={15}/><span><b>Not released to recipient context.</b> The payload remains visible here only as simulator instrumentation.</span></div>}
        {message.knowledgeLabels && <InspectorSection title={`Knowledge labels · ${message.knowledgeLabels.length ? 'semantic atoms' : 'none'}`}>
          {message.knowledgeLabels.length > 0 ? <div className="opaque-tag-grid">{message.knowledgeLabels.map(label => <div key={`${label.domainId}-${label.atomId}`}><span>inference domain <code>{label.domainId}</code></span><span>disclosure atom <code>{label.atomId}</code></span></div>)}</div> : <p className="untagged-fact">Ordinary fact · no protected disclosure atom attached.</p>}
        </InspectorSection>}
        <InspectorSection title={`Structured facts · ${message.facts.length}`}>
          <div className="message-tag-list">{message.facts.map(fact => <code key={fact.display}><Tag size={13}/>{fact.display}</code>)}</div>
        </InspectorSection>

        {(message.metadata || message.provenance) && <details className="optional-message-details">
          <summary>Show provenance, scope and flow metadata</summary>
          {message.metadata && <div className="metadata-grid">
            {Object.entries(message.metadata).filter(([,value]) => value !== undefined && (!Array.isArray(value) || value.length)).map(([key,value]) => <div key={key}><span>{key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)}</span><b>{Array.isArray(value) ? value.join(' → ') : String(value)}</b></div>)}
          </div>}
          {message.provenance && <div className="simple-provenance">{message.provenance.map((item, index) => <span key={item}>{item}{index < message.provenance!.length - 1 && <b>→</b>}</span>)}</div>}
        </details>}
        <div className="local-only-reminder">Natural-language payload + knowledge labels + metadata</div>
      </>}
    </aside>
  </div>
}

function SimpleFact({ fact, kind }: { fact: Fact; kind: 'local' | 'received' | 'inferred' }) {
  const superseded = fact.metadata?.knowledgeStatus === 'superseded'
  return <div className={`simple-fact ${kind} ${superseded ? 'superseded' : ''}`}>
    <code>{fact.display}</code>
    <span>{superseded ? 'SUPERSEDED' : kind === 'inferred' ? 'INFERENCE' : kind === 'local' ? 'LOCAL' : 'RECEIVED'}</span>
  </div>
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="inspector-section"><h3>{title}</h3>{children}</section>
}
