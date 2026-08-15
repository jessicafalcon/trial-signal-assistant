# Airflow (Astro) project

Local-only orchestration for the trial-signal-assistant pipeline —
never run in CI. The one DAG is `dags/trial_safety_pipeline.py`; every
task shells into the repo mount and calls a make target.

How to run it, what each task does, credential scoping, and the
circuit breaker's why: see "Run it on a schedule (Airflow)" in the
[repo README](../README.md). Layout and version choices:
DECISIONS.md 2026-08-15 (Astro entry). Runtime pin: Dockerfile
(Astro Runtime 3.3-2 = Airflow 3.3.0).
