# Local handoff

This directory is the only committed ingress for local workstation requests.

Rules:

- Git/repo may propose JSON jobs under local_handoff/requests/.
- A committed request is never trusted as executable state.
- The Windows user stages a request into .local/jobs/staged/.
- Staging records SHA-256 and source repo path.
- Execution requires both job mode=execute and a local --execute / -Execute action.
- Receipts and raw media remain private under .local/ and recordings/.

Normal flow:

~~~text
repo request
  -> stage-request
  -> private staged copy + SHA-256
  -> dry-run
  -> explicit local execute
  -> receipt
~~~

Never place passwords, tokens, absolute machine paths, or raw media here.
