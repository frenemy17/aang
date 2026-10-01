# Issue #101: Job Pipeline Processing Failures Under Load

## Problem Description

Multiple reports of incorrect behavior in the async job processing pipeline during load testing and production traffic.

### Symptom 1: Priority Inversion
Jobs are not processed in priority order. When multiple jobs with different priorities are enqueued simultaneously, lower-priority jobs (higher priority numbers) are sometimes processed before higher-priority ones. For example, a job with `priority: 10` (low) is executed before a job with `priority: 1` (critical).

### Symptom 2: Worker Pool Exhaustion After Timeouts
After a job times out, subsequent jobs may fail to process or the pool stalls. The worker pool appears to lose available capacity each time a timeout event occurs, eventually reaching zero available workers even though no jobs are actively running. Restarting the service temporarily resolves it.

### Symptom 3: Failed Jobs Stuck in ACTIVE State
When a job handler throws an error, attempting to transition the job to FAILED in the state store throws an `"Invalid transition"` error. Jobs that fail remain permanently stuck in the ACTIVE state, preventing them from being retried or moved to the dead-letter queue. This causes monitoring dashboards to show a growing count of "active" jobs that are actually dead.

### Symptom 4: Retry Count Off by One
The retry scheduler executes one more retry than the configured `maxRetries`. With `maxRetries: 3`, the job is retried 4 times before being moved to the dead-letter queue, causing unnecessary load and delayed failure detection.

## Acceptance Criteria
Run the test suite:
```bash
npm test
```
All tests in `tests/run_all.js` must pass with exit code 0.
