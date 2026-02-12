#!/bin/bash
cd /home/kavia/workspace/code-generation/energy-usage-monitoring-platform-218715-218729/energy_api
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

