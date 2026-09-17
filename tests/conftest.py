import os

# Set at collection time, before any test module imports langfuse, so a developer
# with LANGFUSE_* exported in their shell can never emit real traces from a test run.
os.environ["LANGFUSE_TRACING_ENABLED"] = "False"
