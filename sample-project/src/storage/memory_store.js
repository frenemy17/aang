/**
 * In-memory job state store with enforced state machine transitions.
 *
 * Valid lifecycle:
 *   PENDING → ACTIVE → COMPLETED
 *                    → FAILED → PENDING (retry)
 *                             → DEAD_LETTER (exhausted retries)
 */

const JOB_STATES = {
    PENDING: 'PENDING',
    ACTIVE: 'ACTIVE',
    COMPLETED: 'COMPLETED',
    FAILED: 'FAILED',
    DEAD_LETTER: 'DEAD_LETTER'
};

const VALID_TRANSITIONS = {
    [JOB_STATES.PENDING]:   [JOB_STATES.ACTIVE],
    [JOB_STATES.ACTIVE]:    [JOB_STATES.COMPLETED, JOB_STATES.FAILED],
    [JOB_STATES.FAILED]:    [JOB_STATES.PENDING, JOB_STATES.DEAD_LETTER],
};

class MemoryStore {
    constructor() {
        this._jobs = new Map();
    }

    addJob(job) {
        const record = {
            ...job,
            state: JOB_STATES.PENDING,
            attempts: 0,
            createdAt: Date.now(),
            updatedAt: Date.now(),
            result: null,
            error: null
        };
        this._jobs.set(job.id, record);
        return record;
    }

    getJob(jobId) {
        return this._jobs.get(jobId) || null;
    }

    transition(jobId, newState) {
        const job = this._jobs.get(jobId);
        if (!job) {
            throw new Error(`Job ${jobId} not found`);
        }

        const allowed = VALID_TRANSITIONS[job.state];
        if (!allowed || !allowed.includes(newState)) {
            throw new Error(`Invalid transition: ${job.state} → ${newState} for job ${jobId}`);
        }

        job.state = newState;
        job.updatedAt = Date.now();
        return job;
    }

    setResult(jobId, result) {
        const job = this._jobs.get(jobId);
        if (job) {
            job.result = result;
            job.updatedAt = Date.now();
        }
        return job;
    }

    setError(jobId, error) {
        const job = this._jobs.get(jobId);
        if (job) {
            job.error = typeof error === 'string' ? error : error.message;
            job.updatedAt = Date.now();
        }
        return job;
    }

    incrementAttempts(jobId) {
        const job = this._jobs.get(jobId);
        if (job) {
            job.attempts++;
            job.updatedAt = Date.now();
        }
        return job;
    }

    getJobsByState(state) {
        return [...this._jobs.values()].filter(j => j.state === state);
    }

    getAllJobs() {
        return [...this._jobs.values()];
    }

    clear() {
        this._jobs.clear();
    }
}

module.exports = { MemoryStore, JOB_STATES, VALID_TRANSITIONS };
