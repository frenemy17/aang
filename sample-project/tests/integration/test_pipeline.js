const { PriorityQueue } = require('../../src/queue/job_queue');
const { WorkerPool } = require('../../src/workers/worker_pool');
const { MemoryStore, JOB_STATES } = require('../../src/storage/memory_store');

module.exports = async function () {
    // ── End-to-end successful job processing ──────────────────────

    {
        const store = new MemoryStore();
        const pool = new WorkerPool({ concurrency: 2, timeout: 2000 });
        const queue = new PriorityQueue();

        pool.registerHandler('compute', async (job) => {
            return { value: job.data.x * 2 };
        });

        const jobData = { id: 'p1', type: 'compute', priority: 1, data: { x: 21 } };
        store.addJob(jobData);
        queue.enqueue(jobData);

        store.transition('p1', JOB_STATES.ACTIVE);
        const dequeued = queue.dequeue();
        const result = await pool.executeJob(dequeued);

        store.setResult('p1', result);
        store.transition('p1', JOB_STATES.COMPLETED);

        assertEqual(store.getJob('p1').state, JOB_STATES.COMPLETED, 'pipeline: job reaches COMPLETED');
        assertEqual(store.getJob('p1').result.value, 42, 'pipeline: result is correct');
        assertEqual(pool.getActiveCount(), 0, 'pipeline: worker released after success');
    }

    // ── Priority ordering across pipeline ─────────────────────────

    {
        const queue = new PriorityQueue();
        const pool = new WorkerPool({ concurrency: 1, timeout: 2000 });
        const processed = [];

        pool.registerHandler('log', async (job) => {
            processed.push(job.id);
            return { logged: true };
        });

        queue.enqueue({ id: 'low',      type: 'log', priority: 10 });
        queue.enqueue({ id: 'critical', type: 'log', priority: 1 });
        queue.enqueue({ id: 'medium',   type: 'log', priority: 5 });

        while (!queue.isEmpty()) {
            const job = queue.dequeue();
            await pool.executeJob(job);
        }

        assertEqual(processed[0], 'critical', 'pipeline: critical job processed first');
        assertEqual(processed[1], 'medium',   'pipeline: medium job processed second');
        assertEqual(processed[2], 'low',      'pipeline: low priority job processed last');
    }

    // ── Worker capacity after sequential jobs ─────────────────────

    {
        const pool = new WorkerPool({ concurrency: 2, timeout: 2000 });
        pool.registerHandler('noop', async () => ({ done: true }));

        await pool.executeJob({ id: 'w1', type: 'noop', priority: 1 });
        await pool.executeJob({ id: 'w2', type: 'noop', priority: 1 });
        await pool.executeJob({ id: 'w3', type: 'noop', priority: 1 });

        assertEqual(pool.getActiveCount(), 0, 'pipeline: all workers released after sequential jobs');
    }
};
