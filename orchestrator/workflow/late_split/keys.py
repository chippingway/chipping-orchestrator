# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned keys one late generation owns, spelled once.

Every late field is additive: an issue that never entered the late gate
carries none of them, reads back as an absent generation, and is written back
untouched, so no migration reaches a live issue and an older pinned comment
stays exactly as valid as it was. The key spellings are the compatibility
contract live issues would carry, so they are spelled here and named nowhere
else -- `LATE_STATE_KEYS` is the whole of what one GENERATION owns inside the
pinned comment, and clearing late mode is defined as dropping exactly it.

They sit apart from the round trip that reads and writes them because every
direction needs the same spellings: the reader, the two encoders behind the
write, and the stage that parks on a claim its pinned comment cannot produce
each name a key. A second spelling of one is a field a live issue carries and
this binary never sees.

Two of this domain's other keys are deliberately NOT in the group, and each
for the same reason: it has to survive the clear that ends the generation
which earned it. The commit an accepted candidate publishes under is spelled
on the `exemption` owner, and the pair a cycle's ending leaves behind on the
`endings` owner. This list drops those no more than it drops another stage's
keys.
"""
from __future__ import annotations

CYCLE_ID = "late_cycle_id"
GENERATION = "late_generation"
ROOT_ISSUE = "late_root_issue"
CURRENT_ISSUE = "late_current_issue"
LINEAGE_DEPTH = "late_lineage_depth"
SCOPE = "late_scope"
CANDIDATE_SHA = "late_candidate_sha"
BASE_SHA = "late_base_sha"
THRESHOLD = "late_threshold"
ADDITIONS = "late_additions"
MEASUREMENT_MISS_COUNT = "late_measurement_miss_count"
MEASUREMENT_FAILURE = "late_measurement_failure"
PHASE = "late_phase"
TITLE_BODY_HASH = "late_title_body_hash"
COMMENT_HASH = "late_comment_hash"
COMMENT_WATERMARK_ID = "late_comment_watermark_id"
BASELINE_BOUNDED = "late_baseline_bounded"
PLAN_PR_NUMBER = "late_plan_pr_number"
PLAN_PR_HEAD = "late_plan_pr_head"
PLAN_PR_BODY = "late_plan_pr_body"
POST_PUBLICATION = "late_post_publication"
SOURCE_STAGE = "late_source_stage"
PUBLISHED_PR_NUMBER = "late_published_pr_number"
PUBLISHED_SHA = "late_published_sha"
RESOURCES = "late_resources"
CONSUMERS = "late_consumers"
SPLIT_CHILDREN = "late_split_children"
LINKS_ANNOUNCED = "late_links_announced"
OWED_REPLIES = "late_owed_replies"
OWNER_CHECK_PENDING = "late_owner_check_pending"
CANCELLED = "late_cancelled"
CANCELLED_AT = "late_cancelled_at"
CANCELLED_PHASE = "late_cancelled_phase"
RESTART_PENDING = "late_restart_pending"
RESTART_TARGET = "late_restart_target"
RESTART_CYCLE_ID = "late_restart_cycle_id"
RESTART_PREDECESSOR = "late_restart_predecessor"

SPENDS = "late_spends"

LATE_STATE_KEYS = (
    CYCLE_ID,
    GENERATION,
    ROOT_ISSUE,
    CURRENT_ISSUE,
    LINEAGE_DEPTH,
    SCOPE,
    CANDIDATE_SHA,
    BASE_SHA,
    THRESHOLD,
    ADDITIONS,
    MEASUREMENT_MISS_COUNT,
    MEASUREMENT_FAILURE,
    PHASE,
    TITLE_BODY_HASH,
    COMMENT_HASH,
    COMMENT_WATERMARK_ID,
    BASELINE_BOUNDED,
    PLAN_PR_NUMBER,
    PLAN_PR_HEAD,
    PLAN_PR_BODY,
    POST_PUBLICATION,
    SOURCE_STAGE,
    PUBLISHED_PR_NUMBER,
    PUBLISHED_SHA,
    RESOURCES,
    CONSUMERS,
    SPLIT_CHILDREN,
    LINKS_ANNOUNCED,
    OWED_REPLIES,
    OWNER_CHECK_PENDING,
    CANCELLED,
    CANCELLED_AT,
    CANCELLED_PHASE,
    RESTART_PENDING,
    RESTART_TARGET,
    RESTART_CYCLE_ID,
    RESTART_PREDECESSOR,
    SPENDS,
)
