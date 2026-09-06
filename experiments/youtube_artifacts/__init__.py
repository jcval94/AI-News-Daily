"""Ephemeral YouTube-download experiment.

Nothing in this package is imported by the production pipeline. The experiment
exists only to measure whether a GitHub-hosted runner can materialize a small,
rights-curated set of YouTube clips and retain them as a workflow artifact.
"""

EXPECTED_CATALOG_SIZE = 10
EXPERIMENT_NAME = "youtube-artifact-download"
