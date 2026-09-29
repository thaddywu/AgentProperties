import type { CombinationPolicy, DisclosureDecision, Episode, Fact, KnowledgeLabel, LocalView, Message } from '../../src/types/episode'
import { evaluateDisclosureReceive } from '../../src/policy/disclosure'

const NOVA_DOMAIN = 'nova-strategy@1'
const NOVA_POLICY = 'nova-combination-control@1'
const PROCUREMENT_ATOM: KnowledgeLabel = { domainId: NOVA_DOMAIN, atomId: 'procurement-plan' }
const INFRASTRUCTURE_ATOM: KnowledgeLabel = { domainId: NOVA_DOMAIN, atomId: 'infrastructure-plan' }
const PRODUCT_LAUNCH_ATOM: KnowledgeLabel = { domainId: NOVA_DOMAIN, atomId: 'product-launch-plan' }
const combinationPolicies: CombinationPolicy[] = [{
  id: NOVA_POLICY,
  domainId: NOVA_DOMAIN,
  forbiddenSets: [['procurement-plan', 'infrastructure-plan', 'product-launch-plan']],
}]

const fact = (predicate: string, args: string[], display: string, category: NonNullable<Fact['metadata']>['category']): Fact => ({
  predicate, args, display, metadata: { category, knowledgeStatus: 'current' },
})

const procurementBudget = fact('approved_budget_increase', ['procurement', 'q1', '120m'], 'Procurement increase · +$120M', 'financial')
const facilitiesBudget = fact('approved_budget_increase', ['facilities', 'q1', '80m'], 'Facilities increase · +$80M', 'financial')
const productBudget = fact('approved_budget_increase', ['product_operations', 'q1_q2', '35m'], 'Product Operations increase · +$35M', 'financial')
const totalBudget = fact('total_incremental_spending', ['q1_q2', '235m'], 'Total incremental approved spending · +$235M', 'financial')
const procurementFragment = fact('restricted_explanation', ['accelerator_order', 'q1'], 'Large custom-accelerator order · Q1 delivery', 'restricted')
const facilitiesFragment = fact('restricted_explanation', ['site_west', '35mw', 'q1'], 'Site West capacity expansion · 35 MW by Q1', 'restricted')
const launchFragment = fact('restricted_explanation', ['enterprise_offering', 'q2', '50_customers'], 'Enterprise offering · Q2 · ~50 customers', 'restricted')
const attestation = fact('strategic_justification_verified', ['q1_q2_budget_package', 'approved'], 'Strategic justification · independently verified', 'attestation')
const auditPass = fact('budget_review', ['q1_q2_budget_package', 'pass'], 'Overall budget review · PASS', 'attestation')
const boardApprovalReference = fact('board_approval_reference', ['q1_q2_budget_package', 'valid'], 'Board approval reference · valid', 'attestation')
const blockedReviewFact = fact('reports_review_blocked', ['q1_q2_budget_package', 'product_operations_35m'], 'Sensitive review required · Product Operations +$35M', 'operational')

const allFinance = [procurementBudget, facilitiesBudget, productBudget, totalBudget]
const allRestricted = [procurementFragment, facilitiesFragment, launchFragment]

const emptyView = (note?: string): LocalView => ({ resources: {}, establishedKnowledge: [], receivedKnowledge: [], derivedKnowledge: [], note })

function views({
  departmentLabels = [] as KnowledgeLabel[],
  finance = 0,
  auditLabels = [] as KnowledgeLabel[],
  strategicLabels = [] as KnowledgeLabel[],
  strategicAssigned = false,
  boardReportKnown = false,
  attestationIssued = false,
  attestationReceived = false,
  passed = false,
}: {
  departmentLabels?: KnowledgeLabel[]
  finance?: number
  auditLabels?: KnowledgeLabel[]
  strategicLabels?: KnowledgeLabel[]
  strategicAssigned?: boolean
  boardReportKnown?: boolean
  attestationIssued?: boolean
  attestationReceived?: boolean
  passed?: boolean
} = {}): Record<string, LocalView> {
  const auditRestricted = auditLabels.map(label => label.atomId === 'infrastructure-plan' ? facilitiesFragment : label.atomId === 'procurement-plan' ? procurementFragment : launchFragment)
  const strategicRestricted = strategicLabels.map(label => label.atomId === 'infrastructure-plan' ? facilitiesFragment : label.atomId === 'procurement-plan' ? procurementFragment : launchFragment)
  const financeFacts = finance === 0 ? [] : allFinance.slice(0, finance)
  const departmentHas = (atomId: string) => departmentLabels.some(label => label.domainId === NOVA_DOMAIN && label.atomId === atomId)
  return {
    executive_board: {
      resources: {}, establishedKnowledge: allRestricted, receivedKnowledge: boardReportKnown ? [blockedReviewFact] : [],
      derivedKnowledge: [fact('initiative_authorized', ['project_nova'], 'Project Nova · authorized', 'operational')],
      disclosureState: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], policyExemptions: [NOVA_POLICY],
      note: 'The Board establishes the initiative, but is not an online message-by-message policy checker.',
    },
    procurement: {
      resources: {}, establishedKnowledge: [procurementBudget], receivedKnowledge: departmentHas('procurement-plan') ? [procurementFragment] : [], derivedKnowledge: [], disclosureState: departmentHas('procurement-plan') ? [PROCUREMENT_ATOM] : [],
      note: 'Knows its purchase commitment, not the complete initiative.',
    },
    facilities: {
      resources: {}, establishedKnowledge: [facilitiesBudget], receivedKnowledge: departmentHas('infrastructure-plan') ? [facilitiesFragment] : [], derivedKnowledge: [], disclosureState: departmentHas('infrastructure-plan') ? [INFRASTRUCTURE_ATOM] : [],
      note: 'Knows its capacity work, not the complete initiative.',
    },
    product_operations: {
      resources: {}, establishedKnowledge: [productBudget], receivedKnowledge: departmentHas('product-launch-plan') ? [launchFragment] : [], derivedKnowledge: [], disclosureState: departmentHas('product-launch-plan') ? [PRODUCT_LAUNCH_ATOM] : [],
      note: 'Knows launch readiness, not the complete initiative.',
    },
    corporate_budget_audit: {
      resources: {}, establishedKnowledge: [], receivedKnowledge: [...financeFacts, ...auditRestricted, ...(attestationReceived ? [attestation] : [])],
      derivedKnowledge: [
        ...(finance >= 3 ? [totalBudget] : []),
        ...(passed ? [auditPass] : []),
      ],
      disclosureState: auditLabels, policyExemptions: [],
      note: passed
        ? 'The audit completed without receiving the product-launch atom; the authorized review supplied the missing verification property.'
        : 'Receive decisions use only this tracked disclosure state plus incoming knowledge labels and local policy exemptions.',
    },
    strategic_budget_auditor: {
      ...emptyView('Designated for sensitive review, but still prohibited from completing the Nova forbidden set.'),
      establishedKnowledge: [],
      receivedKnowledge: [...(strategicAssigned ? [boardApprovalReference] : []), ...strategicRestricted],
      derivedKnowledge: attestationIssued ? [attestation] : [],
      disclosureState: strategicLabels,
      policyExemptions: [],
    },
  }
}

const budgetMessage = (id: string, from: string, amount: string, status: Message['status']): Message => ({
  id, from, to: 'corporate_budget_audit', label: `${amount} approved budget submission`,
  text: `Q1 approved budget increase: ${amount}.`,
  facts: [from === 'procurement' ? procurementBudget : from === 'facilities' ? facilitiesBudget : productBudget],
  knowledgeLabels: [], status,
  metadata: { scope: ['q1_q2_budget_package'], audience: ['corporate_budget_audit'], restrictions: ['ordinary audit use'] },
  provenance: [`${from} approved ledger`, 'budget package Q1-27'],
})

const boardInstruction = (id: string, to: string, label: string, text: string, taggedFact: Fact, knowledgeLabel: KnowledgeLabel, status: Message['status']): Message => ({
  id, from: 'executive_board', to, label, text, facts: [taggedFact], knowledgeLabels: [knowledgeLabel], status,
  metadata: {
    issuer: 'executive_board', scope: ['restricted_board_initiative'], audience: [to],
    restrictions: ['recipient-local execution only'], releaseNote: 'Released after the recipient-local disclosure-combination check.',
  },
  provenance: ['Executive Board decision', 'separated execution instruction', `knowledge label (${knowledgeLabel.domainId}, ${knowledgeLabel.atomId})`],
})

const boardProcurement = (status: Message['status']) => boardInstruction(
  'msg_board_procurement', 'procurement', 'Q1 accelerator procurement directive',
  'Commit the approved custom-accelerator order for delivery before the end of Q1.', procurementFragment, PROCUREMENT_ATOM, status,
)
const boardFacilities = (status: Message['status']) => boardInstruction(
  'msg_board_facilities', 'facilities', 'Site West capacity directive',
  'Complete the approved 35 MW Site West capacity expansion by the end of Q1.', facilitiesFragment, INFRASTRUCTURE_ATOM, status,
)
const boardProduct = (status: Message['status']) => boardInstruction(
  'msg_board_product', 'product_operations', 'Q2 launch-readiness directive',
  'Prepare the approved enterprise offering for Q2 with initial capacity for approximately 50 large customers.', launchFragment, PRODUCT_LAUNCH_ATOM, status,
)

const varianceQuestion = (id: string, to: string, amount: string, period: string): Message => ({
  id, from: 'corporate_budget_audit', to, label: `Variance question · ${amount}`,
  text: `What business activity is driving the ${amount} ${period} approved budget increase?`,
  facts: [fact('requests_variance_explanation', [to, amount, period], `Variance explanation requested · ${to} · ${amount}`, 'operational')],
  knowledgeLabels: [], status: 'in_transit',
  metadata: { scope: ['q1_q2_budget_package'], audience: [to], restrictions: ['ordinary audit request; no strategic disclosure atom'] },
})

const explanationMessage = (id: string, from: string, label: string, text: string, taggedFact: Fact, knowledgeLabel: KnowledgeLabel, status: Message['status']): Message => ({
  id, from, to: 'corporate_budget_audit', label, text, facts: [taggedFact], knowledgeLabels: [knowledgeLabel], status,
  metadata: {
    scope: ['q1_q2_budget_package'], audience: ['corporate_budget_audit'], restrictions: ['local disclosure-combination check'],
    releaseNote: status === 'denied' ? 'Payload withheld from Corporate Budget Audit agent context.' : 'Released after local prospective disclosure-state check.',
  },
  provenance: [`${from} local business record`, 'content-specific labeler', `knowledge label (${knowledgeLabel.domainId}, ${knowledgeLabel.atomId})`],
})

const facilityExplanation = (status: Message['status']) => explanationMessage(
  'msg_facilities_reason', 'facilities', 'Facilities variance explanation',
  'The increase is driven by a 35 MW Site West capacity expansion targeted for completion by the end of Q1.',
  facilitiesFragment, INFRASTRUCTURE_ATOM, status,
)
const procurementExplanation = (status: Message['status']) => explanationMessage(
  'msg_procurement_reason', 'procurement', 'Procurement variance explanation',
  'The increase is driven by a large custom-accelerator purchase scheduled for Q1 delivery.',
  procurementFragment, PROCUREMENT_ATOM, status,
)
const productExplanation = (to: string, status: Message['status'], id = 'msg_product_reason'): Message => ({
  ...explanationMessage(id, 'product_operations', 'Product Operations variance explanation',
    'The increase supports a new enterprise offering scheduled for Q2, with initial capacity planned for approximately 50 large customers.',
    launchFragment, PRODUCT_LAUNCH_ATOM, status),
  to,
})

const boardReport: Message = {
  id: 'msg_report_blocked_review', from: 'corporate_budget_audit', to: 'executive_board',
  label: 'Report blocked justification review',
  text: 'The local policy guard cannot release the Product Operations +$35M variance explanation to Corporate Budget Audit. Please assign an independent sensitive review.',
  facts: [blockedReviewFact],
  knowledgeLabels: [], status: 'in_transit',
  metadata: { scope: ['q1_q2_budget_package'], audience: ['executive_board'], restrictions: ['does not include the withheld product-launch explanation'] },
}

const boardAssignment: Message = {
  id: 'msg_assign_strategic_audit', from: 'executive_board', to: 'strategic_budget_auditor',
  label: 'Assign independent strategic review',
  text: 'Independently review the restricted justification for the Product Operations +$35M variance and return only the verification result to Corporate Budget Audit.',
  facts: [fact('assigns_strategic_review', ['q1_q2_budget_package', 'product_operations_35m'], 'Strategic review assigned · Product Operations +$35M', 'operational'), boardApprovalReference],
  knowledgeLabels: [], status: 'in_transit',
  metadata: { issuer: 'executive_board', scope: ['q1_q2_budget_package'], audience: ['strategic_budget_auditor'], restrictions: ['review product-launch-plan only', 'return attestation without strategic details'] },
}

const reviewMessage = (status: Message['status']): Message => {
  const message = productExplanation('strategic_budget_auditor', status, 'msg_review_f2')
  return { ...message, metadata: { ...message.metadata, audience: ['strategic_budget_auditor'], releaseNote: 'Released: the prospective disclosure state does not contain the Nova forbidden set.' } }
}

const attestationMessage = (status: Message['status']): Message => ({
  id: 'msg_attestation', from: 'strategic_budget_auditor', to: 'corporate_budget_audit',
  label: 'Restricted justification verified',
  text: 'The restricted strategic justification for the Q1–Q2 budget package has been independently reviewed and is consistent with an approved Board initiative.',
  facts: [attestation], knowledgeLabels: [], status,
  metadata: { scope: ['q1_q2_budget_package'], audience: ['corporate_budget_audit'], restrictions: ['verification only; no strategic details'] },
  provenance: ['authorized Nova-domain review', 'approved Board initiative', 'explicit narrow-release rule'],
})

const allow = (current: string[], incoming: string[], exempt = false) => ({
  expression: 'forbidden_set(nova-strategy@1) not_subset_of prospective_state OR exempt(i, nova-combination-control@1)',
  result: 'satisfied' as const,
  checks: [
    { label: `current_atoms = ${current.length}`, value: true },
    { label: `incoming_new_atoms = ${incoming.filter(item => !current.includes(item)).length}`, value: true },
    { label: 'forbidden set remains incomplete', value: exempt || !combinationPolicies[0].forbiddenSets.some(set => set.every(atom => new Set([...current, ...incoming]).has(atom))) },
  ],
})
const noEvaluation = { expression: 'local receive check', result: 'unknown' as const, checks: [{ label: 'restricted message pending', value: null }] }

const localDecision = (recipient: string, currentLabels: KnowledgeLabel[], incomingLabels: KnowledgeLabel[], exempt = false): DisclosureDecision => {
  const evaluation = evaluateDisclosureReceive({
    labels: currentLabels,
    policyExemptions: exempt ? [NOVA_POLICY] : [],
  }, incomingLabels, combinationPolicies)
  const result = evaluation.checks[0]
  return {
    recipient,
    policyId: result.policyId,
    domainId: result.domainId,
    currentAtoms: result.currentAtoms,
    incomingAtoms: result.incomingAtoms,
    prospectiveAtoms: result.prospectiveAtoms,
    matchedForbiddenSet: result.matchedForbiddenSet,
    exemptionApplied: result.exemptionApplied,
    result: result.allowed ? 'allow' : 'deny',
    messageIndividuallyPermissible: true,
    routeIndividuallyPermissible: true,
  }
}

const budgetProcurement = (status: Message['status']) => budgetMessage('msg_budget_procurement', 'procurement', '+$120M', status)
const budgetFacilities = (status: Message['status']) => budgetMessage('msg_budget_facilities', 'facilities', '+$80M', status)
const budgetProduct = (status: Message['status']) => budgetMessage('msg_budget_product', 'product_operations', '+$35M', status)

const policies: Episode['policies'] = [
  { id: 'A', family: 'information-flow', title: 'Aggregate Budget Visibility', text: 'Corporate Budget Audit may receive totals, approved amounts, ledger entries, and ordinary accounting metadata. Department participation does not label every financial fact as a Nova disclosure atom.', expression: 'budget_fact(x) -> may_receive(corporate_budget_audit, x)' },
  { id: 'B', family: 'information-flow', title: 'Content-Specific Knowledge Labels', text: 'Knowledge labels attach to content that reveals a policy-defined disclosure atom, not to the sender. The same department can send an unlabeled total and a labeled strategic explanation.', expression: 'Labels(x) depends_on content(x), not sender(x)' },
  { id: 'C', family: 'information-flow', title: 'Forbidden Knowledge Combination', text: 'Every non-Board principal—including both audit functions—must keep the complete Nova forbidden set out of its tracked disclosure state. Repeated disclosure of the same atom does not change the set.', expression: 'ForbiddenNova not_subset_of H_i(nova-strategy@1)' },
  { id: 'D', family: 'authorization', title: 'Executive Board Is the Sole Exception', text: 'Only Executive Board is exempt from nova-combination-control@1. Strategic Budget Auditor is a designated reviewer but has no policy exemption.', expression: 'exempt(i, nova-combination-control@1) iff i = executive_board' },
  { id: 'E', family: 'information-flow', title: 'Local Prospective-State Enforcement', text: 'A receive decision combines the recipient’s tracked disclosure state, incoming knowledge labels, and policy exemptions. It is not a static sender-recipient ACL.', expression: 'MayReceive(i,x) := safe(H_i union Labels(x), Policies_i)' },
  { id: 'F', family: 'authority', title: 'No Central Knowledge Query', text: 'No principal queries a global knowledge registry during delivery, and the Board does not approve every message online.', expression: 'decision_input = local_state + incoming_metadata' },
  { id: 'G', family: 'information-flow', title: 'Opaque Policy Metadata', text: 'Business agents see normal business language. Their local guards compare opaque identifiers; only Researcher view exposes the domain/atom semantic mapping.', expression: '(nova-strategy@1, infrastructure-plan) is opaque to application principals' },
  { id: 'H', family: 'authorization', title: 'Board-Coordinated Review and Safe Attestation', text: 'After a receive denial, Budget Audit reports the blocked item without the withheld detail. Strategic Budget Auditor inspects only the product-launch atom and returns a narrower verification fact.', expression: 'denial -> independent_review(product-launch-plan) -> narrow_attestation' },
  { id: 'I', family: 'information-flow', title: 'Label-Preserving Derivation', text: 'Paraphrasing or summarizing restricted content preserves its knowledge labels by default. Only an explicitly modeled release rule may emit a narrower unlabeled fact such as the verification attestation.', expression: 'Labels(output) superseteq union Labels(inputs), unless approved_release_rule' },
  { id: 'J', family: 'information-flow', title: 'Multi-Label Artifacts', text: 'Messages may carry multiple inference-domain/disclosure-atom pairs. Every affected policy is evaluated atomically before any payload is released.', expression: 'Labels(x) subset_of InferenceDomain × DisclosureAtom' },
]

const episode: Episode = {
  id: 'budget-compartment',
  title: 'Knowledge-Combination Budget Audit',
  eyebrow: 'APP 2 · EXCESSIVE KNOWLEDGE CONVERGENCE',
  scenario: {
    title: 'Knowledge-Combination Corporate Budget Audit',
    summary: 'A company is preparing the unannounced Project Nova. Procurement, Facilities, and Product Operations each hold one policy-defined disclosure atom. Except for Executive Board, no principal may accumulate the complete forbidden Nova atom set.',
    operatingModel: 'There is no central knowledge database in the delivery path. Each recipient guard tests its prospective tracked disclosure state against explicit forbidden sets. When Budget Audit cannot receive the product-launch atom, the Board assigns an independent review that returns only a narrow attestation.',
    roles: [
      { id: 'board', principal: 'Executive Board', description: 'Establishes Project Nova and knows the complete strategic plan without acting as an online policy oracle.', responsibleFor: 'Initiative authorization; exemption from nova-combination-control@1' },
      { id: 'procurement', principal: 'Procurement', description: 'Knows the Q1 custom-accelerator order and can separately disclose its ordinary approved budget total.', responsibleFor: 'Supplier commitments; atom procurement-plan' },
      { id: 'facilities', principal: 'Facilities', description: 'Knows the 35 MW Site West expansion and can separately disclose ordinary budget data.', responsibleFor: 'Infrastructure capacity; atom infrastructure-plan' },
      { id: 'product', principal: 'Product Operations', description: 'Knows the Q2 enterprise offering and its initial capacity plan.', responsibleFor: 'Launch readiness; atom product-launch-plan' },
      { id: 'audit', principal: 'Corporate Budget Audit', description: 'Reconciles all financial amounts and investigates variances, but cannot reconstruct the complete Nova strategy.', responsibleFor: 'Ordinary company-wide budget review; forbidden-set enforcement' },
      { id: 'strategic_audit', principal: 'Strategic Budget Auditor', description: 'Reviews the escalated restricted item and returns a narrow verification attestation without collecting the other Nova atoms.', responsibleFor: 'Sensitive review; no Nova policy exemption' },
    ],
  },
  principals: [
    { id: 'executive_board', label: 'Executive Board', shortLabel: 'Executive Board', kind: 'board', authority: ['authorize initiatives', 'exempt(nova-combination-control@1)'], position: { x: 438, y: 55 } },
    { id: 'procurement', label: 'Procurement', shortLabel: 'Procurement', kind: 'department', authority: ['establish procurement records'], position: { x: 65, y: 95 } },
    { id: 'facilities', label: 'Facilities', shortLabel: 'Facilities', kind: 'department', authority: ['establish facilities records'], position: { x: 65, y: 225 } },
    { id: 'product_operations', label: 'Product Operations', shortLabel: 'Product Ops', kind: 'department', authority: ['establish launch-readiness records'], position: { x: 65, y: 355 } },
    { id: 'corporate_budget_audit', label: 'Corporate Budget Audit', shortLabel: 'Budget Audit', kind: 'audit', authority: ['reconcile budgets', 'request explanations', 'issue audit report'], position: { x: 438, y: 225 } },
    { id: 'strategic_budget_auditor', label: 'Strategic Budget Auditor', shortLabel: 'Strategic Auditor', kind: 'authority', authority: ['verify escalated justifications', 'subject to Nova forbidden set'], position: { x: 830, y: 225 } },
  ],
  resources: [],
  policies,
  combinationPolicies,
  graphEdges: [
    ['executive_board', 'procurement'], ['executive_board', 'facilities'], ['executive_board', 'product_operations'],
    ['procurement', 'corporate_budget_audit'], ['facilities', 'corporate_budget_audit'], ['product_operations', 'corporate_budget_audit'],
    ['executive_board', 'corporate_budget_audit'], ['executive_board', 'strategic_budget_auditor'],
    ['corporate_budget_audit', 'strategic_budget_auditor'], ['product_operations', 'strategic_budget_auditor'],
  ],
  graphDomains: [{ label: 'COMPARTMENTED DEPARTMENTS', x: 2 }, { label: 'ORDINARY AUDIT', x: 43 }, { label: 'AUTHORIZED REVIEW', x: 78 }],
  researcherView: {
    title: 'Knowledge-label semantic map',
    disclaimer: 'Omniscient simulator instrumentation only. This mapping and cross-principal comparison are not available to application agents or local guards.',
    domains: [{ id: NOVA_DOMAIN, label: 'Project Nova strategy', atoms: [
      { id: 'procurement-plan', label: 'Procurement component' },
      { id: 'infrastructure-plan', label: 'Infrastructure component' },
      { id: 'product-launch-plan', label: 'Product-launch component' },
    ] }],
  },
  steps: [
    {
      id: 'n01', title: 'Project Nova exists', kicker: 'One inference domain · three disclosure atoms',
      description: 'The Board knows the complete plan and is exempt from the Nova combination policy. The operating departments and both audit teams start with empty tracked disclosure state.',
      phase: 'setup', authoritativeResources: {}, localViews: views(), messages: [], activeMessageIds: [], policy: noEvaluation,
      activePolicyIds: ['C', 'D', 'F'], annotation: 'The Board will distribute only the component each operating department needs.',
    },
    {
      id: 'n02', title: 'Board briefs Procurement', kicker: 'Labeled instruction · procurement-plan',
      description: 'The Board sends only the Q1 accelerator directive to Procurement. The content carries a Nova-domain procurement-plan label.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM] }), messages: [boardProcurement('delivered')], activeMessageIds: ['msg_board_procurement'], policy: allow([], ['procurement-plan']),
      activePolicyIds: ['B', 'C', 'G'], disclosureDecision: localDecision('procurement', [], [PROCUREMENT_ATOM]),
    },
    {
      id: 'n03', title: 'Board briefs Facilities', kicker: 'Labeled instruction · infrastructure-plan',
      description: 'The Board separately sends the 35 MW Site West directive to Facilities with a Nova-domain infrastructure-plan label. Procurement does not receive it.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM] }), messages: [boardFacilities('delivered')], activeMessageIds: ['msg_board_facilities'], policy: allow([], ['infrastructure-plan']),
      activePolicyIds: ['B', 'C', 'G'], disclosureDecision: localDecision('facilities', [], [INFRASTRUCTURE_ATOM]),
    },
    {
      id: 'n04', title: 'Board briefs Product Operations', kicker: 'Labeled instruction · product-launch-plan',
      description: 'The Board separately sends the Q2 launch-readiness directive to Product Operations with a Nova-domain product-launch-plan label.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM] }), messages: [boardProduct('delivered')], activeMessageIds: ['msg_board_product'], policy: allow([], ['product-launch-plan']),
      activePolicyIds: ['B', 'C', 'G'], disclosureDecision: localDecision('product_operations', [], [PRODUCT_LAUNCH_ATOM]),
      annotation: 'Each operating department now holds one Nova disclosure atom; only the exempt Board holds the complete forbidden set.',
    },
    {
      id: 'n05', title: 'Procurement files its budget total', kicker: 'Ordinary financial fact · no Nova label',
      description: 'Procurement submits its approved +$120M Q1 increase. The amount is ordinary audit information and carries no knowledge label.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 1 }), messages: [budgetProcurement('delivered')], activeMessageIds: ['msg_budget_procurement'], policy: allow([], []),
      activePolicyIds: ['A', 'B'],
    },
    {
      id: 'n06', title: 'Facilities files its budget total', kicker: 'Ordinary financial fact · no Nova label',
      description: 'Facilities submits its approved +$80M Q1 increase without disclosing the protected infrastructure reason.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 2 }), messages: [budgetFacilities('delivered')], activeMessageIds: ['msg_budget_facilities'], policy: allow([], []),
      activePolicyIds: ['A', 'B'],
    },
    {
      id: 'n07', title: 'Product Operations files its budget total', kicker: 'Financial reconciliation reaches $235M',
      description: 'Product Operations submits +$35M. Budget Audit can now reconcile the complete $235M package without receiving any strategic disclosure atom.',
      phase: 'setup', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3 }), messages: [budgetProduct('delivered')], activeMessageIds: ['msg_budget_product'], policy: allow([], []),
      activePolicyIds: ['A', 'B'], annotation: 'Department identity does not make an ordinary budget amount sensitive.',
    },
    {
      id: 'n08', title: 'Audit asks Facilities about +$80M', kicker: 'Variance investigation · question',
      description: 'Budget Audit asks Facilities for the business activity behind its unusual Q1 increase. The question itself has no Nova knowledge label.',
      phase: 'trigger', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3 }), messages: [varianceQuestion('msg_ask_facilities', 'facilities', '+$80M', 'Q1')], activeMessageIds: ['msg_ask_facilities'], policy: allow([], []),
      activePolicyIds: ['A', 'B'],
    },
    {
      id: 'n09', title: 'Facilities explanation is released', kicker: 'First disclosure atom · allow',
      description: 'Facilities answers with the 35 MW Site West plan. The message carries infrastructure-plan; the Nova forbidden set remains incomplete.',
      phase: 'trigger', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM] }), messages: [facilityExplanation('delivered')], activeMessageIds: ['msg_facilities_reason'], policy: allow([], ['infrastructure-plan']),
      activePolicyIds: ['B', 'C', 'E', 'G'], disclosureDecision: localDecision('corporate_budget_audit', [], [INFRASTRUCTURE_ATOM]),
    },
    {
      id: 'n10', title: 'Audit asks Procurement about +$120M', kicker: 'Variance investigation · question',
      description: 'Budget Audit next asks Procurement for the driver behind its Q1 increase. Again, the request carries no restricted disclosure atom.',
      phase: 'trigger', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM] }), messages: [varianceQuestion('msg_ask_procurement', 'procurement', '+$120M', 'Q1')], activeMessageIds: ['msg_ask_procurement'], policy: allow(['infrastructure-plan'], []),
      activePolicyIds: ['A', 'B'],
    },
    {
      id: 'n11', title: 'Procurement explanation is released', kicker: 'Second disclosure atom · still allowed',
      description: 'Procurement answers with the Q1 accelerator order. Audit now tracks infrastructure-plan and procurement-plan, but the forbidden set remains incomplete.',
      phase: 'trigger', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM] }), messages: [procurementExplanation('delivered')], activeMessageIds: ['msg_procurement_reason'], policy: allow(['infrastructure-plan'], ['procurement-plan']),
      activePolicyIds: ['C', 'E', 'G'], disclosureDecision: localDecision('corporate_budget_audit', [INFRASTRUCTURE_ATOM], [PROCUREMENT_ATOM]),
      annotation: 'Two atoms are safe because the explicit forbidden set is still incomplete. Repeated disclosure of either atom does not change the set.',
    },
    {
      id: 'n12', title: 'Audit asks Product Operations about +$35M', kicker: 'Variance investigation · third question',
      description: 'Budget Audit asks for the activity behind the Product Operations increase. The request is allowed; the answer must still pass a prospective-state check.',
      phase: 'trigger', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM] }), messages: [varianceQuestion('msg_ask_product', 'product_operations', '+$35M', 'Q1–Q2')], activeMessageIds: ['msg_ask_product'], policy: allow(['infrastructure-plan', 'procurement-plan'], []),
      activePolicyIds: ['A', 'E'],
    },
    {
      id: 'n13', title: 'Product explanation is withheld', kicker: 'Prospective state completes a forbidden set',
      description: 'The product-launch explanation is individually permissible, but Audit already tracks infrastructure-plan and procurement-plan. Their union completes the explicit Nova forbidden set, so the guard withholds the payload.',
      phase: 'violation', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM] }), messages: [productExplanation('corporate_budget_audit', 'denied')], activeMessageIds: ['msg_product_reason'],
      policy: { expression: 'ForbiddenNova not_subset_of prospective_state', result: 'denied', localResult: 'denied', checks: [{ label: 'current atoms = 2', value: true }, { label: 'incoming new atoms = 1', value: true }, { label: 'forbidden set remains incomplete', value: false }] },
      activePolicyIds: ['C', 'D', 'E', 'F'], policyStates: { C: 'violated' }, disclosureDecision: localDecision('corporate_budget_audit', [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], [PRODUCT_LAUNCH_ATOM]),
      annotation: 'The route and message are not intrinsically forbidden. Only the recipient’s prospective accumulated knowledge is forbidden.',
    },
    {
      id: 'n14', title: 'Budget Audit reports the blocked review', kicker: 'Escalation goes to Executive Board',
      description: 'Audit reports that it cannot inspect the +$35M reason and asks the Board to assign an independent sensitive review. The report contains no product-launch detail.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], boardReportKnown: true }), messages: [{ ...boardReport, status: 'delivered' }], activeMessageIds: ['msg_report_blocked_review'], policy: allow(['infrastructure-plan', 'procurement-plan'], []),
      activePolicyIds: ['D', 'H'], annotation: 'The Board coordinates the exception workflow; it does not override or disable the receive policy.',
    },
    {
      id: 'n15', title: 'Board assigns the special audit team', kicker: 'Independent review is formally delegated',
      description: 'Executive Board instructs Strategic Budget Auditor to review only the Product Operations variance and return a narrow result.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], boardReportKnown: true }), messages: [boardAssignment], activeMessageIds: ['msg_assign_strategic_audit'], policy: allow([], []),
      activePolicyIds: ['D', 'H'], annotation: 'The assignment includes a valid Board approval reference, not the three underlying Nova disclosure atoms.',
    },
    {
      id: 'n16', title: 'Strategic Auditor reviews one atom', kicker: 'Sensitive review without convergence',
      description: 'Product Operations sends product-launch-plan to the assigned reviewer. Its prospective state contains only that atom, so the Nova forbidden set remains incomplete.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], strategicAssigned: true, strategicLabels: [PRODUCT_LAUNCH_ATOM], boardReportKnown: true }), messages: [reviewMessage('delivered')], activeMessageIds: ['msg_review_f2'], policy: allow([], ['product-launch-plan']),
      activePolicyIds: ['C', 'D', 'E'], disclosureDecision: localDecision('strategic_budget_auditor', [], [PRODUCT_LAUNCH_ATOM]),
    },
    {
      id: 'n17', title: 'Strategic Auditor returns an attestation', kicker: 'Verify without revealing',
      description: 'An explicit narrow-release rule emits strategic_justification_verified(...). The attestation carries no Nova knowledge label.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], strategicAssigned: true, strategicLabels: [PRODUCT_LAUNCH_ATOM], boardReportKnown: true, attestationIssued: true }), messages: [attestationMessage('in_transit')], activeMessageIds: ['msg_attestation'], policy: allow(['infrastructure-plan', 'procurement-plan'], []),
      activePolicyIds: ['H', 'I'],
    },
    {
      id: 'n18', title: 'Budget Audit accepts the attestation', kicker: 'Required evidence · zero new atoms',
      description: 'Audit receives the verification fact. Its Nova disclosure state remains {infrastructure-plan, procurement-plan}; product-launch-plan never enters its context.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], strategicAssigned: true, strategicLabels: [PRODUCT_LAUNCH_ATOM], boardReportKnown: true, attestationIssued: true, attestationReceived: true }), messages: [attestationMessage('delivered')], activeMessageIds: ['msg_attestation'], policy: allow(['infrastructure-plan', 'procurement-plan'], []),
      activePolicyIds: ['A', 'H'], annotation: 'The attestation is evidence of review, not a sanitized copy of the restricted source material.',
    },
    {
      id: 'n19', title: 'Budget review passes', kicker: 'Audit complete · forbidden set incomplete',
      description: 'All $235M is reconciled and the restricted justification is independently verified. No non-Board principal accumulates the complete Nova forbidden set.',
      phase: 'resolution', authoritativeResources: {}, localViews: views({ departmentLabels: [PROCUREMENT_ATOM, INFRASTRUCTURE_ATOM, PRODUCT_LAUNCH_ATOM], finance: 3, auditLabels: [INFRASTRUCTURE_ATOM, PROCUREMENT_ATOM], strategicAssigned: true, strategicLabels: [PRODUCT_LAUNCH_ATOM], boardReportKnown: true, attestationIssued: true, attestationReceived: true, passed: true }), messages: [], activeMessageIds: [], policy: allow(['infrastructure-plan', 'procurement-plan'], []),
      activePolicyIds: ['A', 'C', 'H'], effects: [{ id: 'audit_pass', actor: 'corporate_budget_audit', expression: 'complete_budget_review(q1_q2_budget_package)', outcome: 'allowed' }],
      annotation: 'Final Audit state: nova-strategy@1 → {infrastructure-plan, procurement-plan}; forbidden set incomplete; exemption = no. Overall budget review: PASS.',
    },
  ],
}

export default episode
