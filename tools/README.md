# tools/

This directory holds the official `razorpay-mcp-server` binary — **not committed**
(gitignored; it's a ~3MB third-party executable, and the repo should stay source-only).
`src/mcp_client.py` and `src/sources.py`'s `RazorpaySettlementsSource` expect it at
`tools/razorpay-mcp-server/razorpay-mcp-server.exe` (override with the
`RAZORPAY_MCP_SERVER_PATH` env var if you place it elsewhere).

## Fetch it (Windows x86_64)

```powershell
gh release download v1.2.1 --repo razorpay/razorpay-mcp-server `
  --pattern "razorpay-mcp-server_Windows_x86_64.zip" `
  --pattern "razorpay-mcp-server_1.2.1_checksums.txt"

# verify the checksum BEFORE extracting/running anything
certutil -hashfile razorpay-mcp-server_Windows_x86_64.zip SHA256
# compare against the matching line in razorpay-mcp-server_1.2.1_checksums.txt

Expand-Archive razorpay-mcp-server_Windows_x86_64.zip -DestinationPath razorpay-mcp-server
```

(For other platforms, grab the matching asset from the same release —
`Darwin`/`Linux` × `arm64`/`x86_64`/`i386` — and verify against the same checksums file.)

Verified on 2026-09-04: SHA256 `398867265443b1b9140f3f47150b940b5f5231d21acf568078412489ba7c3022`
for `razorpay-mcp-server_Windows_x86_64.zip` (v1.2.1), matching the official
`razorpay-mcp-server_1.2.1_checksums.txt` published alongside it.

## Requires

`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `.env` (test-mode `rzp_test_...` keys —
Dashboard → Test Mode → Settings → API Keys → Generate Test Key). The client always
launches the binary with `--read-only`; it is for reading reconciliation data, never
for mutating Razorpay state, test-mode or otherwise.

## Empirically confirmed (2026-09-04, live, real keys)

- `fetch_all_payments` returns genuine captured test-mode payments — confirmed by
  seeing the same real payment ID (`pay_TTk0Us...`) from the original day-1 spike.
- `fetch_settlement_recon_details` returns `{"count":0,"items":[]}` in test mode —
  RE-confirms (via the official tool this time, not just the raw SDK) that test-mode
  settlements never populate (pre-KYC gating). See `LOG.md`. This is not a bug in the
  integration; it needs a KYC-activated account, which is out of scope for a hackathon
  submission — the CSV/SQLite path remains the demo data source.
