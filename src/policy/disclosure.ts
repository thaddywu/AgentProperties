import type { CombinationPolicy, KnowledgeLabel } from '../types/episode'

export interface LocalDisclosureState {
  labels: KnowledgeLabel[]
  policyExemptions: string[]
}

export interface CombinationCheck {
  policyId: string
  domainId: string
  currentAtoms: string[]
  incomingAtoms: string[]
  prospectiveAtoms: string[]
  matchedForbiddenSet?: string[]
  exemptionApplied: boolean
  allowed: boolean
  reason: 'safe' | 'exempt' | 'forbidden_combination' | 'unknown_domain' | 'unknown_atom'
}

export interface DisclosureReceiveResult {
  allowed: boolean
  checks: CombinationCheck[]
}

const distinctAtoms = (labels: KnowledgeLabel[], domainId: string) => [
  ...new Set(labels.filter(label => label.domainId === domainId).map(label => label.atomId)),
]

const containsAll = (atoms: string[], candidate: string[]) => candidate.every(atom => atoms.includes(atom))

/**
 * Recipient-local, atomic admission check over semantic disclosure labels.
 * Labels are assumed to be correctly assigned and non-forgeable by this layer.
 */
export function evaluateDisclosureReceive(
  state: LocalDisclosureState,
  incomingLabels: KnowledgeLabel[],
  policies: CombinationPolicy[],
): DisclosureReceiveResult {
  const affectedDomains = [...new Set(incomingLabels.map(label => label.domainId))]
  const checks: CombinationCheck[] = affectedDomains.flatMap((domainId): CombinationCheck[] => {
    const domainPolicies = policies.filter(policy => policy.domainId === domainId)
    const currentAtoms = distinctAtoms(state.labels, domainId)
    const incomingAtoms = distinctAtoms(incomingLabels, domainId)
    const prospectiveAtoms = [...new Set([...currentAtoms, ...incomingAtoms])]

    if (domainPolicies.length === 0) {
      return [{
        policyId: 'unknown', domainId, currentAtoms, incomingAtoms, prospectiveAtoms,
        matchedForbiddenSet: undefined, exemptionApplied: false, allowed: false, reason: 'unknown_domain',
      }]
    }

    const knownAtoms = new Set(domainPolicies.flatMap(policy => policy.forbiddenSets.flat()))
    if (incomingAtoms.some(atom => !knownAtoms.has(atom))) {
      return [{
        policyId: domainPolicies.map(policy => policy.id).join(','), domainId, currentAtoms, incomingAtoms, prospectiveAtoms,
        matchedForbiddenSet: undefined, exemptionApplied: false, allowed: false, reason: 'unknown_atom',
      }]
    }

    return domainPolicies.map(policy => {
      const exemptionApplied = state.policyExemptions.includes(policy.id)
      const matchedForbiddenSet = policy.forbiddenSets.find(set => containsAll(prospectiveAtoms, set))
      const allowed = exemptionApplied || !matchedForbiddenSet
      return {
        policyId: policy.id,
        domainId,
        currentAtoms,
        incomingAtoms,
        prospectiveAtoms,
        matchedForbiddenSet,
        exemptionApplied,
        allowed,
        reason: exemptionApplied ? 'exempt' : matchedForbiddenSet ? 'forbidden_combination' : 'safe',
      }
    })
  })

  return { allowed: checks.every(check => check.allowed), checks }
}
