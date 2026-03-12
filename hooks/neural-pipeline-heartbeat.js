#!/usr/bin/env node
/**
 * neural-pipeline-heartbeat.js
 *
 * Neural Pipeline -- UserPromptSubmit hook
 * Warns if the monitor daemon heartbeat is stale (>2 minutes)
 * or has never started.
 */
var fs = require('fs');
var path = require('path');

function findProjectRoot() {
  var candidates = [
    process.cwd(),
    path.join(process.env.HOME || process.env.USERPROFILE, 'Documents', 'ProjectsCL1', 'react'),
  ];
  for (var i = 0; i < candidates.length; i++) {
    if (fs.existsSync(path.join(candidates[i], 'system', 'config.yaml'))) {
      return candidates[i];
    }
  }
  return null;
}

function main() {
  var input = JSON.parse(fs.readFileSync(0, 'utf8'));
  var root = findProjectRoot();

  if (!root) {
    process.stdout.write(JSON.stringify({ result: 'approve' }));
    return;
  }

  var heartbeatPath = path.join(root, 'monitor', 'health', 'heartbeat');

  if (!fs.existsSync(heartbeatPath)) {
    process.stdout.write(JSON.stringify({
      result: 'approve',
      message: '<system-reminder>Neural Pipeline monitor has never started. Run ./1_start.sh to start it.</system-reminder>',
    }));
    return;
  }

  var heartbeat = fs.readFileSync(heartbeatPath, 'utf8').trim();
  var lastBeat = new Date(heartbeat);
  var now = new Date();
  var ageMs = now - lastBeat;
  var ageMinutes = ageMs / 60000;

  if (ageMinutes > 2) {
    process.stdout.write(JSON.stringify({
      result: 'approve',
      message: '<system-reminder>Neural Pipeline monitor heartbeat is ' + Math.round(ageMinutes) + ' minutes old. It may be stopped. Run ./1_start.sh to restart.</system-reminder>',
    }));
    return;
  }

  process.stdout.write(JSON.stringify({ result: 'approve' }));
}

main();
