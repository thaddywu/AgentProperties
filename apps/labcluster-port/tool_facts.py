"""Adaptation code: shared receipt and terminal-result assignments.

Tool-specific Job/Approval/Run updates live beside their original tool actions.
These helpers only record confirmed evidence; they never execute business logic.
"""


def lookup(policy, name, identity):
    return next(row for row in policy.rows(name) if row[0] == identity)


def record_receipt(policy, record):
    policy.put('Receipt', record['id'], record['run_id'], record['job_id'], record['node_id'],
               record['generation'], record['task_hash'], record['source'], record['kind'])
    if record.get('exit_code') == 0:
        policy.put('ExitSuccess', record['id'])
    # Adaptation code: link this receipt to its actual run.
    run_data = next(data for kind, identity, data in policy.rows('RecordData')
                    if kind == 'run' and identity == record['run_id'])
    receipt_data = policy.data.reference('receipt', record['id'])
    policy.put('RecordData', 'receipt', record['id'], receipt_data)
    policy.put('DependsOn', receipt_data, run_data)


def record_terminal(policy, result):
    """Confirm the selected move and record any release/stop evidence."""
    if result.get('code') == 'ALREADY_TERMINAL':
        return
    job = result['job']
    transition = policy.transition
    if not transition or job['state'] != transition['to']:
        raise ValueError('The original tool did not confirm the selected target state.')
    if transition['from'] == 'RUNNING':
        run = lookup(policy, 'Run', job['run_id'])
        node, kind, cores, memory, _, generation = lookup(policy, 'Node', run[2])
        policy.put('Node', node, kind, cores, memory, '', generation)
    if result.get('stop_receipt'):
        record_receipt(policy, result['stop_receipt'])
    policy.put('JobOutcome', job['id'], job['outcome'])
    # Existing ResourceState is changed only by the SDK's confirmed FSM commit.
