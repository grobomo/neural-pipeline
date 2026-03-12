#!/usr/bin/env node
/**
 * neural-pipeline-guard.js
 *
 * Neural Pipeline -- PreToolUse hook (BLOCKING, GLOBAL)
 * Prevents Claude Code from doing work directly on ANY project.
 * Forces all work to be routed through the ego pipeline.
 *
 * BLOCKS: Edit/Write on code files (.py, .js, .ts, .jsx, .tsx, .go, .rs, .java,
 *         .sh, .yaml, .yml, .json, .html, .css, .sql, .tf, .md project docs)
 * ALLOWS: pipeline infrastructure, hooks, config, tests, CLAUDE.md, etc.
 *
 * Hook type: PreToolUse
 * Matcher: Edit|Write|Bash
 */
var fs = require('fs');
var path = require('path');

var PIPELINE_ROOT = path.join(
  process.env.HOME || process.env.USERPROFILE,
  'Documents', 'ProjectsCL1', 'react'
);

// Code file extensions that should go through the pipeline
var CODE_EXTENSIONS = [
  '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java', '.rb',
  '.sh', '.bash', '.zsh', '.ps1',
  '.html', '.css', '.scss', '.less',
  '.sql', '.tf', '.hcl',
  '.c', '.cpp', '.h', '.hpp', '.cs',
  '.php', '.swift', '.kt', '.scala',
  '.r', '.R', '.jl', '.lua', '.pl',
  '.dockerfile', '.yaml', '.yml', '.toml',
];

// Paths ALWAYS allowed (pipeline infrastructure, config, meta-files)
var ALWAYS_ALLOWED = [
  // Pipeline infrastructure
  /[/\\]\.claude[/\\]/,
  /[/\\]hooks[/\\]/,
  /[/\\]tests[/\\]/,
  /[/\\]\.tmp[/\\]/,
  // Pipeline source code (its own implementation)
  new RegExp(PIPELINE_ROOT.replace(/[\\]/g, '[/\\\\]') + '[/\\\\]src[/\\\\]'),
  new RegExp(PIPELINE_ROOT.replace(/[\\]/g, '[/\\\\]') + '[/\\\\]system[/\\\\]'),
  new RegExp(PIPELINE_ROOT.replace(/[\\]/g, '[/\\\\]') + '[/\\\\]pipeline[/\\\\]'),
  new RegExp(PIPELINE_ROOT.replace(/[\\]/g, '[/\\\\]') + '[/\\\\]ego[/\\\\]'),
  new RegExp(PIPELINE_ROOT.replace(/[\\]/g, '[/\\\\]') + '[/\\\\]monitor[/\\\\]'),
  // Meta-files in any project
  /CLAUDE\.md$/,
  /SKILL\.md$/,
  /BUILD_PLAN\.md$/,
  /SPEC\.md$/,
  /README\.md$/,
  /\.gitignore$/,
  /requirements\.txt$/,
  /package\.json$/,
  /generate_report\.py$/,
  /install\.sh$/,
  /[/\\][0-9]_[a-z]+\.sh$/,   // Lifecycle scripts (1_start.sh, etc.)
  // Settings and config
  /settings\.json$/,
  /settings\.local\.json$/,
  /\.mcp\.json$/,
  /config\.yaml$/,
];

// Bash commands always allowed
var ALLOWED_BASH = [
  /python\s+-m\s+src\.ego/,    // Ego CLI
  /python\s+tests[/\\]/,       // Tests
  /python\s+generate_report/,  // Report gen
  /\.\/[0-9]_/,                // Lifecycle scripts
  /git\s+/,                    // Git
  /gh\s+/,                     // GitHub CLI
  /ls\b/,                      // Listing
  /cat\b/,                     // Reading
  /head\b/,
  /tail\b/,
  /wc\b/,
  /grep\b/,
  /find\b/,
  /pip\b/,                     // Package management
  /npm\b/,
  /node\b/,
  /start\s+""/,                // Opening files (Windows)
  /open\s+/,                   // Opening files (Mac)
  /xdg-open/,                  // Opening files (Linux)
  /python\s+-c\s+".*import/,   // Python one-liner checks
  /chmod\b/,
  /mkdir\b/,
  /rm\b/,                      // File cleanup (careful but allowed)
  /cp\b/,
  /mv\b/,
];

function isAlwaysAllowed(filePath) {
  for (var i = 0; i < ALWAYS_ALLOWED.length; i++) {
    if (ALWAYS_ALLOWED[i].test(filePath)) return true;
  }
  return false;
}

function isCodeFile(filePath) {
  var ext = path.extname(filePath).toLowerCase();
  return CODE_EXTENSIONS.indexOf(ext) !== -1;
}

function isAllowedBash(command) {
  for (var i = 0; i < ALLOWED_BASH.length; i++) {
    if (ALLOWED_BASH[i].test(command)) return true;
  }
  return false;
}

function main() {
  var input = JSON.parse(fs.readFileSync(0, 'utf8'));
  var toolName = input.tool_name || '';
  var toolInput = input.tool_input || {};

  // Only guard Edit, Write, Bash
  if (toolName !== 'Edit' && toolName !== 'Write' && toolName !== 'Bash') {
    process.exit(0);
    return;
  }

  // Handle Edit/Write
  if (toolName === 'Edit' || toolName === 'Write') {
    var filePath = toolInput.file_path || '';

    // Always-allowed paths bypass the guard
    if (isAlwaysAllowed(filePath)) {
      process.exit(0);
      return;
    }

    // If it's a code file, block it
    if (isCodeFile(filePath)) {
      process.stderr.write(
        'BLOCKED by neural-pipeline-guard: Direct code editing is disabled.\n' +
        'File: ' + filePath + '\n\n' +
        'BLOCKED: Relay user\'s exact request to ego: python -m src.ego "<user request>"\n' +
        'Pass through verbatim -- do NOT rephrase, enhance, or interpret.\n'
      );
      process.exit(2);
      return;
    }

    // Non-code files (txt, log, etc.) -- allow
    process.exit(0);
    return;
  }

  // Handle Bash
  if (toolName === 'Bash') {
    var command = toolInput.command || '';

    if (isAllowedBash(command)) {
      process.exit(0);
      return;
    }

    // Block commands that clearly write code files
    var codeWritePatterns = [
      /echo\s+.*>\s+\S+\.(py|js|ts|go|rs|java|sh)/,
      /cat\s+<<.*>\s+\S+\.(py|js|ts|go|rs|java|sh)/,
      /python\s+-c\s+.*open\(.*'w'/,
    ];

    for (var i = 0; i < codeWritePatterns.length; i++) {
      if (codeWritePatterns[i].test(command)) {
        process.stderr.write(
          'BLOCKED by neural-pipeline-guard: Cannot write code files via Bash.\n' +
          'BLOCKED: Relay user\'s exact request to ego: python -m src.ego "<user request>"\n' +
          'Pass through verbatim -- do NOT rephrase, enhance, or interpret.\n'
        );
        process.exit(2);
        return;
      }
    }

    // Other bash commands -- allow
    process.exit(0);
    return;
  }

  process.exit(0);
}

main();
