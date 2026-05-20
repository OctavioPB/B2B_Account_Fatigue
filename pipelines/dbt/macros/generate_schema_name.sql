{% macro generate_schema_name(custom_schema_name, node) -%}

    {#-
        Custom schema name generator for harmoni.

        Default dbt behaviour: <target_schema>_<custom_schema_name>
        harmoni behaviour:     <custom_schema_name> (ignores target schema prefix)

        This ensures our schema names (staging, intermediate, snapshots, marts)
        are consistent across dev, staging, and prod targets regardless of the
        default schema configured in profiles.yml.

        Exception: when custom_schema_name is not set, fall back to the target
        schema (standard dbt behaviour).
    -#}

    {%- set default_schema = target.schema -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}

    {%- else -%}
        {{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
