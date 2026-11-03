"use strict";

const test = require("node:test");
const assert = require("node:assert");
const { tokenPath, localIso, buildEvent, makeThrottle } = require("./tracker_logic.js");

test("token path uses CODETIME_HOME when set", () => {
    assert.strictEqual(tokenPath({ CODETIME_HOME: "/tmp/x" }, "/home/u"), "/tmp/x/token");
});

test("token path defaults to ~/.codetime", () => {
    assert.strictEqual(tokenPath({}, "/home/u"), "/home/u/.codetime/token");
});

test("localIso has no time zone and pads numbers", () => {
    assert.strictEqual(localIso(new Date(2026, 10, 3, 9, 5, 7)), "2026-11-03T09:05:07");
});

test("buildEvent sends the folder name only, never the path", () => {
    const event = buildEvent("/home/student/codetime", new Date(2026, 10, 3, 9, 0, 0));
    assert.deepStrictEqual(event, { project: "codetime", time: "2026-11-03T09:00:00" });
});

test("buildEvent has exactly two fields", () => {
    const event = buildEvent("/a/b/c", new Date(2026, 10, 3, 9, 0, 0));
    assert.deepStrictEqual(Object.keys(event).sort(), ["project", "time"]);
});

test("throttle allows the first event", () => {
    const shouldSend = makeThrottle(15000);
    assert.strictEqual(shouldSend(1000), true);
});

test("throttle blocks events inside the gap", () => {
    const shouldSend = makeThrottle(15000);
    shouldSend(1000);
    assert.strictEqual(shouldSend(15999), false);
});

test("throttle allows an event once the gap has passed", () => {
    const shouldSend = makeThrottle(15000);
    shouldSend(1000);
    assert.strictEqual(shouldSend(16000), true);
});

test("a blocked event does not reset the gap", () => {
    const shouldSend = makeThrottle(15000);
    shouldSend(1000);
    shouldSend(10000);
    assert.strictEqual(shouldSend(16000), true);
});
