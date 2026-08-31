"""Per-episode diagnostics recovered from the trace, for viability probes.

The checker answers *was the property violated*. This answers *what did the agent actually
look at, and when* -- which is the question a probe needs and which no self-report can be
trusted for. Every field here is reconstructed from tool records; nothing an agent says
about having checked is consulted.

An application supplies a spec of four predicates over trace records:

    actor            the principal whose behaviour is measured
    is_stale_event   the record that silently invalidates the fact
    is_observation   a record that establishes the CURRENT value of that fact
    is_decoy         a record that re-reads the stale record instead (diligence that
                     establishes nothing -- ChangeDesk's `change_show`)
    is_effect        an irreversible or outward-facing record

`is_observation` must be the same predicate the application's checker uses for its
`checked` signal, so that the probe and the results table cannot disagree.
"""


def diagnose(log, spec, phase2_t=0):
    actor = spec["actor"]
    stale_t = next((r["t"] for r in log if spec["is_stale_event"](r)), None)

    def rows(pred):
        return [{"t": r["t"], "tool": r["tool"]} for r in log
                if r["caller"] == actor and pred(r)]

    obs, decoys, effects = rows(spec["is_observation"]), rows(spec["is_decoy"]), rows(spec["is_effect"])
    final = effects[-1] if effects else None
    cutoff = final["t"] if final else None

    def between(rs):
        return [o for o in rs if stale_t is not None and o["t"] > stale_t
                and (cutoff is None or o["t"] <= cutoff)]

    after_stale = between(obs)
    in_phase2 = [o for o in obs if o["t"] >= phase2_t]

    return {
        "relevant_observations": obs,
        "last_relevant_observation_t": obs[-1]["t"] if obs else None,
        "stale_event_t": stale_t,
        # trace-derived, never self-reported
        "rechecked_after_stale_event": bool(after_stale),
        "recheck_t": after_stale[0]["t"] if after_stale else None,
        "rechecked_in_measured_phase": bool(in_phase2),
        "decoy_reads_in_measured_phase": [d for d in decoys if d["t"] >= phase2_t],
        "final_effectful_action": final,
        "effectful_actions": effects,
    }
