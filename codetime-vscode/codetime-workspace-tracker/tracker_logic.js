"use strict";

const path = require("path");

function tokenPath(env, home) {
    const base = env.CODETIME_HOME || path.join(home, ".codetime");
    return path.join(base, "token");
}

function pad(n) {
    return String(n).padStart(2, "0");
}

// Local time without a time zone, like "2026-11-03T09:00:00".
function localIso(date) {
    return (
        `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
        `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    );
}

// The message sent to CodeTime: folder NAME and time only. Nothing else.
function buildEvent(folderPath, now) {
    return {
        project: path.basename(folderPath),
        time: localIso(now),
    };
}

// Returns a function: call it with the current time in milliseconds.
// It answers true (and remembers the time) only if enough time has passed.
function makeThrottle(minGapMs) {
    let last = null;
    return function shouldSend(nowMs) {
        if (last !== null && nowMs - last < minGapMs) {
            return false;
        }
        last = nowMs;
        return true;
    };
}

module.exports = { tokenPath, localIso, buildEvent, makeThrottle };
