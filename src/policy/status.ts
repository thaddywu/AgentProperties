import type { MessageStatus, PolicyResult, ResourceStatus } from '../types/episode'

export const statusLabel: Record<ResourceStatus, string> = {
  active: 'Active', pending: 'Pending', suspended: 'Suspended', revoked: 'Revoked',
}

export const policyLabel: Record<PolicyResult, string> = {
  satisfied: 'Satisfied', violated: 'Violated', unknown: 'Insufficient evidence', denied: 'Denied',
}

export const messageLabel: Record<MessageStatus, string> = {
  sent: 'Sent', in_transit: 'In transit', delivered: 'Delivered', denied: 'Denied', historical: 'Historical',
}
