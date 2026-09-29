import type { Episode, EpisodeStep, Fact, FactMetadata, LocalView, Message, PolicyEvaluation, ResourceStatus } from '../../src/types/episode'

const fact = (predicate: string, ...args: string[]): Fact => ({
  predicate,
  args,
  display: `${predicate}(${args.join(', ')})`,
})
const tagged = (predicate: string, args: string[], metadata: FactMetadata): Fact => ({
  predicate, args, display: `${predicate}(${args.join(', ')})`, metadata,
})
const derived = (predicate: string, ...args: string[]) => tagged(predicate, args, { source: 'local_reasoning', knowledgeStatus: 'current' })

const baseline = [
  tagged('gas_clear', ['excavation_42'], { issuer: 'gas_utility', source: 'gas_utility', scope: ['excavation_42'], version: 1, lifecycle: 'active', knowledgeStatus: 'current', authoritative: true, audience: ['clearance_holder', 'assigned_downstream_actor'], restrictions: ['no cross-utility redistribution'] }),
  tagged('electric_clear', ['excavation_42'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 3, lifecycle: 'active', knowledgeStatus: 'current', authoritative: true, audience: ['clearance_holder', 'assigned_downstream_actor'], restrictions: ['minimum necessary', 'private grid inputs withheld'] }),
  tagged('telecom_clear', ['excavation_42'], { issuer: 'telecom_utility', source: 'telecom_utility', scope: ['excavation_42'], version: 2, lifecycle: 'active', knowledgeStatus: 'current', authoritative: true, audience: ['clearance_holder', 'assigned_downstream_actor'], restrictions: ['no cross-utility redistribution', 'private fiber-route data withheld'] }),
  tagged('permit_active', ['excavation_42'], { issuer: 'municipality', source: 'municipality', scope: ['excavation_42'], version: 5, lifecycle: 'active', knowledgeStatus: 'current', authoritative: true }),
]
const delegation = [
  tagged('delegates', ['general_contractor', 'subcontractor_a', 'excavation_42'], { issuer: 'general_contractor', source: 'general_contractor', scope: ['excavation_42', 'submitted_scope'], version: 1, authoritative: true }),
  tagged('delegates', ['subcontractor_a', 'crew_7', 'excavation_42'], { issuer: 'subcontractor_a', source: 'subcontractor_a', scope: ['excavation_42', 'submitted_scope'], version: 1, authoritative: true }),
]
const heat = tagged('heat_alert', ['county_region_1', 'weekend'], { issuer: 'weather_service', source: 'weather_service', scope: ['county_region_1', 'weekend'], version: 1, authoritative: true })
const activeElectric = tagged('clearance_status', ['electric_clearance_42', 'active'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 3, issuedAt: 'Fri 09:00', validUntil: 'Sun 18:00', lifecycle: 'active', knowledgeStatus: 'current', authoritative: true, audience: ['clearance_holder', 'assigned_downstream_actor'], restrictions: ['minimum necessary', 'private grid inputs withheld'] })
const suspendedElectric = tagged('clearance_status', ['electric_clearance_42', 'suspended'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 4, issuedAt: 'Sat 08:20', lifecycle: 'suspended', knowledgeStatus: 'current', authoritative: true, audience: ['clearance_holder', 'assigned_downstream_actor'], restrictions: ['minimum necessary', 'do not redistribute to unrelated utilities'] })
const staleActiveElectric: Fact = { ...activeElectric, metadata: { ...activeElectric.metadata, knowledgeStatus: 'superseded', supersededBy: suspendedElectric.display } }

type StatusMap = Record<string, ResourceStatus>
const resourceMap = (electric: ResourceStatus): StatusMap => ({
  gas_clearance_42: 'active', electric_clearance_42: electric,
  telecom_clearance_42: 'active', permit_42: 'active',
})

function forwarded(f: Fact, via: string[]): Fact {
  return { ...f, metadata: { ...f.metadata, via, authoritative: true } }
}

function receivedBundle(status: ResourceStatus, via: string[]): Fact[] {
  const stable = baseline.filter(f => f.predicate !== 'electric_clear').map(f => forwarded(f, via))
  return status === 'suspended'
    ? [...stable, forwarded(staleActiveElectric, via), forwarded(suspendedElectric, via)]
    : [...stable, forwarded(activeElectric, via)]
}

function views(electric: { eu: ResourceStatus; gc: ResourceStatus; sub: ResourceStatus; crew: ResourceStatus }, heatKnown: boolean, knowledgeStage: 'contractor' | 'subcontractor' | 'crew' = 'crew'): Record<string, LocalView> {
  const downstream = (status: ResourceStatus, via: string[], establishedKnowledge: Fact[] = []): LocalView => ({
    resources: resourceMap(status), establishedKnowledge, receivedKnowledge: receivedBundle(status, via),
    derivedKnowledge: status === 'suspended' ? [derived('must_stop', 'excavation_42')] : [derived('clearance_bundle_complete', 'excavation_42')],
  })
  const empty = (note: string): LocalView => ({ resources: {}, establishedKnowledge: [], receivedKnowledge: [], derivedKnowledge: [], note })
  const electricEstablished = electric.eu === 'suspended'
    ? [staleActiveElectric, suspendedElectric, tagged('heat_risk_assessed', ['excavation_42'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 4, authoritative: true }), tagged('applies_to', ['electric_clearance_42', 'excavation_42'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 4, authoritative: true })]
    : [activeElectric]
  return {
    weather_service: { resources: {}, establishedKnowledge: heatKnown ? [heat] : [], receivedKnowledge: [], derivedKnowledge: [], note: 'Knows regional conditions, not worksite topology.' },
    electric_utility: { resources: { electric_clearance_42: electric.eu }, establishedKnowledge: electricEstablished, receivedKnowledge: heatKnown ? [forwarded(heat, [])] : [], derivedKnowledge: electric.eu === 'suspended' ? [derived('must_notify', 'general_contractor', 'electric_clearance_42')] : heatKnown ? [derived('review_required', 'electric_clearance_42')] : [] },
    gas_utility: { resources: { gas_clearance_42: 'active' }, establishedKnowledge: [baseline[0]], receivedKnowledge: [], derivedKnowledge: [] },
    telecom_utility: { resources: { telecom_clearance_42: 'active' }, establishedKnowledge: [baseline[2]], receivedKnowledge: [], derivedKnowledge: [] },
    municipality: { resources: { permit_42: 'active' }, establishedKnowledge: [baseline[3]], receivedKnowledge: [], derivedKnowledge: [] },
    general_contractor: downstream(electric.gc, [], knowledgeStage === 'contractor' ? [] : [delegation[0]]),
    subcontractor_a: knowledgeStage === 'contractor' ? empty('Delegation has not arrived.') : downstream(electric.sub, ['general_contractor'], knowledgeStage === 'crew' ? [delegation[1]] : []),
    crew_7: knowledgeStage !== 'crew' ? empty('Assignment has not arrived.') : { ...downstream(electric.crew, ['general_contractor', 'subcontractor_a']), derivedKnowledge: electric.crew === 'suspended' ? [derived('must_stop', 'excavation_42')] : [derived('may_start', 'crew_7', 'excavation_42')] },
  }
}

const heatMessage = (status: Message['status']): Message => ({
  id: 'msg_heat_07', from: 'weather_service', to: 'electric_utility', label: 'Weekend heat alert for County Region 1',
  text: 'We expect excessive heat across County Region 1 this weekend. Please review any affected operations.', facts: [heat], status,
  provenance: ['weather observation 07', 'regional alert', 'scoped utility notice'],
  metadata: { issuer: 'weather_service', scope: ['county_region_1', 'weekend'], version: 1, audience: ['electric_utility'], restrictions: ['operational use only'] },
})

const suspensionFacts = [
  suspendedElectric,
  tagged('applies_to', ['electric_clearance_42', 'excavation_42'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 4, authoritative: true }),
  tagged('issuer', ['electric_clearance_42', 'electric_utility'], { issuer: 'electric_utility', source: 'electric_utility', scope: ['excavation_42'], version: 4, authoritative: true }),
]
const suspensionMessage = (id: string, from: string, to: string, status: Message['status']): Message => ({
  id, from, to, label: 'Electric excavation clearance suspended',
  text: from === 'electric_utility'
    ? 'We have suspended the electrical clearance for excavation 42. Please pause the affected work.'
    : from === 'general_contractor'
      ? 'Electric Utility has suspended the clearance for excavation 42. Stop and notify your assigned crew.'
      : 'Do not begin excavation 42. Electric Utility has suspended the electrical clearance.',
  facts: suspensionFacts, status,
  provenance: ['heat_alert_07', 'electric utility decision', 'clearance suspension'],
  metadata: {
    issuer: 'electric_utility', scope: ['excavation_42'], version: 4, issuedAt: 'Sat 08:20',
    supersedes: 'electric_clearance_42_active_v3', audience: ['clearance_holder', 'assigned_downstream_actor'],
    via: from === 'electric_utility' ? [] : from === 'general_contractor' ? ['general_contractor'] : ['general_contractor', 'subcontractor_a'],
    derivedFrom: ['heat_alert_07', 'electric_utility_private_risk_assessment'],
    restrictions: ['minimum necessary', 'do not redistribute to unrelated utilities'],
  },
})

const requestSpecs = [
  ['gas_utility', 'gas_clearance_42', 'Request gas-safe excavation approval', 'Could you review excavation 42 and approve work near your gas infrastructure?'],
  ['electric_utility', 'electric_clearance_42', 'Request electrical excavation approval', 'Could you review excavation 42 and approve work near your electrical infrastructure?'],
  ['telecom_utility', 'telecom_clearance_42', 'Request telecom excavation approval', 'Could you review excavation 42 and approve work near your telecom infrastructure?'],
  ['municipality', 'permit_42', 'Request municipal excavation permit', 'Could you review excavation 42 and issue the required municipal excavation permit?'],
] as const

const requestMessages = (status: Message['status']): Message[] => requestSpecs.map(([to, resource, label, text]) => ({
  id: `msg_request_${to}`, from: 'general_contractor', to, label,
  text,
  facts: [fact('requests_review', 'general_contractor', resource, 'excavation_42')], status,
  provenance: ['excavation_42 work plan', 'contractor request', `${to} review queue`],
  metadata: { issuer: 'general_contractor', scope: ['excavation_42', 'submitted_scope'], version: 1, audience: [to], restrictions: ['review purpose only'] },
}))

const responseMessage = (authority: string, resource: string, label: string, status: Message['status']): Message => ({
  id: `msg_approve_${authority}`, from: authority, to: 'general_contractor', label,
  text: `${label}. Excavation 42 may proceed within the submitted scope and conditions.`,
  facts: [
    fact('clearance_status', resource, 'active'), fact('applies_to', resource, 'excavation_42'), fact('issuer', resource, authority),
    ...(authority === 'telecom_utility' ? [fact('may_disclose', resource, 'general_contractor'), fact('derived_from', `msg_approve_${authority}`, 'telecom_conduit_map')] : []),
  ],
  status, provenance: [`${authority} local review`, 'scoped approval decision', 'contractor evidence set'],
  metadata: {
    issuer: authority, scope: ['excavation_42', 'submitted_scope'], version: authority === 'electric_utility' ? 3 : 1,
    issuedAt: 'Fri 09:00', validUntil: 'Sun 18:00', audience: ['general_contractor', 'assigned_downstream_actor'],
    shareableWith: ['subcontractor_a', 'crew_7'], derivedFrom: [`${authority}_private_review`],
    restrictions: ['minimum necessary', 'no cross-utility redistribution', 'private inputs withheld'],
  },
})

const approvalHistory: Message[] = [
  ...requestMessages('historical'),
  responseMessage('gas_utility', 'gas_clearance_42', 'Gas excavation clearance approved', 'historical'),
  responseMessage('electric_utility', 'electric_clearance_42', 'Electrical excavation clearance approved', 'historical'),
  responseMessage('telecom_utility', 'telecom_clearance_42', 'Telecom excavation clearance approved', 'historical'),
  responseMessage('municipality', 'permit_42', 'Municipal excavation permit approved', 'historical'),
]

const delegationMessage = (id: string, from: string, to: string, label: string, status: Message['status'], delegationFact: Fact): Message => ({
  id, from, to, label, status,
  text: `You are authorized to perform the assigned work for excavation 42 within the approved scope.`,
  facts: [delegationFact, fact('applies_to', id, 'excavation_42')],
  provenance: ['authorized_for(general_contractor, excavation_42)', 'scoped delegation', `${to} local assignment`],
  metadata: { issuer: from, scope: ['excavation_42', 'submitted_scope'], version: 1, audience: [to], shareableWith: to === 'subcontractor_a' ? ['crew_7'] : [], restrictions: ['no scope expansion'] },
})

const pendingMap: StatusMap = { gas_clearance_42: 'pending', electric_clearance_42: 'pending', telecom_clearance_42: 'pending', permit_42: 'pending' }
const issuerFor: Record<string, string> = { gas_clearance_42: 'gas_utility', electric_clearance_42: 'electric_utility', telecom_clearance_42: 'telecom_utility', permit_42: 'municipality' }
const knowledgeFactsFor = (statuses: StatusMap, received = false) => Object.entries(statuses).map(([id, status]) => tagged(
  id === 'permit_42' ? 'permit_status' : 'clearance_status', [id, status],
  { issuer: issuerFor[id], source: issuerFor[id], scope: ['excavation_42'], version: status === 'active' ? 1 : 0, lifecycle: status, knowledgeStatus: 'current', authoritative: true, via: received ? [] : undefined },
))
const preflightViews = (authority: StatusMap, contractor: StatusMap): Record<string, LocalView> => ({
  weather_service: { resources: {}, establishedKnowledge: [], receivedKnowledge: [], derivedKnowledge: [], note: 'No worksite or delegation knowledge.' },
  gas_utility: { resources: { gas_clearance_42: authority.gas_clearance_42 }, establishedKnowledge: knowledgeFactsFor({ gas_clearance_42: authority.gas_clearance_42 }), receivedKnowledge: [], derivedKnowledge: [] },
  electric_utility: { resources: { electric_clearance_42: authority.electric_clearance_42 }, establishedKnowledge: knowledgeFactsFor({ electric_clearance_42: authority.electric_clearance_42 }), receivedKnowledge: [], derivedKnowledge: [] },
  telecom_utility: { resources: { telecom_clearance_42: authority.telecom_clearance_42 }, establishedKnowledge: knowledgeFactsFor({ telecom_clearance_42: authority.telecom_clearance_42 }), receivedKnowledge: [], derivedKnowledge: [] },
  municipality: { resources: { permit_42: authority.permit_42 }, establishedKnowledge: knowledgeFactsFor({ permit_42: authority.permit_42 }), receivedKnowledge: [], derivedKnowledge: [] },
  general_contractor: { resources: contractor, establishedKnowledge: [], receivedKnowledge: knowledgeFactsFor(contractor, true).filter(f => f.metadata?.lifecycle === 'active'), derivedKnowledge: Object.values(contractor).every(s => s === 'active') ? [derived('clearance_bundle_complete', 'excavation_42')] : [] },
  subcontractor_a: { resources: {}, establishedKnowledge: [], receivedKnowledge: [], derivedKnowledge: [], note: 'Not yet delegated.' },
  crew_7: { resources: {}, establishedKnowledge: [], receivedKnowledge: [], derivedKnowledge: [], note: 'Not yet assigned.' },
})

const preflightFrame = (index: number, title: string, kicker: string, description: string, authority: StatusMap, contractor: StatusMap, messages: Message[], activeMessageIds: string[]): EpisodeStep => ({
  id: `t${index + 1}`, title, kicker, description, phase: 'setup', authoritativeResources: authority,
  localViews: preflightViews(authority, contractor), messages, activeMessageIds, policy: unknown,
})

const pass: PolicyEvaluation = {
  expression: 'may_start(crew_7, excavation_42)', result: 'satisfied',
  checks: [
    { label: 'gas_clear', value: true }, { label: 'electric_clear', value: true },
    { label: 'telecom_clear', value: true }, { label: 'permit_active', value: true },
    { label: 'crew_authorized', value: true },
  ],
}
const unknown: PolicyEvaluation = { ...pass, result: 'unknown', checks: pass.checks.map(c => ({ ...c, value: c.label === 'crew_authorized' ? null : c.value })) }
const violation: PolicyEvaluation = {
  expression: 'may_start(crew_7, excavation_42)', result: 'violated', localResult: 'satisfied',
  checks: pass.checks.map(c => c.label === 'electric_clear' ? ({ ...c, value: false, localValue: true }) : c),
}
const denied: PolicyEvaluation = {
  expression: 'may_start(crew_7, excavation_42)', result: 'denied', localResult: 'denied',
  checks: pass.checks.map(c => c.label === 'electric_clear' ? ({ ...c, value: false, localValue: false }) : c),
}

type FrameInput = Omit<EpisodeStep, 'id' | 'authoritativeResources' | 'localViews'> & {
  electric: { eu: ResourceStatus; gc: ResourceStatus; sub: ResourceStatus; crew: ResourceStatus }
  heatKnown?: boolean
  knowledgeStage?: 'contractor' | 'subcontractor' | 'crew'
}
const frame = (index: number, data: FrameInput): EpisodeStep => {
  const { electric, heatKnown = false, knowledgeStage = 'crew', ...rest } = data
  const workflowMessages: Message[] = [
    ...(index >= 7 ? [delegationMessage('msg_delegate_sub', 'general_contractor', 'subcontractor_a', 'Authorize Subcontractor A for excavation 42', index === 7 ? 'delivered' : 'historical', delegation[0])] : []),
    ...(index >= 8 ? [delegationMessage('msg_assign_crew', 'subcontractor_a', 'crew_7', 'Assign Crew 7 to excavation 42', index === 8 ? 'delivered' : 'historical', delegation[1])] : []),
  ]
  return {
    id: `t${index + 1}`, authoritativeResources: resourceMap(electric.eu), localViews: views(electric, heatKnown, knowledgeStage),
    ...rest, messages: [...approvalHistory, ...workflowMessages, ...rest.messages],
  }
}

const allActive = { eu: 'active', gc: 'active', sub: 'active', crew: 'active' } as const

export const heatRevocationEpisode: Episode = {
  id: 'heat-revocation',
  eyebrow: 'Distributed authorization study · Scenario 01',
  title: 'Heat alert causes clearance revocation',
  scenario: {
    title: 'Underground work coordination',
    summary: 'A contractor must coordinate a proposed excavation with several independently controlled organizations before field work can begin. Each organization keeps its own operational records and communicates only the conclusions needed by the workflow.',
    operatingModel: 'There is no shared application registry containing everyone’s current state. Each principal establishes facts within its own authority, learns other facts through messages, and makes decisions from the knowledge available locally.',
    roles: [
      { id: 'role_contractor', principal: 'General Contractor', description: 'Prepares the excavation plan, requests the required external approvals, assembles the returned evidence, and delegates the approved work downstream.', responsibleFor: 'work plan, coordination, scoped delegation, and forwarding relevant lifecycle updates' },
      { id: 'role_telecom', principal: 'Telecom Utility', description: 'A telecom operator that controls private cable records such as underground location, depth, bandwidth, construction era, route topology, and infrastructure condition. Given a proposed excavation plan, it can evaluate interference risk and issue a scoped clearance or work restriction.', responsibleFor: 'telecom facility assessment and authoritative Telecom clearance state' },
      { id: 'role_electric', principal: 'Electric Utility', description: 'Uses the same coordination model for underground electric assets. It evaluates the submitted plan against private location, loading, topology, maintenance, and asset-health information without exposing those internal inputs.', responsibleFor: 'electric facility assessment and authoritative Electric clearance state' },
      { id: 'role_gas', principal: 'Gas Utility', description: 'Uses the same model for underground gas infrastructure and private pipeline records. It returns the minimum scoped decision needed for safe excavation.', responsibleFor: 'gas facility assessment and authoritative Gas clearance state' },
      { id: 'role_municipality', principal: 'Municipality', description: 'Reviews the excavation under municipal requirements. Its permit is separate from every utility clearance and cannot substitute for one.', responsibleFor: 'authoritative municipal permit state' },
      { id: 'role_weather', principal: 'Weather Service', description: 'Observes regional weather conditions and issues alerts. It does not know the contractor’s work-assignment topology and cannot change a utility clearance itself.', responsibleFor: 'authoritative regional weather alerts' },
      { id: 'role_subcontractor', principal: 'Subcontractor A', description: 'Receives a bounded work delegation from the General Contractor and may assign only the permitted portion of that work to its known field crew.', responsibleFor: 'local downstream assignment and propagation to Crew 7' },
      { id: 'role_crew', principal: 'Crew 7', description: 'Performs the field work. It may begin only from the clearances, permit, restrictions, and delegation currently present in its own local knowledge.', responsibleFor: 'executing or refusing the excavation action' },
    ],
  },
  principals: [
    { id: 'weather_service', label: 'Weather Service', shortLabel: 'Weather', kind: 'signal', authority: ['regional weather alerts'], position: { x: 85, y: 90 } },
    { id: 'gas_utility', label: 'Gas Utility', shortLabel: 'Gas', kind: 'utility', authority: ['gas clearance state'], position: { x: 83, y: 255 } },
    { id: 'electric_utility', label: 'Electric Utility', shortLabel: 'Electric', kind: 'utility', authority: ['electric clearance state', 'electric facility constraints'], position: { x: 285, y: 90 } },
    { id: 'telecom_utility', label: 'Telecom Utility', shortLabel: 'Telecom', kind: 'utility', authority: ['telecom clearance state'], position: { x: 82, y: 420 } },
    { id: 'municipality', label: 'Municipality', shortLabel: 'Municipality', kind: 'authority', authority: ['excavation permits'], position: { x: 285, y: 420 } },
    { id: 'general_contractor', label: 'General Contractor', shortLabel: 'Gen. Contractor', kind: 'contractor', authority: ['job coordination', 'scoped delegation'], position: { x: 505, y: 255 } },
    { id: 'subcontractor_a', label: 'Subcontractor A', shortLabel: 'Subcontractor A', kind: 'contractor', authority: ['delegated excavation 42'], position: { x: 705, y: 255 } },
    { id: 'crew_7', label: 'Field Crew 7', shortLabel: 'Crew 7', kind: 'field', authority: ['perform assigned field work'], position: { x: 895, y: 255 } },
  ],
  resources: [
    { id: 'gas_clearance_42', label: 'Gas clearance', status: 'active', authority: 'gas_utility' },
    { id: 'electric_clearance_42', label: 'Electric clearance', status: 'active', authority: 'electric_utility' },
    { id: 'telecom_clearance_42', label: 'Telecom clearance', status: 'active', authority: 'telecom_utility' },
    { id: 'permit_42', label: 'Municipal permit', status: 'active', authority: 'municipality' },
  ],
  policies: [
    { id: '1', family: 'information-flow', title: 'Utility data minimization', text: 'A utility may share only the clearance decision, validity, and necessary work restrictions. It must not expose internal grid topology, telemetry, fiber routes, asset health, maintenance data, or review notes.' },
    { id: '2', family: 'information-flow', title: 'Cross-utility isolation', text: 'A contractor must not share one utility’s clearance, comments, or facility information with another utility unless that utility is explicitly authorized to receive it.' },
    { id: '3', family: 'authority', title: 'Authority stays with the issuer', text: 'Forwarding or learning a clearance does not make the recipient authoritative. Only the issuing utility may create, update, suspend, revoke, or otherwise establish that clearance.' },
    { id: '4', family: 'authorization', title: 'Delegation is scoped', text: 'A delegation applies only to the specified job and work scope. It does not implicitly authorize different locations, methods, times, or further delegation.' },
    { id: '5', family: 'authorization', title: 'All required approvals must be valid before work starts', text: 'Crew 7 may begin excavation only when the Gas, Electric, and Telecom clearances are all valid, the permit is active, and Crew 7 has valid delegation.' },
    { id: '6', family: 'lifecycle', title: 'Latest lifecycle state wins', text: 'Only the latest authoritative version of a clearance counts. A suspension, revocation, or expiration invalidates older approvals, and any party that previously forwarded dependent work authority must pass the update to its known downstream recipients.' },
  ],
  steps: [
    preflightFrame(0, 'Excavation 42 is proposed', 'No evidence exists yet', 'The General Contractor creates the work package. Every required clearance is still pending.', pendingMap, pendingMap, [], []),
    preflightFrame(1, 'Contractor requests review', 'Four directed requests leave one node', 'Gas, electric, telecom, and municipal authorities each receive only the submitted excavation scope.', pendingMap, pendingMap, requestMessages('in_transit'), requestMessages('in_transit').map(m => m.id)),
    preflightFrame(2, 'Authorities receive requests', 'Independent review begins', 'Each organization evaluates the request against its own private records and authority.', pendingMap, pendingMap, requestMessages('delivered'), requestMessages('delivered').map(m => m.id)),
    preflightFrame(3, 'Gas clearance is issued', 'Evidence returns independently', 'Gas Utility approves the submitted scope; the reply is traveling back to the contractor.', { ...pendingMap, gas_clearance_42: 'active' }, pendingMap, [...requestMessages('historical'), responseMessage('gas_utility', 'gas_clearance_42', 'Gas excavation clearance approved', 'in_transit')], ['msg_approve_gas_utility']),
    preflightFrame(4, 'Electric clearance is issued', 'Two authorities have decided', 'The contractor knows the gas result while Electric Utility sends its own scoped approval.', { ...pendingMap, gas_clearance_42: 'active', electric_clearance_42: 'active' }, { ...pendingMap, gas_clearance_42: 'active' }, [...requestMessages('historical'), responseMessage('gas_utility', 'gas_clearance_42', 'Gas excavation clearance approved', 'historical'), responseMessage('electric_utility', 'electric_clearance_42', 'Electrical excavation clearance approved', 'in_transit')], ['msg_approve_electric_utility']),
    preflightFrame(5, 'Final approvals are returned', 'Evidence set is almost complete', 'Telecom Utility and Municipality return scoped decisions without exposing their underlying records.', { gas_clearance_42: 'active', electric_clearance_42: 'active', telecom_clearance_42: 'active', permit_42: 'active' }, { ...pendingMap, gas_clearance_42: 'active', electric_clearance_42: 'active' }, [...requestMessages('historical'), responseMessage('gas_utility', 'gas_clearance_42', 'Gas excavation clearance approved', 'historical'), responseMessage('electric_utility', 'electric_clearance_42', 'Electrical excavation clearance approved', 'historical'), responseMessage('telecom_utility', 'telecom_clearance_42', 'Telecom excavation clearance approved', 'in_transit'), responseMessage('municipality', 'permit_42', 'Municipal excavation permit approved', 'in_transit')], ['msg_approve_telecom_utility', 'msg_approve_municipality']),
    frame(6, { title: 'All clearances active', kicker: 'Baseline established', description: 'The contractor has assembled four approvals; downstream agents do not know them yet.', phase: 'setup', electric: allActive, knowledgeStage: 'contractor', messages: [], activeMessageIds: [], policy: unknown }),
    frame(7, { title: 'Work delegated downstream', kicker: 'Authority moves by explicit grant', description: 'The General Contractor delegates only excavation 42 to Subcontractor A.', phase: 'setup', electric: allActive, knowledgeStage: 'subcontractor', messages: [], activeMessageIds: ['msg_delegate_sub'], policy: unknown }),
    frame(8, { title: 'Crew 7 is assigned', kicker: 'Local evidence is complete', description: 'Crew 7 receives a scoped assignment and locally sees every prerequisite as active.', phase: 'setup', electric: allActive, messages: [], activeMessageIds: ['msg_assign_crew'], policy: pass, effects: [{ id: 'e_ready', actor: 'crew_7', expression: 'ready(excavation_42)', outcome: 'allowed' }] }),
    frame(9, { title: 'Heat alert issued', kicker: 'A new fact enters the network', description: 'Weather Service observes a weekend heat event. It does not know the worksite topology.', phase: 'trigger', electric: allActive, heatKnown: true, messages: [heatMessage('sent')], activeMessageIds: ['msg_heat_07'], policy: pass }),
    frame(10, { title: 'Alert reaches Electric Utility', kicker: 'Scoped delivery', description: 'The alert is delivered to the principal that can interpret it against private grid state.', phase: 'trigger', electric: allActive, heatKnown: true, messages: [heatMessage('delivered')], activeMessageIds: ['msg_heat_07'], policy: pass }),
    frame(11, { title: 'Electric clearance suspended', kicker: 'Authoritative state changes locally', description: 'Electric Utility suspends its clearance. Every downstream local view still says active.', phase: 'gap', electric: { ...allActive, eu: 'suspended' }, heatKnown: true, messages: [heatMessage('historical')], activeMessageIds: [], policy: { ...violation, result: 'denied' }, annotation: 'The authoritative change exists at exactly one principal.' }),
    frame(12, { title: 'Suspension notice sent', kicker: 'Propagation begins', description: 'A scoped fact—not the internal grid map—is sent to the General Contractor.', phase: 'gap', electric: { ...allActive, eu: 'suspended' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'in_transit')], activeMessageIds: ['msg_suspend_gc'], policy: { ...violation, result: 'denied' } }),
    frame(13, { title: 'Contractor receives suspension', kicker: 'Knowledge is now inconsistent', description: 'The contractor updates its local view. Subcontractor A and Crew 7 remain stale.', phase: 'gap', electric: { eu: 'suspended', gc: 'suspended', sub: 'active', crew: 'active' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'delivered')], activeMessageIds: ['msg_suspend_gc'], policy: { ...violation, result: 'denied' }, annotation: '2 of 4 dependent principals still believe the electric clearance is active.' }),
    frame(14, { title: 'Crew attempts to start', kicker: 'Local knowledge conflicts with issuer state', description: 'Crew 7 acts on stale evidence. Its local inference permits work, while Electric Utility has already suspended E42.', phase: 'violation', electric: { eu: 'suspended', gc: 'suspended', sub: 'active', crew: 'active' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'delivered')], activeMessageIds: [], policy: violation, effects: [{ id: 'e_start_1', actor: 'crew_7', expression: 'start_excavation(crew_7, excavation_42)', outcome: 'violation' }], annotation: 'Crew 7 inferred may_start from stale local facts; no central policy lookup occurred.' }),
    frame(15, { title: 'Contractor forwards suspension', kicker: 'Revocation follows delegation', description: 'The contractor forwards the same scoped lifecycle fact to Subcontractor A.', phase: 'resolution', electric: { eu: 'suspended', gc: 'suspended', sub: 'active', crew: 'active' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'historical'), suspensionMessage('msg_suspend_sub', 'general_contractor', 'subcontractor_a', 'in_transit')], activeMessageIds: ['msg_suspend_sub'], policy: { ...violation, result: 'denied' } }),
    frame(16, { title: 'Subcontractor learns suspension', kicker: 'One stale view remains', description: 'Subcontractor A updates local state and forwards the notice to its assigned crew.', phase: 'resolution', electric: { eu: 'suspended', gc: 'suspended', sub: 'suspended', crew: 'active' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'historical'), suspensionMessage('msg_suspend_sub', 'general_contractor', 'subcontractor_a', 'delivered'), suspensionMessage('msg_suspend_crew', 'subcontractor_a', 'crew_7', 'in_transit')], activeMessageIds: ['msg_suspend_sub', 'msg_suspend_crew'], policy: { ...violation, result: 'denied' }, annotation: 'Crew 7 is now the only dependent principal with a stale view.' }),
    frame(17, { title: 'Crew refuses to start', kicker: 'Local and global state converge', description: 'Crew 7 receives the suspension. A second start attempt is correctly blocked locally.', phase: 'resolution', electric: { eu: 'suspended', gc: 'suspended', sub: 'suspended', crew: 'suspended' }, heatKnown: true, messages: [heatMessage('historical'), suspensionMessage('msg_suspend_gc', 'electric_utility', 'general_contractor', 'historical'), suspensionMessage('msg_suspend_sub', 'general_contractor', 'subcontractor_a', 'historical'), suspensionMessage('msg_suspend_crew', 'subcontractor_a', 'crew_7', 'delivered')], activeMessageIds: ['msg_suspend_crew'], policy: denied, effects: [{ id: 'e_start_2', actor: 'crew_7', expression: 'start_excavation(crew_7, excavation_42)', outcome: 'blocked' }], annotation: 'All relevant principals now agree: electric_clearance_42 is suspended.' }),
  ],
}

export default heatRevocationEpisode
