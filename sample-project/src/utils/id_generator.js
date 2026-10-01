/**
 * Unique job ID generator using timestamp and monotonic counter.
 */

let counter = 0;

function generateJobId(prefix = 'job') {
    counter++;
    return `${prefix}_${Date.now()}_${counter}`;
}

function resetCounter() {
    counter = 0;
}

module.exports = { generateJobId, resetCounter };
