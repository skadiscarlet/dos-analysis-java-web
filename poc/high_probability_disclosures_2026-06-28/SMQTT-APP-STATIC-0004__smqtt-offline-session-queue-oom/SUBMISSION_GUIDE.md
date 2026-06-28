# Submission Guide: SMQTT-APP-STATIC-0004

## Where to Report

Primary target: `quickmsg/smqtt` (https://github.com/quickmsg/smqtt)

Direct reporting links:

- GitHub private vulnerability report, if enabled: https://github.com/quickmsg/smqtt/security/advisories/new
- GitHub Security tab: https://github.com/quickmsg/smqtt/security
- GitHub security policy page: https://github.com/quickmsg/smqtt/security/policy
- Public issues fallback, contact request only and no PoC details: https://github.com/quickmsg/smqtt/issues
- CNVD later-stage coordination: https://www.cnvd.org.cn/

Project-specific private contact:

- No concrete address in local `SECURITY.md`; use GitHub private reporting first, then ask maintainers for a private security contact if unavailable.

Recommended order:

1. Submit privately through GitHub private vulnerability reporting when the direct URL is available.
2. If GitHub private reporting is disabled, use the project-specific email/Tidelift contact above when present.
3. If no private channel exists, open only a minimal public issue asking for a security contact. Do not include payload size, reproduction loop, logs, or attached evidence publicly.
4. If the maintainer is unresponsive after a reasonable coordination window, submit the same package to CNVD/CVE coordination as an availability-only DoS report.

## What to Send

Attach or paste:

- `VULNERABILITY_REPORT.md`
- `attachments/dynamic_finding.json`
- `attachments/static_finding.json`
- `attachments/SMQTT-APP-STATIC-0004.log.gz`
- `attachments/ATTACHMENTS.md`

Suggested subject:

`[Security] Denial of Service in quickmsg/smqtt: Offline persistent subscriptions accumulate unbounded session message queues`

## Handling Notes

- Keep the report private until the maintainer acknowledges and has a fix plan.
- Start with the reproduction summary in `VULNERABILITY_REPORT.md`; provide exact scripts or payload builders only after the maintainer asks.
- Ask the maintainer whether they want to publish a GitHub Security Advisory and request a CVE.
- If submitting to CNVD later, include the same report plus the compressed log and make clear that the impact is availability-only DoS.
- GitHub reference for private vulnerability reporting: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability
