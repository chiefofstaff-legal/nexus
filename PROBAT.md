# PROBAT

Probat = "it is proven" (Latin). Self-notarising chain demonstrating that nexus-poc speaks the OSS happi/1.1 protocol from github.com/chiefofstaff-legal/donna.

**Verify locally** (Python stdlib only, no dependencies):

```bash
git clone https://github.com/chiefofstaff-legal/donna.git ~/donna-legal
export DONNA_NOTARISE_KEY=nexus-public-demo-key-2026-05-11
python3 ~/donna-legal/bin/notarise verify --chain PROBAT.md
# expected: OK: 3 record(s) verified (HMAC-SHA256)
```

Tamper with any record below — flip a single byte in any `metadata` field, or change a `previous_hash` — and the verifier reports the break with its sequence number. The chain is append-only, the signature signs the canonical payload (sort_keys=True, separators=(",","":")), and the wire schema is byte-identical to donna-legal/bin/notarise.

---

## Chain

```idr
{
  "confidence": 0.92,
  "decision_id": "idr_1778532406071401984_fc546a85",
  "intent": "sensitivity_classification: confidential \u2014 NEXUS council routes to on-prem Ollama for FADP-protected client data",
  "metadata": {
    "decision": "confidential",
    "decision_point": "sensitivity_classification",
    "demo": true
  },
  "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "protocol": "happi/1.1",
  "signature": "cd46c62f01679323eb8dbd79929f7974d7c078950190f9886b0106c81454bca8",
  "signer": "nexus-bot",
  "timestamp": "2026-05-11T20:46:46Z"
}
```

```idr
{
  "confidence": 0.88,
  "decision_id": "idr_1778532406072193024_29314df7",
  "intent": "llm_routing: ollama qwen2.5:3b \u2014 confidential path on Hetzner VPS, zero cloud egress",
  "metadata": {
    "decision": "ollama",
    "decision_point": "llm_routing",
    "demo": true,
    "model": "qwen2.5:3b"
  },
  "previous_hash": "49d6ec886a58ba1232c0e07b9fa794a5ffe54862911efb95343a0772bbd9665e",
  "protocol": "happi/1.1",
  "signature": "9ed0adafa8640c1b1d4eae49ade9e0c0dc18ef801cd00e5ce60f889d720b0fea",
  "signer": "nexus-bot",
  "timestamp": "2026-05-11T20:46:46Z"
}
```

```idr
{
  "confidence": 0.95,
  "decision_id": "idr_1778532406072505088_2a298bc9",
  "intent": "document_classification: nda \u2014 PyMuPDF4LLM extracted, Claude Haiku classified, signed before filing",
  "metadata": {
    "decision": "nda",
    "decision_point": "document_classification",
    "demo": true
  },
  "previous_hash": "ee1d22dba9a2c3ea40edfad1f68fbe1f9aa33149c765eeb4cb62192da6061574",
  "protocol": "happi/1.1",
  "signature": "34ebf8f0894442528ba4a1b1406080ed2814032c07f5e3078727309e328736e3",
  "signer": "nexus-bot",
  "timestamp": "2026-05-11T20:46:46Z"
}
```
