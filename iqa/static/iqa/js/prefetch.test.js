const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function runPrefetch({ images, Image, navigator = {}, responseOk = true }) {
    const attributes = {
        'data-prefetch-url': '/prefetch/',
        'data-prefetch-report-url': '/prefetch-report/',
        'data-prefetch-study': '1',
    };
    const context = {
        Blob: class {
            constructor(parts, options) {
                this.parts = parts;
                this.type = options.type;
            }
        },
        Image,
        Promise,
        document: {
            readyState: 'complete',
            querySelector: () => ({
                getAttribute: (name) => attributes[name],
            }),
        },
        fetch: () => Promise.resolve({
            ok: responseOk,
            json: () => Promise.resolve({ images }),
        }),
        navigator,
    };

    vm.runInNewContext(
        fs.readFileSync(path.join(__dirname, 'prefetch.js'), 'utf8'),
        context,
    );
}

test('warms all 24 images in a complete 8-trial window', async () => {
    let loads = 0;
    class FakeImage {
        set src(value) {
            loads += 1;
            if (this.onload) this.onload();
        }
    }

    runPrefetch({
        images: Array.from({ length: 24 }, (_, i) => `/image/${i}`),
        Image: FakeImage,
    });
    await new Promise(setImmediate);

    assert.equal(loads, 24);
});

test('keeps at most three image requests active', async () => {
    const pending = [];
    let active = 0;
    let maxActive = 0;

    class FakeImage {
        set src(value) {
            active += 1;
            maxActive = Math.max(maxActive, active);
            pending.push(this);
        }
    }

    runPrefetch({
        images: Array.from({ length: 24 }, (_, i) => `/image/${i}`),
        Image: FakeImage,
    });
    await new Promise(setImmediate);

    let completed = 0;
    while (completed < pending.length) {
        const image = pending[completed];
        completed += 1;
        active -= 1;
        image.onload();
    }

    assert.equal(pending.length, 24);
    assert.equal(maxActive, 3);
    assert.equal(active, 0);
});

test('continues after failures and sends one failure report', async () => {
    const pending = [];
    const beacons = [];

    class FakeImage {
        set src(value) {
            pending.push(this);
        }
    }

    runPrefetch({
        images: Array.from({ length: 5 }, (_, i) => `/image/${i}`),
        Image: FakeImage,
        navigator: {
            sendBeacon: (url, blob) => {
                beacons.push({ url, blob });
                return true;
            },
        },
    });
    await new Promise(setImmediate);

    let completed = 0;
    while (completed < pending.length) {
        const image = pending[completed];
        completed += 1;
        if (completed === 1) image.onerror();
        else image.onload();
    }

    assert.equal(pending.length, 5);
    assert.equal(beacons.length, 1);
    assert.equal(beacons[0].url, '/prefetch-report/');
    assert.deepEqual(
        JSON.parse(beacons[0].blob.parts[0]),
        { study: '1', ok: 4, fail: 1 },
    );
});

test('does not load images for a non-OK manifest response', async () => {
    let loads = 0;
    class FakeImage {
        set src(value) {
            loads += 1;
        }
    }

    runPrefetch({
        images: ['/image/0'], Image: FakeImage, responseOk: false,
    });
    await new Promise(setImmediate);

    assert.equal(loads, 0);
});
