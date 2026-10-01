/**
 * Priority-based job queue implemented as a binary min-heap.
 * Jobs with lower priority values are dequeued first (priority 1 = critical).
 */
class PriorityQueue {
    constructor() {
        this._heap = [];
    }

    get size() {
        return this._heap.length;
    }

    isEmpty() {
        return this._heap.length === 0;
    }

    enqueue(job) {
        if (!job || typeof job.priority !== 'number') {
            throw new Error('Job must have a numeric priority field');
        }
        this._heap.push(job);
        this._bubbleUp(this._heap.length - 1);
    }

    dequeue() {
        if (this.isEmpty()) return null;
        const top = this._heap[0];
        const last = this._heap.pop();
        if (this._heap.length > 0) {
            this._heap[0] = last;
            this._sinkDown(0);
        }
        return top;
    }

    peek() {
        return this.isEmpty() ? null : this._heap[0];
    }

    toArray() {
        const result = [];
        const copy = new PriorityQueue();
        copy._heap = [...this._heap];
        while (!copy.isEmpty()) {
            result.push(copy.dequeue());
        }
        return result;
    }

    _bubbleUp(idx) {
        while (idx > 0) {
            const parentIdx = Math.floor((idx - 1) / 2);
            if (this._heap[idx].priority < this._heap[parentIdx].priority) {
                [this._heap[idx], this._heap[parentIdx]] = [this._heap[parentIdx], this._heap[idx]];
                idx = parentIdx;
            } else {
                break;
            }
        }
    }

    _sinkDown(idx) {
        const length = this._heap.length;
        while (true) {
            let target = idx;
            const left = 2 * idx + 1;
            const right = 2 * idx + 2;

            if (left < length && this._heap[left].priority < this._heap[target].priority) {
                target = left;
            }
            if (right < length && this._heap[right].priority < this._heap[target].priority) {
                target = right;
            }

            if (target !== idx) {
                [this._heap[idx], this._heap[target]] = [this._heap[target], this._heap[idx]];
                idx = target;
            } else {
                break;
            }
        }
    }
}

module.exports = { PriorityQueue };
