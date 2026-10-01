/**
 * Exponential backoff calculator with optional jitter.
 *
 * @param {number} attempt - Retry attempt number (1-indexed).
 * @param {object} options
 * @param {number} options.baseDelay  - Base delay in ms (default 100).
 * @param {number} options.maxDelay   - Maximum delay cap in ms (default 30000).
 * @param {boolean} options.jitter    - Add random jitter (default true).
 * @returns {number} Delay in milliseconds.
 */
function calculateBackoff(attempt, options = {}) {
    const { baseDelay = 100, maxDelay = 30000, jitter = true } = options;

    const exponentialDelay = baseDelay * Math.pow(2, attempt - 1);
    const cappedDelay = Math.min(exponentialDelay, maxDelay);

    if (jitter) {
        const jitterRange = cappedDelay * 0.5;
        return Math.floor(cappedDelay + (Math.random() * jitterRange - jitterRange / 2));
    }

    return cappedDelay;
}

module.exports = { calculateBackoff };
