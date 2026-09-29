import budgetCompartmentEpisode from './budget-compartment/episode'
import type { Episode, EpisodeComparison, EpisodeStep, Fact, Message } from '../src/types/episode'

const copyStep = (step: EpisodeStep): EpisodeStep => ({
  ...step,
  authoritativeResources: { ...step.authoritativeResources },
  localViews: Object.fromEntries(Object.entries(step.localViews).map(([id, view]) => [id, {
    ...view,
    resources: { ...view.resources },
    establishedKnowledge: [...view.establishedKnowledge],
    receivedKnowledge: [...view.receivedKnowledge],
    derivedKnowledge: [...view.derivedKnowledge],
    disclosureState: view.disclosureState ? [...view.disclosureState] : undefined,
    policyExemptions: view.policyExemptions ? [...view.policyExemptions] : undefined,
  }])),
  messages: step.messages.map(message => ({
    ...message,
    facts: [...message.facts],
    knowledgeLabels: message.knowledgeLabels ? [...message.knowledgeLabels] : undefined,
    metadata: message.metadata ? { ...message.metadata } : undefined,
    provenance: message.provenance ? [...message.provenance] : undefined,
  })),
  activeMessageIds: [...step.activeMessageIds],
  policy: { ...step.policy, checks: step.policy.checks.map(check => ({ ...check })) },
  activePolicyIds: step.activePolicyIds ? [...step.activePolicyIds] : undefined,
  policyStates: step.policyStates ? { ...step.policyStates } : undefined,
  effects: step.effects?.map(effect => ({ ...effect })),
  disclosureDecision: step.disclosureDecision ? {
    ...step.disclosureDecision,
    currentAtoms: [...step.disclosureDecision.currentAtoms],
    incomingAtoms: [...step.disclosureDecision.incomingAtoms],
    prospectiveAtoms: [...step.disclosureDecision.prospectiveAtoms],
    matchedForbiddenSet: step.disclosureDecision.matchedForbiddenSet ? [...step.disclosureDecision.matchedForbiddenSet] : undefined,
  } : undefined,
})

const stepAt = (episode: Episode, id: string) => {
  const step = episode.steps.find(item => item.id === id)
  if (!step) throw new Error(`Comparison step not found: ${episode.id}/${id}`)
  return copyStep(step)
}

function withoutKnowledgeLabels(stepId: string): EpisodeStep {
  const step = stepAt(budgetCompartmentEpisode, stepId)
  step.localViews = Object.fromEntries(Object.entries(step.localViews).map(([id, view]) => [id, {
    ...view,
    disclosureState: undefined,
    policyExemptions: undefined,
  }]))
  step.messages = step.messages.map(message => ({
    ...message,
    knowledgeLabels: [],
    metadata: message.metadata ? {
      ...message.metadata,
      releaseNote: 'Delivered as ordinary business content; no knowledge labels are present.',
    } : undefined,
  }))
  step.disclosureDecision = undefined
  step.activePolicyIds = ['A', 'B']
  return step
}

const reconstructedStrategy: Fact = {
  predicate: 'strategy_reconstructed',
  args: ['project_nova', 'corporate_budget_audit'],
  display: 'Project Nova strategy reconstructed from all three disclosure atoms',
  metadata: { category: 'restricted', knowledgeStatus: 'current', source: 'local_reasoning' },
}

const unlabeledThird = withoutKnowledgeLabels('n13')
const unlabeledProductMessage = unlabeledThird.messages.find(message => message.id === 'msg_product_reason') as Message
unlabeledProductMessage.status = 'delivered'
unlabeledProductMessage.metadata = {
  ...unlabeledProductMessage.metadata,
  releaseNote: 'Delivered: without a product-launch-plan label, the recipient guard sees no combinational risk.',
}
const auditView = unlabeledThird.localViews.corporate_budget_audit
auditView.receivedKnowledge = [...auditView.receivedKnowledge, ...unlabeledProductMessage.facts]
auditView.derivedKnowledge = [...auditView.derivedKnowledge, reconstructedStrategy]
auditView.note = 'All three strategic explanations arrived as ordinary content; no local disclosure-label state existed to detect their forbidden combination.'
unlabeledThird.title = 'Third explanation is delivered'
unlabeledThird.kicker = 'No label · no prospective combination check'
unlabeledThird.description = 'Product Operations sends the final explanation as ordinary content. Audit receives the product-launch component in addition to the two explanations it already holds.'
unlabeledThird.policy = {
  expression: 'may_receive(message) without knowledge labels', result: 'violated', localResult: 'satisfied',
  checks: [
    { label: 'sender-recipient route allowed', value: true, localValue: true },
    { label: 'message individually ordinary', value: true, localValue: true },
    { label: 'forbidden combination detectable', value: false, localValue: null },
  ],
}
unlabeledThird.effects = [{ id: 'nova_reconstructed', actor: 'corporate_budget_audit', expression: 'reconstruct_strategy(all three disclosure atoms)', outcome: 'violation' }]
unlabeledThird.annotation = 'Every message looked permissible in isolation; the missing knowledge labels hid the forbidden aggregate state.'

const labeledThird = stepAt(budgetCompartmentEpisode, 'n13')
labeledThird.phase = 'resolution'
labeledThird.kicker = 'Label present · prospective state denied'

const unlabeledBudgetOutcome = copyStep(unlabeledThird)
unlabeledBudgetOutcome.id = 'n13-outcome'
unlabeledBudgetOutcome.title = 'Audit now knows the complete strategy'
unlabeledBudgetOutcome.kicker = 'Irreversible knowledge convergence'
unlabeledBudgetOutcome.description = 'Audit can reconcile the budget, but it has also reconstructed the protected Project Nova plan. A later warning cannot remove that knowledge.'
unlabeledBudgetOutcome.messages = unlabeledBudgetOutcome.messages.map(message => ({ ...message, status: 'historical' }))
unlabeledBudgetOutcome.activeMessageIds = []

const labeledReview = stepAt(budgetCompartmentEpisode, 'n16')
labeledReview.phase = 'resolution'
const labeledAuditPass = stepAt(budgetCompartmentEpisode, 'n19')

export const budgetComparison: EpisodeComparison = {
  id: budgetCompartmentEpisode.id,
  episode: budgetCompartmentEpisode,
  labelFormat: 'nova-strategy@1 / disclosure atom',
  labelDescription: 'Content-specific knowledge labels let each recipient guard test explicit forbidden sets against its prospective tracked disclosure state.',
  withoutLabelsSummary: 'Each explanation looks harmless alone, so all three disclosure atoms reach Budget Audit and collectively reveal the protected strategy.',
  withLabelsSummary: 'The first two atoms are allowed; the third is withheld and reviewed independently, returning only a narrow attestation.',
  beats: [
    {
      id: 'b-finance', title: 'Ordinary audit data remains available', kicker: 'Labels do not block the business workflow',
      description: 'Budget Audit receives all three approved amounts and reconciles the same $235M total in both branches.',
      withoutLabels: { step: withoutKnowledgeLabels('n07'), state: 'same', caption: 'All ordinary financial totals arrive.' },
      withLabels: { step: stepAt(budgetCompartmentEpisode, 'n07'), state: 'same', caption: 'All ordinary financial totals arrive.' },
    },
    {
      id: 'b-first', title: 'Facilities explains the first variance', kicker: 'One strategic component',
      description: 'The business explanation is identical. Only the protected branch labels its semantic disclosure atom as infrastructure-plan.',
      withoutLabels: { step: withoutKnowledgeLabels('n09'), state: 'risk', caption: 'Audit receives the explanation with no tracked label state.' },
      withLabels: { step: stepAt(budgetCompartmentEpisode, 'n09'), state: 'protected', caption: 'Allowed: the forbidden set remains incomplete.' },
    },
    {
      id: 'b-second', title: 'Procurement explains the second variance', kicker: 'Two components can coexist',
      description: 'Both branches release the second explanation. The protected branch records a prospective count of two.',
      withoutLabels: { step: withoutKnowledgeLabels('n11'), state: 'risk', caption: 'Audit receives another untracked component.' },
      withLabels: { step: stepAt(budgetCompartmentEpisode, 'n11'), state: 'protected', caption: 'Allowed: two of three forbidden-set atoms are present.' },
    },
    {
      id: 'b-third', title: 'Product Operations sends the third explanation', kicker: 'The decisive receive check',
      description: 'A route-only decision permits the message. A label-aware decision sees that product-launch-plan would complete the explicit forbidden set.',
      withoutLabels: { step: unlabeledThird, state: 'violation', caption: 'Delivered: Audit now holds all three components.' },
      withLabels: { step: labeledThird, state: 'protected', caption: 'Withheld: prospective state contains the forbidden set.' },
    },
    {
      id: 'b-review', title: 'The required review still happens', kicker: 'Exposure versus separated duties',
      description: 'The labeled workflow sends only product-launch-plan to an independent reviewer. The unlabeled branch has already exposed the complete strategy to ordinary Audit.',
      withoutLabels: { step: unlabeledBudgetOutcome, state: 'violation', caption: 'The forbidden knowledge state is irreversible.' },
      withLabels: { step: labeledReview, state: 'protected', caption: 'Strategic Auditor reviews only product-launch-plan.' },
    },
    {
      id: 'b-outcome', title: 'Budget audit outcome', kicker: 'Same audit coverage · different disclosure',
      description: 'Both workflows can account for $235M. Only the labeled workflow completes without concentrating the full Nova forbidden set in one non-Board principal.',
      withoutLabels: { step: unlabeledBudgetOutcome, state: 'violation', caption: 'Audit complete, but confidentiality policy is violated.' },
      withLabels: { step: labeledAuditPass, state: 'protected', caption: 'Audit passes with two atoms and a narrow attestation.' },
    },
  ],
}
