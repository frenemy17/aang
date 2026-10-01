/**
 * Retry scheduler with configurable max retries and exponential backoff.
 */
const { calculateBackoff } = require('../utils/backoff');

class RetryScheduler {
    constructor(options = {}) {
        this.maxRetries = options.maxRetries || 3;
        this.backoffOptions = options.backoff || {};
        this._retryQueue = [];
        this._onRetry = options.onRetry || null;
    }

    shouldRetry(job) {
        // Allow retries while attempts made are less than maxRetries.
        // When attempts equals maxRetries, no further retry should be scheduled.
        return job.attempts < this.maxRetries;
    }

    scheduleRetry(job) {
        if (!this.shouldRetry(job)) {
            return null;
        }

        job.attempts++;
        const delay = calculateBackoff(job.attempts, this.backoffOptions);

        const retryEntry = {
            job,
            delay,
            scheduledAt: Date.now(),
            executeAt: Date.now() + delay
        };

        this._retryQueue.push(retryEntry);

        if (this._onRetry) {
            this._onRetry(retryEntry);
        }

        return retryEntry;
    }

    getPendingRetries() {
        return [...this._retryQueue];
    }

    getReadyRetries(now) {
        const timestamp = now || Date.now();
        return this._retryQueue.filter(entry => entry.executeAt <= timestamp);
    }

    removeRetry(jobId) {
        this._retryQueue = this._retryQueue.filter(entry => entry.job.id !== jobId);
    }

    clear() {
        this._retryQueue = [];
    }
}

module.exports = { RetryScheduler };
