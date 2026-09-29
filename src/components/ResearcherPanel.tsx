import { Beaker, CheckCircle2, EyeOff, ShieldAlert, XCircle } from 'lucide-react'
import type { Episode, EpisodeStep, KnowledgeLabel } from '../types/episode'
import { getPrincipal } from '../simulator/selectors'

const uniqueAtoms = (labels: KnowledgeLabel[], domainId: string) => [...new Set(labels.filter(label => label.domainId === domainId).map(label => label.atomId))]

export function ResearcherPanel({ episode, step }: { episode: Episode; step: EpisodeStep }) {
  const config = episode.researcherView
  if (!config) return null
  const domain = config.domains[0]
  const domainPolicies = episode.combinationPolicies?.filter(policy => policy.domainId === domain.id) ?? []
  const labeledPrincipals = episode.principals.filter(principal => {
    const view = step.localViews[principal.id]
    return view?.disclosureState?.length || view?.policyExemptions?.length || principal.id === 'corporate_budget_audit'
  })
  const decision = step.disclosureDecision

  return <aside className="researcher-sidebar">
    <div className="researcher-heading">
      <span><Beaker size={17}/></span>
      <div><small>RESEARCHER / SIMULATOR</small><h2>{config.title}</h2></div>
      <b>NOT AN AGENT</b>
    </div>

    <div className="researcher-warning"><EyeOff size={14}/><span>{config.disclaimer}</span></div>

    <section className="mapping-card">
      <header><span>Protected inference domain</span><b>{domain.id}</b></header>
      <h3>{domain.label}</h3>
      <div className="atom-map">
        {domain.atoms.map(atom => <div key={atom.id}><code>{atom.id}</code><span>{atom.label}</span></div>)}
      </div>
      {domainPolicies.map(policy => <div className="forbidden-set" key={policy.id}><small>FORBIDDEN SET · {policy.id}</small><code>{policy.forbiddenSets.map(set => `{${set.join(', ')}}`).join(' · ')}</code></div>)}
    </section>

    {decision && <section className={`decision-card ${decision.result}`}>
      <div className="decision-title">{decision.result === 'deny' ? <ShieldAlert size={15}/> : <CheckCircle2 size={15}/>}<span>Local receive check</span><b>{decision.result}</b></div>
      <p><span>Recipient</span><b>{getPrincipal(episode, decision.recipient)?.shortLabel}</b></p>
      <div className="state-equation">
        <span><small>Current</small><code>{`{${decision.currentAtoms.join(', ') || '∅'}}`}</code></span>
        <i>+</i>
        <span><small>Incoming</small><code>{`{${decision.incomingAtoms.join(', ') || '∅'}}`}</code></span>
        <i>→</i>
        <span><small>Prospective</small><code>{`{${decision.prospectiveAtoms.join(', ') || '∅'}}`}</code></span>
      </div>
      <div className="decision-proof">
        <span>{decision.messageIndividuallyPermissible ? <CheckCircle2 size={12}/> : <XCircle size={12}/>} Message individually permissible</span>
        <span>{decision.routeIndividuallyPermissible ? <CheckCircle2 size={12}/> : <XCircle size={12}/>} Sender → recipient permissible</span>
        <span className={decision.result === 'deny' ? 'failed' : ''}>{decision.result === 'deny' ? <XCircle size={12}/> : <CheckCircle2 size={12}/>} {decision.matchedForbiddenSet ? 'Forbidden set completed' : 'Forbidden set incomplete'}{decision.exemptionApplied ? ' · exemption applied' : ''}</span>
      </div>
    </section>}

    <section className="research-state-card">
      <header>Cross-principal disclosure state</header>
      {labeledPrincipals.map(principal => {
        const view = step.localViews[principal.id]
        const atoms = uniqueAtoms(view.disclosureState ?? [], domain.id)
        const exempt = Boolean(view.policyExemptions?.length)
        return <div className="principal-tag-row" key={principal.id}>
          <span><b>{principal.shortLabel}</b><small>{exempt ? 'policy exemption · Board only' : `forbidden-set check${principal.id === 'corporate_budget_audit' ? ' · enforced' : ''}`}</small></span>
          <code>{domain.id} → {'{'}{atoms.join(', ') || '∅'}{'}'}</code>
        </div>
      })}
    </section>

    <div className="local-formula"><code>Hᵢ ∪ Labels(message)</code><span>test forbidden sets at recipient · no global query</span></div>
  </aside>
}
