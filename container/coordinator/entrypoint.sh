#!/bin/sh
set -eu

# The image is deliberately shadow-only until a later explicit production
# promotion.  A changed environment cannot silently turn this package into an
# execution service.
if [ "${BIGQMT_COORDINATOR_MODE:-}" != "SHADOW_READONLY" ]; then
  echo "refusing non-shadow Coordinator mode" >&2
  exit 64
fi
if [ "${BIGQMT_EXECUTION_WRITES_DISABLED:-}" != "1" ] || \
   [ "${BIGQMT_LEASE_GRANTS_DISABLED:-}" != "1" ] || \
   [ "${BIGQMT_INTENT_CONFIRM_DISABLED:-}" != "1" ]; then
  echo "refusing Coordinator with any execution write switch enabled" >&2
  exit 65
fi

exec python /app/scripts/coordinator/serve.py
