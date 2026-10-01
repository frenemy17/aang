/**
 * Test runner — discovers and executes all test modules, reports results.
 */
const path = require('path');

let totalAssertions = 0;
let passedAssertions = 0;
let failedAssertions = 0;
const failures = [];

// ─── Assertion Utilities ────────────────────────────────────────

function assert(condition, message) {
    totalAssertions++;
    if (condition) {
        passedAssertions++;
        process.stdout.write('✓');
    } else {
        failedAssertions++;
        const msg = message || `Assertion #${totalAssertions} failed`;
        failures.push(msg);
        process.stdout.write('✗');
    }
}

function assertEqual(actual, expected, message) {
    const pass = JSON.stringify(actual) === JSON.stringify(expected);
    assert(pass, `${message || 'assertEqual'}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

function assertThrows(fn, expectedSubstring, testName) {
    try {
        fn();
        assert(false, `${testName || 'assertThrows'}: expected error but none was thrown`);
    } catch (e) {
        if (expectedSubstring) {
            assert(
                e.message.includes(expectedSubstring),
                `${testName || 'assertThrows'}: error "${e.message}" does not contain "${expectedSubstring}"`
            );
        } else {
            assert(true);
        }
    }
}

async function assertRejects(fn, expectedSubstring, testName) {
    try {
        await fn();
        assert(false, `${testName || 'assertRejects'}: expected rejection but promise resolved`);
    } catch (e) {
        if (expectedSubstring) {
            assert(
                e.message.includes(expectedSubstring),
                `${testName || 'assertRejects'}: error "${e.message}" does not contain "${expectedSubstring}"`
            );
        } else {
            assert(true);
        }
    }
}

// Expose globally for test modules
global.assert = assert;
global.assertEqual = assertEqual;
global.assertThrows = assertThrows;
global.assertRejects = assertRejects;

// ─── Test Discovery & Execution ─────────────────────────────────

const testFiles = [
    './unit/test_queue',
    './unit/test_store',
    './unit/test_backoff',
    './integration/test_pipeline',
    './integration/test_failure_recovery',
];

async function runAll() {
    console.log('\n══════════════════════════════════════════════════');
    console.log('  Async Job Pipeline — Test Suite');
    console.log('══════════════════════════════════════════════════\n');

    for (const file of testFiles) {
        const label = path.basename(file);
        const beforeTotal = totalAssertions;
        const beforePassed = passedAssertions;
        const beforeFailed = failedAssertions;

        process.stdout.write(`  ${label.padEnd(28)} `);

        try {
            const testModule = require(file);
            if (typeof testModule === 'function') {
                await testModule();
            } else if (testModule && typeof testModule.run === 'function') {
                await testModule.run();
            }
        } catch (e) {
            totalAssertions++;
            failedAssertions++;
            failures.push(`${label}: uncaught error — ${e.message}`);
            process.stdout.write('✗');
        }

        const ran = totalAssertions - beforeTotal;
        const passed = passedAssertions - beforePassed;
        const failed = failedAssertions - beforeFailed;
        const status = failed === 0 ? ' PASS' : ' FAIL';
        console.log(`  ${ran} assertions (${passed} passed, ${failed} failed)${status}`);
    }

    console.log('\n══════════════════════════════════════════════════');
    console.log(`  TOTAL: ${totalAssertions} assertions — ${passedAssertions} passed, ${failedAssertions} failed`);
    console.log('══════════════════════════════════════════════════');

    if (failures.length > 0) {
        console.log('\n  FAILURES:');
        failures.forEach((f, i) => console.log(`    ${i + 1}. ${f}`));
        console.log('');
    }

    process.exit(failedAssertions > 0 ? 1 : 0);
}

runAll().catch(err => {
    console.error('\nTest runner crashed:', err);
    process.exit(1);
});
