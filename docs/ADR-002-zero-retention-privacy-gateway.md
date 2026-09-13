# ADR-002: Zero-Retention Privacy Gateway & Bi-Directional Tokenization

**Status**: Accepted  
**Date**: September 2026  
**Author**: Pedro Griff Marcincowski (Systems Architect & Lead Engineer)  
**Stakeholders**: Information Security (InfoSec), Legal, Privacy & Compliance (LGPD/GDPR/PIPEDA)  

---

## 1. Context & Problem Statement

Global organizations operating across Brazil, the United States, and Canada, processing sensitive People data:
- **Brazil**: CPF (*Cadastro de Pessoas Físicas*), CLT wage contracts, maternity status, protected under **LGPD** (*Lei Geral de Proteção de Dados*, Law No. 13.709/2018).
- **United States**: SSN (Social Security Numbers), compensation histories, protected under federal and state privacy statutes.
- **Canada**: SIN (Social Insurance Numbers), pay transparency disclosures, protected under **PIPEDA**.

Directly sending sensitive identifiers, employee legal names, or compensation figures to third-party commercial LLMs creates severe compliance and data exfiltration liabilities.

---

## 2. Decision Drivers

- **Zero PII/SPII Exfiltration**: Invariant that no raw Brazilian CPF, US SSN, Canadian SIN, or exact salary figures may cross the external network perimeter.
- **Reasoning Fidelity**: The LLM must still be able to reason about relative compensation (e.g. compa-ratio, percentage merit) without knowing plaintext financial numbers or government IDs.
- **LGPD Article 18 Compliance**: Right-to-be-forgotten / cryptographic shredding capability to permanently anonymize historical logs upon employee departure.

---

## 3. Considered Options

1. **Option A: Self-Host Open-Source LLMs (e.g. Llama-3-70B on internal Kubernetes)**
   - *Pros*: Data stays within VPC.
   - *Cons*: High CapEx GPU infrastructure costs, complex operational overhead, lower baseline reasoning on nuanced multilingual HR nuances compared to frontier models.
2. **Option B: Contractual Zero-Data-Retention (ZDR) Only**
   - *Pros*: Simplest implementation.
   - *Cons*: Still exposes plaintext SPII across external TLS boundaries; does not protect against provider logging bugs or internal prompt injection attacks.
3. **Option C: Perimeter Ingress Tokenization Vault with Cryptographic Shredding (Chosen)**
   - *Pros*: Zero plaintext PII ever leaves the perimeter; deterministic surrogate tokens (`[TOKEN_CPF_XXXX]`, `[TOKEN_COMP_XXXX]`) preserve reasoning structure; vault can be cryptographically shredded per LGPD requirements.
   - *Cons*: Requires maintaining a tokenization proxy and regex/NER pattern engine.

---

## 4. Decision Outcome

**Chosen Option: Option C (Perimeter Ingress Tokenization Vault)**.

We engineered `ZeroRetentionPrivacyGateway` directly into the mesh pipeline:
1. **Perimeter Interception**: All incoming text payloads are scanned and scrubbed. Sensitive entities are mapped to cryptographic surrogate tokens.
2. **Hard Assert Barrier**: Before any payload is transmitted to an LLM provider, `assert_zero_pii_leakage()` runs regex verification. Any unmasked PII trips an immediate exception and blocks transmission.
3. **Local Rehydration**: Once the LLM returns its structured evaluation, surrogate tokens are rehydrated to plaintext strictly within the secure internal boundary before presenting to authorized humans.
4. **LGPD Cryptographic Shredding**: Calling `vault.shred()` deletes all token mappings, instantly rendering historical external traces permanently un-linkable.
