-- Every completeness measure must be a valid percentage and every
-- partition non-empty (phase-4 review deferral F16, resolved phase 7).
-- pct_withdrawn_or_terminated_with_why_stopped is nullable by design
-- (left join: a partition can hold no stopped trials); the others are
-- computed over count(*) > 0 and must never be null. Runs on both
-- targets — portable SQL only.

select *
from {{ ref('mart_field_completeness') }}
where
    total_studies <= 0
    or pct_with_results is null
    or pct_with_results not between 0 and 100
    or pct_date_precision_day is null
    or pct_date_precision_day not between 0 and 100
    or pct_date_precision_month is null
    or pct_date_precision_month not between 0 and 100
    or pct_date_absent is null
    or pct_date_absent not between 0 and 100
    or (
        pct_withdrawn_or_terminated_with_why_stopped is not null
        and pct_withdrawn_or_terminated_with_why_stopped not between 0 and 100
    )
