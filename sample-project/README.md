# Async Job Pipeline

A Node.js background job processing system with priority scheduling, concurrent worker pools, retry logic with exponential backoff, and dead-letter queue support.

## Architecture

```
src/
├── queue/
│   └── job_queue.js          # Priority min-heap job queue
├── workers/
│   └── worker_pool.js        # Concurrent worker pool with timeout support
├── storage/
│   └── memory_store.js       # In-memory job state machine
├── scheduler/
│   └── retry_scheduler.js    # Retry scheduling with exponential backoff
└── utils/
    ├── backoff.js            # Exponential backoff calculator with jitter
    └── id_generator.js       # Unique job ID generator
```

## Job States

```
PENDING → ACTIVE → COMPLETED
                 → FAILED → PENDING (retry)
                          → DEAD_LETTER (exhausted retries)
```

## Running Tests

```bash
npm test
```
