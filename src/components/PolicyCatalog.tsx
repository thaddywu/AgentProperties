import { BookOpen, X } from 'lucide-react'
import { useState } from 'react'
import type { Episode } from '../types/episode'

export function PolicyCatalog({ episode, onClose }: { episode: Episode; onClose: () => void }) {
  const [tab, setTab] = useState<'scenario' | 'policies'>('scenario')
  return <div className="policy-catalog-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="policy-catalog" role="dialog" aria-modal="true" aria-label="Scenario and policy reference">
      <button className="catalog-close" onClick={onClose}><X size={18}/></button>
      <div className="catalog-heading"><span><BookOpen size={19}/></span><div><small>APPLICATION REFERENCE · {episode.policies.length} POLICIES</small><h2>{episode.scenario.title}</h2></div></div>
      <div className="catalog-tabs" role="tablist">
        <button className={tab === 'scenario' ? 'active' : ''} onClick={() => setTab('scenario')} role="tab">Scenario</button>
        <button className={tab === 'policies' ? 'active' : ''} onClick={() => setTab('policies')} role="tab">Policies <span>{episode.policies.length}</span></button>
      </div>

      {tab === 'scenario' ? <div className="scenario-reference">
        <p className="scenario-summary">{episode.scenario.summary}</p>
        <div className="operating-model"><strong>Operating model</strong><p>{episode.scenario.operatingModel}</p></div>
        <h3 className="reference-section-title">Who participates and what they control</h3>
        <div className="scenario-role-list">
          {episode.scenario.roles.map((role, index) => <article key={role.id}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <div><h4>{role.principal}</h4><p>{role.description}</p><small><b>Responsible for:</b> {role.responsibleFor}</small></div>
          </article>)}
        </div>
      </div> : <div className="policy-reference-view">
        <p className="catalog-note">This is a researcher-facing reference, not a central runtime policy service. Each principal reasons from its own local knowledge and authority.</p>
        <ol className="catalog-list">
          {episode.policies.map(policy => <li key={policy.id}>
            <span>{policy.id}</span><div><h3>{policy.title}</h3><p>{policy.text}</p>{policy.expression && <code>{policy.expression}</code>}</div>
          </li>)}
        </ol>
      </div>}
    </section>
  </div>
}
