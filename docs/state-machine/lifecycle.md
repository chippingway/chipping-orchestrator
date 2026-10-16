# Label lifecycle diagram

The main routes below summarize the handlers. The delivery and conversation references own the detailed decisions,
parks, transactions, and recovery; the [transition graph](../../orchestrator/workflow/transitions.py) defines allowed
label writes. Labels, control labels, and legacy spellings are defined in
[labels and state](labels-and-state.md#workflow-labels).

## Delivery path

```text
(none) ──► workflow:decomposing ──► workflow:ready
              │                         │
              │                         ▼
              │                  workflow:implementing
              │                         │
              │                         ▼
              │                  workflow:validating ◄──────────────┐
              │                    │             │                 │
              │           approved │             │ changes         │
              │                    ▼             ▼                 │
              │           workflow:documenting  workflow:fixing ───┘
              │                    │                 ▲
              │                    ▼                 │ human feedback
              │                 in_review ───────────┘
              │                    │
              │                    └──► done | rejected
              │
              └── split ──► workflow:blocked ──► workflow:ready
                         └► workflow:umbrella ──► done
```

`DECOMPOSE=off` sends new pickup directly to `workflow:implementing`. A blocked parent retains its own implementation;
an umbrella completes through its children. A blocked leaf waits for its dependencies. The orchestrator publishes
pull requests and observes their merge or close decisions; humans merge them.

| Route | Decision | Reference |
|---|---|---|
| Pickup | Initialize a trusted new issue and start decomposition or implementation | [Pickup][pickup] |
| Decomposition | `single` makes the issue ready; `split` creates a family | [Decomposing][decomposing] |
| Blocked family | Release eligible children; make the parent ready after all children finish | [Blocked][blocked] |
| Umbrella | Settle split resources and finish after all children are done | [Umbrella][umbrella] |
| Implementation | Record the report, gate the candidate, publish, and enter validation | [Implementing][implementing] |
| Automated review | Approval proceeds to documenting; change requests enter fixing | [Validating][validating] |
| Final documentation | Complete the head-specific docs pass, then enter human review | [Documenting][documenting] |
| Human review | New feedback enters fixing; stale approval returns to validation | [In review][in-review] |
| Fixing | Deliver feedback and publish the resulting code or report, then revalidate | [Fixing][fixing] |

## Detours and endings

| Situation | Route | Reference |
|---|---|---|
| Above `MAX_ADDED_LINES` | Hold publication; adjudicate under `workflow:decomposing` | [Size gate][size-gate] |
| Late verdict: `single` | Park for operator authorization of the exact commit | [Late verdicts][late-verdicts] |
| Late verdict: `split` | Preserve work, create children, supersede the parent | [Late split][late-split] |
| Rebase conflicts | Enter `workflow:resolving_conflict`, resolve, and revalidate | [Conflicts][conflicts] |
| Requirements change | Re-decompose, resume the developer, or revalidate according to stage | [Content drift][drift] |
| PR merges or closes | Finalize as `done` or `rejected` through terminal checks | [Delivery stages][delivery] |
| Family owner closes | Reconcile cancellation and external resources | [Closed-owner cleanup][cleanup] |
| Cancelled owner loses `rejected` | Start a fresh cycle once cancellation owes nothing | [Restart][restart] |

An authorized oversized candidate returns to implementation if unpublished, or to its recorded source stage for an
existing pull request. Proven workflow rewrites may carry its authorization; descendants and other changed candidates
pass the gate again. The [size-gate reference][size-gate] owns those publication rules.

## Conversation paths

Operators apply `question` and `discussion`; no delivery stage routes into them.

```text
question   ── answer / trusted reply ──► question
           └─ issue closed ───────────► done

discussion ── design round / reply ────► discussion
           └─ confirmed plan PR ──────► merged: done
                                     ► closed unmerged: rejected
```

Question rounds are read-only and open no pull request. Discussion rounds may commit only the confirmed plan file;
the stage publishes it and waits for the plan pull request's verdict. A discussion closed before a plan exists can
finish directly. The [question handler][question] and [discussion handler][discussion] own publication, relabel guards,
and cleanup.

## Waiting for a human

`awaiting_human` is pinned state, not a workflow label. Most parks wait for a trusted reply and then continue the
appropriate conversation. Repairable records and transient failures can instead settle on a later poll; each handler
reference defines what answers its parks.

A spent daily spawn budget (`retry_cap`) in decomposition, late adjudication, or implementation requires a trusted
`/orchestrator continue` to buy one fresh attempt. A spent lifetime ledger (`agent_run_limit`) requires
`/orchestrator add-agent-runs N`; elapsed time and ordinary replies do not replenish it. See the
[retry budget][retry-budget] and [agent-run hold][agent-run-hold] for the command and persistence contracts.

[pickup]: delivery-stages.md#_handle_pickup-no-label--workflowdecomposing-or-workflowimplementing
[decomposing]: delivery-stages.md#_handle_decomposing-label-workflowdecomposing
[blocked]: delivery-stages.md#_handle_blocked-label-workflowblocked
[umbrella]: delivery-stages.md#_handle_umbrella-label-workflowumbrella
[implementing]: delivery-stages.md#_handle_implementing-label-workflowimplementing
[validating]: delivery-stages.md#_handle_validating-label-workflowvalidating
[documenting]: delivery-stages.md#_handle_documenting-label-workflowdocumenting
[in-review]: delivery-stages.md#_handle_in_review-label-in_review
[fixing]: delivery-stages.md#_handle_fixing-label-workflowfixing
[size-gate]: delivery-stages.md#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr
[late-verdicts]: ../workflow/roles.md#what-a-verdict-the-read-cleared-earns
[late-split]: ../workflow/roles.md#what-a-cleared-split-actually-does
[conflicts]: delivery-stages.md#_handle_resolving_conflict-label-workflowresolving_conflict
[drift]: delivery-stages.md#user-content-drift-detection
[delivery]: delivery-stages.md
[cleanup]: delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own
[restart]: ../configuration/operations.md#restarting-an-issue-whose-cycle-was-cancelled
[question]: conversation-stages.md#_handle_question-label-question
[discussion]: conversation-stages.md#_handle_discussion-label-discussion
[retry-budget]: labels-and-state.md#the-retry-budget
[agent-run-hold]: delivery-stages.md#the-agent-run-limit-hold-every-dispatch-ahead-of-every-handler
