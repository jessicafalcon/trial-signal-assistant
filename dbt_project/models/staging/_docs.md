# Shared column descriptions (dbt doc blocks)

One definition per column that appears in both staging models;
schema.yml references them with {{ doc('...') }} so the two copies can
never drift (phase-3 review residual, resolved in phase 7). Columns
whose meaning differs per model (nct_id, ingest_date, snapshot_source)
keep inline descriptions in schema.yml.

{% docs trial_brief_title %}
Short public title of the study.
{% enddocs %}

{% docs trial_overall_status %}
Recruitment/lifecycle status as reported by the API. Values enumerated
from the 2026-08-14 corpus (1,738 AD studies).
{% enddocs %}

{% docs trial_phase %}
Trial phase(s) joined with "/" (e.g. PHASE1/PHASE2); "NA" means not
applicable; null when absent.
{% enddocs %}

{% docs trial_sponsor_name %}
Lead sponsor name.
{% enddocs %}

{% docs trial_conditions %}
List of condition strings; empty list when absent. data_type is
duckdb's; on the snowflake target this column is ARRAY (COPY from
parquet) — the one deliberate type divergence.
{% enddocs %}

{% docs trial_interventions %}
List of intervention names; empty list when absent. data_type is
duckdb's; ARRAY on the snowflake target (see conditions).
{% enddocs %}

{% docs trial_start_date_raw %}
Start date exactly as the API sent it; null if absent.
{% enddocs %}

{% docs trial_start_date %}
Normalized start date (month precision resolves to first of month);
null when absent or unparseable.
{% enddocs %}

{% docs trial_date_precision %}
Precision of start_date_raw — "day" or "month"; null when the date is
absent or in an unrecognized format.
{% enddocs %}

{% docs trial_why_stopped %}
Free-text stop reason; present only on some withdrawn/terminated
trials.
{% enddocs %}

{% docs trial_brief_summary %}
descriptionModule.briefSummary — short free-text study summary; null
when the module or field is absent.
{% enddocs %}

{% docs trial_detailed_description %}
descriptionModule.detailedDescription — longer free-text description;
absent on many studies, null then.
{% enddocs %}

{% docs trial_has_results %}
Whether the registry has posted results.
{% enddocs %}
