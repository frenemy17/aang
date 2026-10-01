const { WorkerPool } = require('../../src/workers/worker_pool');
const { MemoryStore, JOB_STATES } = require('../../src/storage/memory_store');
const { RetryScheduler } = require('../../src/scheduler/retry_scheduler');

module.exports = async function () {
    // ── Failed job transitions to FAILED state ────────────────────

    {
        const store = new MemoryStore();
        const pool = new WorkerPool({ concurrency: 2, timeout: 2000 });

        pool.registerHandler('fail_task', async () => {
            throw new Error('Simulated handler failure');
        });

        const job = { id: 'f1', type: 'fail_task', priority: 1 };
        store.addJob(job);
        store.transition('f1', JOB_STATES.ACTIVE);

        try { await pool.executeJob(job); } catch (e) { /* expected */ }

        try {
            store.transition('f1', JOB_STATES.FAILED);
            assertEqual(store.getJob('f1').state, JOB_STATES.FAILED, 'failure: job reaches FAILED');
        } catch (e) {
            assert(false, `failure: ACTIVE → FAILED should be valid but threw: ${e.message}`);
        }
    }

    // ── Worker pool recovers after handler error ──────────────────

    {
        const pool = new WorkerPool({ concurrency: 2, timeout: 2000 });

        pool.registerHandler('fail_task', async () => { throw new Error('boom'); });
        pool.registerHandler('ok_task', async () => ({ ok: true }));

        try { await pool.executeJob({ id: 'e1', type: 'fail_task', priority: 1 }); } catch (e) { /* expected */ }

        assertEqual(pool.getActiveCount(), 0, 'failure: worker released after handler error');

        const result = await pool.executeJob({ id: 's1', type: 'ok_task', priority: 1 });
        assertEqual(result.ok, true, 'failure: pool processes next job after error');
    }

    // ── Timeout releases worker slot ──────────────────────────────

    {
        const pool = new WorkerPool({ concurrency: 1, timeout: 50 });

        pool.registerHandler('hang', () => {
            return new Promise(() => {}); // intentionally never resolves
        });

        try {
            await pool.executeJob({ id: 't1', type: 'hang', priority: 1 });
        } catch (e) {
            // expected timeout rejection
        }

        await new Promise(r => setTimeout(r, 30));

        assertEqual(pool.getActiveCount(), 0, 'timeout: worker slot released after timeout');
        assert(pool.hasCapacity(), 'timeout: pool has capacity after timeout');
    }

    // ── Retry scheduler respects maxRetries exactly ───────────────

    {
        const scheduler = new RetryScheduler({
            maxRetries: 3,
            backoff: { baseDelay: 10, jitter: false }
        });
        const job = { id: 'r1', attempts: 0 };

        let retryCount = 0;
        while (scheduler.shouldRetry(job)) {
            scheduler.scheduleRetry(job);
            retryCount++;
        }

        assertEqual(retryCount, 3, `retry: expected exactly 3 retries, got ${retryCount}`);
        assertEqual(job.attempts, 3, `retry: attempts should be 3, got ${job.attempts}`);
    }

    // ── Full failure → retry → dead-letter lifecycle ──────────────

    {
        const store = new MemoryStore();
        const scheduler = new RetryScheduler({ maxRetries: 2, backoff: { baseDelay: 10, jitter: false } });

        const job = { id: 'dl1', type: 'flaky', priority: 1, attempts: 0 };
        store.addJob(job);

        // First attempt fails: PENDING → ACTIVE → FAILED
        store.transition('dl1', JOB_STATES.ACTIVE);
        try {
            store.transition('dl1', JOB_STATES.FAILED);
        } catch (e) {
            assert(false, `dead_letter: first ACTIVE → FAILED threw: ${e.message}`);
            return;
        }
        scheduler.scheduleRetry(store.getJob('dl1'));

        // Retry 1: FAILED → PENDING → ACTIVE → FAILED
        store.transition('dl1', JOB_STATES.PENDING);
        store.transition('dl1', JOB_STATES.ACTIVE);
        try {
            store.transition('dl1', JOB_STATES.FAILED);
        } catch (e) {
            assert(false, `dead_letter: second ACTIVE → FAILED threw: ${e.message}`);
            return;
        }
        scheduler.scheduleRetry(store.getJob('dl1'));

        // Retries exhausted → DEAD_LETTER
        assert(!scheduler.shouldRetry(store.getJob('dl1')), 'dead_letter: no retries remaining');
        store.transition('dl1', JOB_STATES.DEAD_LETTER);
        assertEqual(store.getJob('dl1').state, JOB_STATES.DEAD_LETTER, 'dead_letter: job reaches DEAD_LETTER');
    }
};
