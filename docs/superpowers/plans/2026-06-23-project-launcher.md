# Project Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a root-level shell launcher for the backend and frontend.

**Architecture:** One shell script owns local dev orchestration. It clears backend and frontend ports, starts each service with explicit environment and port values, and cleans up child processes on exit.

**Tech Stack:** Bash, Python stdlib backend, Vite frontend, Python unittest for contract checks.

---

### Task 1: Launcher Script

**Files:**
- Create: `tests/test_launcher_script.py`
- Create: `script.sh`

- [ ] **Step 1: Write the failing test**

Create `tests/test_launcher_script.py` with assertions for `script.sh` existence, executable mode, bash syntax, port choices, cleanup behavior, commands, and traps.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_launcher_script -v`

Expected: FAIL because `script.sh` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `script.sh` with backend port `8765`, frontend port `8766`, a `kill_port` helper using `lsof`, backend/frontend launch commands, and cleanup traps.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_launcher_script -v`

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS.
