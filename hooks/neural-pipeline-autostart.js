#!/usr/bin/env node
/**
 * neural-pipeline-autostart.js
 *
 * SessionStart hook -- auto-starts the monitor daemon if not running.
 * Pure Node.js -- no bash/shell spawns to avoid Windows console windows.
 *
 * Hook type: SessionStart
 */
var fs = require('fs');
var path = require('path');
var child_process = require('child_process');

var PIPELINE_ROOT = path.join(
  process.env.HOME || process.env.USERPROFILE,
  'Documents', 'ProjectsCL1', 'react'
);
var PID_FILE = path.join(PIPELINE_ROOT, '.tmp', 'monitor.pid');
var LOG_DIR = path.join(PIPELINE_ROOT, 'monitor', 'logs');

function isMonitorRunning() {
  try {
    if (!fs.existsSync(PID_FILE)) return false;
    var pid = parseInt(fs.readFileSync(PID_FILE, 'utf8').trim());
    process.kill(pid, 0); // signal 0 = check if alive
    return true;
  } catch (e) {
    try { fs.unlinkSync(PID_FILE); } catch (e2) {}
    return false;
  }
}

function ensureDir(dir) {
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) {}
}

function main() {
  // Read stdin (SessionStart hook contract)
  try { fs.readFileSync(0, 'utf8'); } catch (e) {}

  if (isMonitorRunning()) {
    process.stdout.write('[neural-pipeline] Monitor running. Pipeline ready.\n');
    process.exit(0);
    return;
  }

  ensureDir(path.join(PIPELINE_ROOT, '.tmp'));
  ensureDir(LOG_DIR);

  // Spawn python directly -- no bash, no nohup, no shell
  var logFile = path.join(LOG_DIR, 'monitor-stdout.log');
  var out = fs.openSync(logFile, 'a');
  var err = fs.openSync(logFile, 'a');

  var child;
  try {
    child = child_process.spawn('python', ['-m', 'src.monitor', PIPELINE_ROOT], {
      cwd: PIPELINE_ROOT,
      detached: true,
      stdio: ['ignore', out, err],
      windowsHide: true,
      shell: false,
    });
    child.unref();
  } catch (e) {
    process.stderr.write('[neural-pipeline] Failed to start monitor: ' + e.message + '\n');
    process.exit(0);
    return;
  }

  fs.writeFileSync(PID_FILE, String(child.pid));
  process.stdout.write('[neural-pipeline] Monitor started (PID ' + child.pid + '). Pipeline ready.\n');
  process.exit(0);
}

main();
