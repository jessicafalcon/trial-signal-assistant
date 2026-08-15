{% snapshot snap_trial_status %}

    {{
        config(
            unique_key='nct_id',
            strategy='check',
            check_cols=['overall_status'],
        )
    }}

    {# Input switch. 'live' (default) = stg_trials_current; 'seed' = the
       synthetic day-0 seed (corpus or fixtures variant). Anything else
       is a loud compile-time failure, never a silent fallback. #}
    {% set src = var('snapshot_source', 'live') %}

    {% if src == 'live' %}

        select
            nct_id,
            overall_status,
            snapshot_source
        from {{ ref('stg_trials_current') }}

    {% elif src == 'seed' %}

        {% set scope = var('day0_seed_scope', 'corpus') %}
        {% if scope == 'corpus' %}
            {% set day0_seed = ref('seed_synthetic_day0') %}
        {% elif scope == 'fixtures' %}
            {% set day0_seed = ref('seed_synthetic_day0_fixtures') %}
        {% else %}
            {{ exceptions.raise_compiler_error(
                "day0_seed_scope must be 'corpus' or 'fixtures', got: "
                ~ scope
            ) }}
        {% endif %}

        select
            nct_id,
            overall_status,
            snapshot_source
        from {{ day0_seed }}

    {% else %}

        {{ exceptions.raise_compiler_error(
            "snapshot_source must be 'live' or 'seed', got: " ~ src
        ) }}

    {% endif %}

{% endsnapshot %}
