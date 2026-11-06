# Astra API transport

The native Codex pool runner creates one loopback relay per pool and a distinct route and timing ledger per room. All execution pools and QA clients sharing the API credential must share the same **50-request gate** and the same absolute lock directory. One accepted model request holds one slot until upstream consumption ends. Time spent waiting for a slot is recorded separately.

## Fresh runs

On the trusted controller, provision the Responses-compatible HTTPS base URL (ending in `/v1`) and API key via the environment using your secret manager. Set `PRIVATE` to a private directory outside the checkout, and `SHARED_LOCKS` to a shared absolute directory mounted at the same path on every participating host. Confirm that concurrent atomic mkdir on that filesystem excludes competitors across hosts before using the verification flag.

```sh
umask 077
mkdir -p "$PRIVATE"
python3 transport/configure.py \
  --credentials "$PRIVATE/provider.private.json" \
  --gate "$PRIVATE/api-concurrency.private.json" \
  --shared-lock-directory "$SHARED_LOCKS" \
  --scope astra_shared --atomic-mkdir-verified
unset VIDEOICL_API_BASE_URL VIDEOICL_API_KEY
```

The generator reads `VIDEOICL_API_BASE_URL` and `VIDEOICL_API_KEY`. It writes mode-0600 files, leaves existing credentials untouched, and can reuse an identical gate file. Point the pool configuration at these files. Give all pools access to the chosen CA bundle. The bundle must validate the chosen provider’s HTTPS certificate and hostname.

The corresponding options of `VideoICLBench/scripts/harbor/run_embodied_pool.py` are:

```sh
--credentials "$PRIVATE/provider.private.json" \
--provider-ca-bundle "$CA_BUNDLE" \
--api-concurrency-config "$PRIVATE/api-concurrency.private.json" \
--provider-request-metadata --embodied-auto-recover \
--unknown-api-policy preserve_world --timeout 0
```

The runner starts the pinned `vic_sdk/tls_relay_entry.py`. Direct TLS uses HTTP/1.1, ignores ambient proxy variables and disables redirects. Connection and pool acquisition timeouts are 300 seconds. Accepted reads and writes can run longer. The relay streams the original Responses or native compact request without an automatic replay. Inspect per-room API timing and successful-response usage to distinguish queueing, quota errors and pool action barriers.

## Historical provider cutover

The campaign returned to its direct My API route after a temporary provider switch. Existing sessions retained their old per-room endpoint. The replacement relay using that endpoint forwarded the original model body with the new upstream Authorization header. `direct_auth.py` contains the portable equivalent of that header and model check with a locally configured HTTPS destination. Fresh pools read the chosen key at launch and use the ordinary relay entrypoint above.

Production cutover additionally required pinning the live owner and native world, preserving timing routes and concurrency admission, gracefully draining the old listener, then binding the same loopback port. These one-shot, host-specific operations and their credentials are deliberately separate from the fresh-run configuration. If upstream outcome is unknown, preserve the world and lease for reconciliation. Never start a second episode to rotate a credential.

Offline checks from this directory: `python3 -B -m unittest discover -v`. These tests call no API.
