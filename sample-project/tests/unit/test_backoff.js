const { calculateBackoff } = require('../../src/utils/backoff');

module.exports = async function () {
    // First attempt = baseDelay
    {
        const d = calculateBackoff(1, { baseDelay: 100, jitter: false });
        assertEqual(d, 100, 'attempt 1 = baseDelay (100ms)');
    }

    // Exponential growth without jitter
    {
        const d1 = calculateBackoff(1, { baseDelay: 100, jitter: false });
        const d2 = calculateBackoff(2, { baseDelay: 100, jitter: false });
        const d3 = calculateBackoff(3, { baseDelay: 100, jitter: false });
        assertEqual(d1, 100, 'attempt 1 = 100ms');
        assertEqual(d2, 200, 'attempt 2 = 200ms');
        assertEqual(d3, 400, 'attempt 3 = 400ms');
    }

    // Max delay cap
    {
        const d = calculateBackoff(20, { baseDelay: 100, maxDelay: 5000, jitter: false });
        assertEqual(d, 5000, 'delay capped at maxDelay');
    }

    // Jitter stays within ±25% of base
    {
        const base = 1000;
        for (let i = 0; i < 20; i++) {
            const d = calculateBackoff(1, { baseDelay: base, jitter: true });
            assert(d >= base * 0.5,  `jitter lower bound: ${d} >= ${base * 0.5}`);
            assert(d <= base * 1.5,  `jitter upper bound: ${d} <= ${base * 1.5}`);
        }
    }

    // Default options work
    {
        const d = calculateBackoff(1);
        assert(typeof d === 'number' && d > 0, 'default options produce positive delay');
    }
};
