const { MemoryStore, JOB_STATES } = require('../../src/storage/memory_store');

module.exports = async function () {
    // ── Basic CRUD ────────────────────────────────────────────────

    // Add and retrieve a job
    {
        const store = new MemoryStore();
        const job = store.addJob({ id: 'j1', type: 'email', priority: 1 });
        assertEqual(job.state, JOB_STATES.PENDING, 'new job starts in PENDING');
        assertEqual(store.getJob('j1').id, 'j1', 'getJob retrieves by id');
    }

    // Unknown ID returns null
    {
        const store = new MemoryStore();
        assertEqual(store.getJob('ghost'), null, 'unknown id returns null');
    }

    // Increment attempts
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        store.incrementAttempts('j1');
        store.incrementAttempts('j1');
        assertEqual(store.getJob('j1').attempts, 2, 'attempts incremented twice');
    }

    // getJobsByState filtering
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'a', priority: 1 });
        store.addJob({ id: 'j2', type: 'b', priority: 2 });
        store.transition('j1', JOB_STATES.ACTIVE);
        const pending = store.getJobsByState(JOB_STATES.PENDING);
        assertEqual(pending.length, 1, 'one job remains PENDING');
        assertEqual(pending[0].id, 'j2', 'j2 is the pending job');
    }

    // ── Valid Transitions ─────────────────────────────────────────

    // PENDING → ACTIVE
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        const updated = store.transition('j1', JOB_STATES.ACTIVE);
        assertEqual(updated.state, JOB_STATES.ACTIVE, 'PENDING → ACTIVE succeeds');
    }

    // ACTIVE → COMPLETED
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        store.transition('j1', JOB_STATES.ACTIVE);
        const completed = store.transition('j1', JOB_STATES.COMPLETED);
        assertEqual(completed.state, JOB_STATES.COMPLETED, 'ACTIVE → COMPLETED succeeds');
    }

    // ACTIVE → FAILED (critical failure path)
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        store.transition('j1', JOB_STATES.ACTIVE);
        try {
            const failed = store.transition('j1', JOB_STATES.FAILED);
            assertEqual(failed.state, JOB_STATES.FAILED, 'ACTIVE → FAILED succeeds');
        } catch (e) {
            assert(false, `ACTIVE → FAILED should be valid but threw: ${e.message}`);
        }
    }

    // FAILED → DEAD_LETTER
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        store.transition('j1', JOB_STATES.ACTIVE);
        try {
            store.transition('j1', JOB_STATES.FAILED);
            const dl = store.transition('j1', JOB_STATES.DEAD_LETTER);
            assertEqual(dl.state, JOB_STATES.DEAD_LETTER, 'FAILED → DEAD_LETTER succeeds');
        } catch (e) {
            assert(false, `FAILED → DEAD_LETTER flow failed: ${e.message}`);
        }
    }

    // FAILED → PENDING (re-queue for retry)
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        store.transition('j1', JOB_STATES.ACTIVE);
        try {
            store.transition('j1', JOB_STATES.FAILED);
            const requeued = store.transition('j1', JOB_STATES.PENDING);
            assertEqual(requeued.state, JOB_STATES.PENDING, 'FAILED → PENDING succeeds');
        } catch (e) {
            assert(false, `FAILED → PENDING flow failed: ${e.message}`);
        }
    }

    // ── Invalid Transitions ───────────────────────────────────────

    // PENDING → COMPLETED is invalid
    {
        const store = new MemoryStore();
        store.addJob({ id: 'j1', type: 'x', priority: 1 });
        assertThrows(
            () => store.transition('j1', JOB_STATES.COMPLETED),
            'Invalid transition',
            'PENDING → COMPLETED is rejected'
        );
    }
};
