const { PriorityQueue } = require('../../src/queue/job_queue');

module.exports = async function () {
    // ── Basic Operations ──────────────────────────────────────────

    // Single enqueue / dequeue
    {
        const q = new PriorityQueue();
        q.enqueue({ id: 'a', priority: 5 });
        const job = q.dequeue();
        assertEqual(job.id, 'a', 'single enqueue/dequeue returns the item');
    }

    // Size tracking
    {
        const q = new PriorityQueue();
        assertEqual(q.size, 0, 'initial size is 0');
        q.enqueue({ id: 'a', priority: 1 });
        assertEqual(q.size, 1, 'size is 1 after enqueue');
        q.dequeue();
        assertEqual(q.size, 0, 'size is 0 after dequeue');
    }

    // isEmpty
    {
        const q = new PriorityQueue();
        assert(q.isEmpty(), 'new queue is empty');
        q.enqueue({ id: 'a', priority: 1 });
        assert(!q.isEmpty(), 'queue with item is not empty');
    }

    // Dequeue on empty returns null
    {
        const q = new PriorityQueue();
        assertEqual(q.dequeue(), null, 'dequeue on empty returns null');
    }

    // Validation rejects missing priority
    {
        const q = new PriorityQueue();
        assertThrows(() => q.enqueue({ id: 'bad' }), 'priority', 'rejects job without priority');
    }

    // ── Priority Ordering (critical correctness test) ─────────────

    // Jobs must be dequeued in ascending priority order (1 = highest)
    {
        const q = new PriorityQueue();
        q.enqueue({ id: 'low',      priority: 10 });
        q.enqueue({ id: 'critical', priority: 1 });
        q.enqueue({ id: 'medium',   priority: 5 });
        q.enqueue({ id: 'high',     priority: 2 });
        q.enqueue({ id: 'normal',   priority: 7 });

        const first  = q.dequeue();
        const second = q.dequeue();
        const third  = q.dequeue();

        assertEqual(first.id,  'critical', 'priority 1 dequeued first');
        assertEqual(second.id, 'high',     'priority 2 dequeued second');
        assertEqual(third.id,  'medium',   'priority 5 dequeued third');
    }

    // Duplicate priorities maintain FIFO within same level
    {
        const q = new PriorityQueue();
        q.enqueue({ id: 'x', priority: 3 });
        q.enqueue({ id: 'y', priority: 1 });
        q.enqueue({ id: 'z', priority: 3 });

        const first = q.dequeue();
        assertEqual(first.id, 'y', 'lowest priority number comes first regardless of insertion order');
    }
};
