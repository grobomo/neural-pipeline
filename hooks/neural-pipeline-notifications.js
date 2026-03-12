#!/usr/bin/env node
/**
 * neural-pipeline-notifications.js
 *
 * Neural Pipeline -- UserPromptSubmit hook
 * Checks ego/notifications/ for pending notifications and injects
 * them into the user's context. After injection, archives them.
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

  var notifDir = path.join(root, 'ego', 'notifications');
  var archiveDir = path.join(notifDir, 'archive');

  if (!fs.existsSync(notifDir)) {
    process.stdout.write(JSON.stringify({ result: 'approve' }));
    return;
  }

  var files = fs.readdirSync(notifDir).filter(function(f) { return f.endsWith('.md'); });

  if (files.length === 0) {
    process.stdout.write(JSON.stringify({ result: 'approve' }));
    return;
  }

  var notifications = [];
  for (var i = 0; i < files.length; i++) {
    var filePath = path.join(notifDir, files[i]);
    var stat = fs.statSync(filePath);
    if (stat.isFile()) {
      var content = fs.readFileSync(filePath, 'utf8').trim();
      notifications.push(content);

      if (!fs.existsSync(archiveDir)) {
        fs.mkdirSync(archiveDir, { recursive: true });
      }
      fs.renameSync(filePath, path.join(archiveDir, files[i]));
    }
  }

  if (notifications.length === 0) {
    process.stdout.write(JSON.stringify({ result: 'approve' }));
    return;
  }

  var message = [
    '<system-reminder>',
    '## Neural Pipeline Notifications',
    '',
  ].concat(notifications).concat([
    '',
    '(' + notifications.length + ' notification(s) -- now archived)',
    '</system-reminder>',
  ]).join('\n');

  process.stdout.write(JSON.stringify({
    result: 'approve',
    message: message,
  }));
}

main();
