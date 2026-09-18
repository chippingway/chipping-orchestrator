# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One dev session per issue, from the first spawn to the PR it hands off.

The owners here divide by the decisions one `implementing` tick makes rather
than by the code those decisions run. `handler` owns the order they are asked
in. `spawn` decides whether anything runs at all -- an awaiting-human tick
belongs to the human's reply, and a worktree that already carries commits is a
publication an earlier tick was interrupted mid-way through.

The locked dev session is four owners because a resume is not one act:
`session_read` says what the pinned state claims the session is and what a
failed run's own text says about its health, `session` decides when it is
retired and gates a fresh spawn against the per-issue daily cap, `resume` keeps
the call shape every other stage wrote against, and `execution` runs one attempt
plus the single poisoned-session retry behind it, in `worktree`'s checkout.

Finished work follows the publication owners: `disposition` compares HEAD
against the pre-agent SHA to tell this run's commit from carried-over work,
`late_gate` measures whatever it is about to publish and holds a candidate
past the size ceiling unpublished under `workflow:decomposing`, `publication`
turns a clean tree into a pushed branch, a PR, and the validating handoff,
`late_candidate_recovery` owns measurement and restored-checkout recovery, and
`late_authorization_recovery` owns commands that must preserve their park until
publication. `late_recovery` routes the three parks that gate takes -- one owed
another reading, one another look at the checkout, and one a decision only an operator
can make -- routing each back through the disposition's own publication seam
ahead of any spawn, since on all three the work is committed already,
`late_rollback` holds that last park across the seam call and puts it back
where the call never returned, `late_authorship` says which comments on its
thread are this stage's own words, and `parks` owns the five ways a
commit-less or unpublishable run stops. The gate
sits inside the disposition rather than beside it because being the ONE seam
all three committed outcomes publish through -- a finished run, a timeout that
committed first, and a branch a crash stranded -- is what makes the
measurement a contract rather than a check.

The publication divides again, because deciding WHEN something happens is not
the same act as deciding what it says. `publication` owns the order alone --
one named commit made durable, then the push, then the pull request, then the
handoff -- while `checkout_guards` owns the proof that the worktree is still
the thing that was measured, asked of the commit AND of the tree on both sides
of the push and parked under the one reason a moved checkout earns, and
`checkout_recovery` owns the answer to that park -- the same two questions
asked silently on every ordinary tick, since what lifts it is the worktree
coming back rather than anything a human could reply; `push_barrier` owns
what may have ENDED between the tick's own readings and the push it is about,
asked immediately before the transport and nowhere else -- a close a poll
latched, and the pull request this push would join, with a `discussion` plan
the humans settled carved out of it, since merging a design is an agreement
rather than a delivery; `dev_pr` owns what that
pull request says and whose work it says it carries, including the reuse that
reads the attribution back off one somebody else opened; `pr_description`
owns the report-aware verdict on such a description, which keeps every word of
it and edits none a developer report may live in, and which no caller asks
yet; and
`handoff` owns the last write and the relabel it goes out ahead of.

`late_gate` is the order its own questions are asked in and nothing else, so
nine owners sit under it: what one gate call is ABOUT and the identity every
refusal is reported under is `late_records`, the pair a count is taken over is
`late_freeze`, what a recovery proves before it acts on a recorded commit is
`late_evidence`, whether the human behind an adjudicated commit is one this
issue can SHOW -- the exemption and the operator authorization asked together,
both held to one commit, with the contribution between the pair that
authorization names re-fingerprinted here, since an exemption is an agent's
verdict and half a bypass alone -- is `late_authority`, what a receipt naming
this stage's own push has to PROVE
before it excuses a candidate from being read -- its own numbered pull
request, open here, on the branch the seam would push, standing on that exact
commit -- is `late_delivery`, what a measured candidate earns -- the push, the
`workflow:decomposing` hold, and the retirement each is durable behind -- is
`late_verdict`, and the one park shape every unreadable reading takes, with
the typed failure both sinks carry and the approval group whose basis says
which owner granted a publication debt, is `late_parks`. The last two are the
park an oversized candidate `late_authority` calls exempt on a record nobody
authorized waits on: `late_consent` takes it, records what an operator's
command authorizes from the gate's own reading, and answers a command it may
not act on, while
`late_command` beside it decides which reply on a standing park a tick should
act on at all -- the last fresh trusted reply, and how far reading it got.

A candidate the remote already carries is the same gate one seam further on,
and eleven more owners divide it the way the seam itself divides: what a call
taken past publication has to freeze before it may measure at all -- the
stage, the pull request, the head it stands on, and the seven refusals that
make freezing them fail closed -- is `late_overflow`; the switch, the record,
and the count asked in one place so the seam that reached the gate makes no
difference to the answer is `late_publication`; the one call every push onto a
pull request the remote already carries goes through -- measure, push named
and leased, spend the debt, prove the checkout again -- is `late_push`, so a
pull request cannot be grown past the ceiling a commit at a time; the push a
human's adjudication already accepted, taken with no measurement but over a
checkout re-proved, is `late_accepted`; the push a squash-on-approval makes
over the branch it just rewrote -- entered on that publication before anything
destructive runs, then measuring the commit the squash MADE, since that is
what would go onto the pull request -- is `late_rewrite`, whether that
rewrite may carry an adjudication's exemption onto the object it produced,
rather than have the same change measured past the same ceiling a second time,
is `late_transfer`, what the receipt of the push that permission licensed does
with it -- carry the exemption over on the same write, or drop a claim the
publication went past -- is `late_rotation`, and the one record a move that
really landed leaves on both sinks, asked past that write so nothing is
reported for a settlement GitHub refused, is `late_transfer_telemetry`; the
reading the dispatcher takes ahead of every handler for a pair this issue
froze and never counted is
`late_reconcile`; whether the work either of its roads would publish onto has
already ENDED -- the issue closed, or its pull request merged or closed, which
the issue's own flag cannot show -- is `late_terminal`, read fail-OPEN there
because what a wrong answer costs is a stranded issue rather than a branch
nothing can put back; the approval that same dispatcher pays ahead of it,
where a crash past the write that granted one left no record to reconcile
from, is `late_debt`; and what a pinned record CLAIMS about either -- and the
claims nothing may act on, since every field here is read fail-closed and a
group missing a member parses as no group -- is `late_claims`. The last five
own the signals that arrive between runs -- a body edit (`drift`), a body edit
before any session existed plus the quiet timeout recovery
(`drift_preflight`), an operator's `/orchestrator continue` (`continue_command`),
the park a spent spawn budget leaves and the one command that lifts it
(`retry_cap`), and a `question` / `discussion` -> `implementing` relabel
(`read_only_relabel`)
-- over the records they hand each other (`models`) and the pinned-state keys
and CLI markers they share (`state`).

The relabel divides again, because screening one is not the same act as
honouring the plan it hands over. `read_only_relabel` owns the screen itself --
which park it answers for, and the acceptance write that retires the
conversation's records -- while what the branch and the checkout are carrying is
`relabel_hazard`, what anything here has grounds to vouch for a tip sitting on
is `relabel_evidence`, and the idempotent park a finding earns, with the
remediation that clears it without destroying work worth keeping, is
`relabel_refusal`. The plan PR under the handoff is two more: `plan_reading`
says what its reviewers left on it and where that puts the checkout, and
`plan_handoff` takes that same reading again every tick until a developer
publishes, since the humans can move the head all through the window the
acceptance opens.

Callers import the owner they need, so this initializer binds nothing: the
dispatcher resolves one handler per issue, and an eager binding here would
charge a park or a session read for the publication path it never reaches.
"""
