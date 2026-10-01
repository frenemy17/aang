/**
 * Concurrent worker pool with configurable concurrency limits and timeout.
 */
class WorkerPool {
    constructor(options = {}) {
        this.concurrency = options.concurrency || 4;
        this.timeout = options.timeout || 5000;
        this.activeCount = 0;
        this._handlers = new Map();
    }

    registerHandler(jobType, handler) {
        this._handlers.set(jobType, handler);
    }

    getHandler(jobType) {
        return this._handlers.get(jobType) || null;
    }

    hasCapacity() {
        return this.activeCount < this.concurrency;
    }

    getActiveCount() {
        return this.activeCount;
    }

    acquireWorker() {
        if (!this.hasCapacity()) {
            throw new Error('No available workers — pool exhausted');
        }
        this.activeCount++;
    }

    releaseWorker() {
        if (this.activeCount > 0) {
            this.activeCount--;
        }
    }

    async executeJob(job) {
        const handler = this._handlers.get(job.type);
        if (!handler) {
            throw new Error(`No handler registered for job type: ${job.type}`);
        }

        this.acquireWorker();
        let settled = false;

        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                if (!settled) {
                    settled = true;
                    // Release the worker slot on timeout before rejecting
                    this.releaseWorker();
                    reject(new Error(`Job ${job.id} timed out after ${this.timeout}ms`));
                }
            }, this.timeout);

            Promise.resolve(handler(job))
                .then(result => {
                    if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        this.releaseWorker();
                        resolve(result);
                    }
                })
                .catch(err => {
                    if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        this.releaseWorker();
                        reject(err);
                    }
                });
        });
    }
}

module.exports = { WorkerPool };
