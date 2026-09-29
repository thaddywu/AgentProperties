export type PrincipalKind = 'signal' | 'utility' | 'authority' | 'contractor' | 'field' | 'board' | 'department' | 'audit'
export type ResourceStatus = 'active' | 'pending' | 'suspended' | 'revoked'
export type MessageStatus = 'sent' | 'in_transit' | 'delivered' | 'denied' | 'historical'
export type PolicyResult = 'satisfied' | 'violated' | 'unknown' | 'denied'

export interface KnowledgeLabel {
  domainId: string
  atomId: string
}

export interface CombinationPolicy {
  id: string
  domainId: string
  forbiddenSets: string[][]
}

export interface Fact {
  predicate: string
  args: string[]
  display: string
  metadata?: FactMetadata
}

export interface FactMetadata {
  issuer?: string
  source?: string
  scope?: string[]
  version?: number | string
  issuedAt?: string
  validUntil?: string
  audience?: string[]
  shareableWith?: string[]
  via?: string[]
  derivedFrom?: string[]
  lifecycle?: ResourceStatus
  knowledgeStatus?: 'current' | 'superseded'
  supersededBy?: string
  authoritative?: boolean
  restrictions?: string[]
  category?: 'financial' | 'restricted' | 'attestation' | 'operational'
}

export interface Resource {
  id: string
  label: string
  status: ResourceStatus
  authority: string
}

export interface Principal {
  id: string
  label: string
  shortLabel: string
  kind: PrincipalKind
  authority: string[]
  position: { x: number; y: number }
}

export interface LocalView {
  resources: Record<string, ResourceStatus>
  establishedKnowledge: Fact[]
  receivedKnowledge: Fact[]
  derivedKnowledge: Fact[]
  disclosureState?: KnowledgeLabel[]
  policyExemptions?: string[]
  note?: string
}

export interface Message {
  id: string
  from: string
  to: string
  label: string
  text: string
  facts: Fact[]
  knowledgeLabels?: KnowledgeLabel[]
  status: MessageStatus
  provenance?: string[]
  metadata?: MessageMetadata
}

export interface MessageMetadata {
  issuer?: string
  scope?: string[]
  version?: number | string
  issuedAt?: string
  validUntil?: string
  supersedes?: string
  audience?: string[]
  shareableWith?: string[]
  via?: string[]
  derivedFrom?: string[]
  restrictions?: string[]
  releaseNote?: string
}

export interface Effect {
  id: string
  actor: string
  expression: string
  outcome: 'allowed' | 'blocked' | 'violation'
}

export interface PolicyCheck {
  label: string
  value: boolean | null
  localValue?: boolean | null
}

export interface PolicyEvaluation {
  expression: string
  result: PolicyResult
  localResult?: PolicyResult
  checks: PolicyCheck[]
}

export interface Policy {
  id: string
  family: 'authorization' | 'lifecycle' | 'information-flow' | 'authority'
  title: string
  text: string
  expression?: string
}

export interface ScenarioRole {
  id: string
  principal: string
  description: string
  responsibleFor: string
}

export interface ScenarioDescription {
  title: string
  summary: string
  operatingModel: string
  roles: ScenarioRole[]
}

export interface DisclosureDecision {
  recipient: string
  policyId: string
  domainId: string
  currentAtoms: string[]
  incomingAtoms: string[]
  prospectiveAtoms: string[]
  matchedForbiddenSet?: string[]
  exemptionApplied: boolean
  result: 'allow' | 'deny'
  messageIndividuallyPermissible: boolean
  routeIndividuallyPermissible: boolean
}

export interface ResearcherDomain {
  id: string
  label: string
  atoms: { id: string; label: string }[]
}

export interface ResearcherViewConfig {
  title: string
  disclaimer: string
  domains: ResearcherDomain[]
}

export interface GraphDomain {
  label: string
  x: number
}

export type PolicyRuleState = 'satisfied' | 'violated' | 'at_risk' | 'not_evaluated'

export interface EpisodeStep {
  id: string
  title: string
  kicker: string
  description: string
  phase: 'setup' | 'trigger' | 'gap' | 'violation' | 'resolution'
  authoritativeResources: Record<string, ResourceStatus>
  localViews: Record<string, LocalView>
  messages: Message[]
  activeMessageIds: string[]
  policy: PolicyEvaluation
  activePolicyIds?: string[]
  policyStates?: Record<string, PolicyRuleState>
  effects?: Effect[]
  annotation?: string
  disclosureDecision?: DisclosureDecision
}

export interface Episode {
  id: string
  title: string
  eyebrow: string
  scenario: ScenarioDescription
  principals: Principal[]
  resources: Resource[]
  policies: Policy[]
  combinationPolicies?: CombinationPolicy[]
  steps: EpisodeStep[]
  graphEdges?: [string, string][]
  graphDomains?: GraphDomain[]
  researcherView?: ResearcherViewConfig
}

export type ComparisonState = 'same' | 'risk' | 'protected' | 'violation'

export interface ComparisonFrame {
  step: EpisodeStep
  state: ComparisonState
  caption: string
}

export interface ComparisonBeat {
  id: string
  title: string
  kicker: string
  description: string
  withoutLabels: ComparisonFrame
  withLabels: ComparisonFrame
}

export interface EpisodeComparison {
  id: string
  episode: Episode
  labelFormat: string
  labelDescription: string
  withoutLabelsSummary: string
  withLabelsSummary: string
  beats: ComparisonBeat[]
}
