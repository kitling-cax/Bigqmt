BIGQMT_BRIDGE generic upload notes
==================================

Use the profile-specific README.txt inside each generated release ZIP.  The
repository copy is generic and contains no environment account binding.

Each ZIP contains:

  qmt_python\       files copied into that environment's QMT python directory
  qmt_editor\       BIGQMT_BRIDGE.py pasted into a new QMT Python strategy
  host_config\      Redis/host configuration for the corresponding Tray
  MANIFEST.json     SHA256 and deployment identity

Required order:

  1. Keep both QMT accounts logged in but start with SIMULATION only.
  2. Stop BIGQMT_REDIS_DRYRUN in simulation QMT.
  3. Back up the existing simulation QMT python Bridge files.
  4. Copy qmt_python into the simulation QMT python directory.
  5. Create BIGQMT_BRIDGE in QMT and paste qmt_editor\BIGQMT_BRIDGE.py.
  6. Run it on minute bars and verify the printed release id.
  7. Verify read-only ping/account/positions/orders/trades/quotes.
  8. Only after simulation passes, prepare production Redis port 6380 and
     use the formal package's own generated README.

The formal package has rpc_allow_order_methods=False, a strict read-only RPC
whitelist, and every execution gate BLOCKED. FormulaServer 58600 is disabled
on the formal host side because the simulation terminal currently owns it.

If any version, environment, account, Redis or quote check is wrong, stop the
new strategy and restore BIGQMT_REDIS_DRYRUN.  Never troubleshoot by enabling
order methods.
