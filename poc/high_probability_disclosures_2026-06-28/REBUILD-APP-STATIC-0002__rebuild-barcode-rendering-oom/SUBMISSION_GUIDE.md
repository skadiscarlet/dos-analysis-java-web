# Submission Guide: REBUILD-APP-STATIC-0002

## Where to Report

Primary target: `getrebuild/rebuild` (https://github.com/getrebuild/rebuild)

Direct reporting links:

- GitHub private vulnerability report, if enabled: https://github.com/getrebuild/rebuild/security/advisories/new
- GitHub Security tab: https://github.com/getrebuild/rebuild/security
- GitHub security policy page: https://github.com/getrebuild/rebuild/security/policy
- Public issues fallback, contact request only and no PoC details: https://github.com/getrebuild/rebuild/issues
- CNVD later-stage coordination: https://www.cnvd.org.cn/

Project-specific private contact:

- Security email from `SECURITY.md`: rebuild@ruifang-tech.com

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
- `attachments/REBUILD-APP-STATIC-0002.log.gz`
- `attachments/ATTACHMENTS.md`

Suggested subject:

`[Security] Denial of Service in getrebuild/rebuild: Anonymous barcode rendering can allocate oversized BitMatrix/BufferedImage`

## Handling Notes

- Keep the report private until the maintainer acknowledges and has a fix plan.
- Start with the reproduction summary in `VULNERABILITY_REPORT.md`; provide exact scripts or payload builders only after the maintainer asks.
- Ask the maintainer whether they want to publish a GitHub Security Advisory and request a CVE.
- If submitting to CNVD later, include the same report plus the compressed log and make clear that the impact is availability-only DoS.
- GitHub reference for private vulnerability reporting: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability
