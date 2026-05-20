{% macro meta_required(model) %}

    {#-
        Validates that a model's meta block contains the required keys.
        Called in CI via: dbt run-operation meta_required --args '{model: stg_accounts}'

        Required keys: owner, source, refresh_cadence
        Raises a compilation error if any are missing.
    -#}

    {%- set required_keys = ['owner', 'source', 'refresh_cadence'] -%}
    {%- set node = graph.nodes.get('model.' ~ project_name ~ '.' ~ model) -%}

    {%- if node is none -%}
        {{ exceptions.raise_compiler_error("Model '" ~ model ~ "' not found in graph.") }}
    {%- endif -%}

    {%- set meta = node.config.get('meta', {}) -%}

    {%- for key in required_keys -%}
        {%- if key not in meta -%}
            {{ exceptions.raise_compiler_error(
                "Model '" ~ model ~ "' is missing required meta key: '" ~ key ~ "'. "
                ~ "Add meta: { " ~ key ~ ": '...' } to the model config."
            ) }}
        {%- endif -%}
    {%- endfor -%}

    {{ log("meta_required: model '" ~ model ~ "' passed all meta checks.", info=True) }}

{% endmacro %}
