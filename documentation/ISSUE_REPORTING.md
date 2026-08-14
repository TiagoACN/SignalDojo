# Reporting a SignalDojo Issue

A useful issue report should let another engineer reproduce the problem without exposing confidential test data.

## Before reporting

1. Save a copy of the affected project.
2. Run **Workflow → Validate Workflow**.
3. Open **Help → Diagnostics** and copy the application version, operating-system version, package versions, plugin errors, project validation result and relevant recent log lines.
4. Replace confidential source files with a small synthetic dataset whenever possible.
5. Confirm whether the issue also occurs with third-party plugins removed from `%USERPROFILE%\.signaldojo\plugins`.

## Include

- A clear title and expected behaviour.
- Exact steps to reproduce the issue.
- The smallest `.sdojo` project that demonstrates it.
- A synthetic or anonymised input file when data is required.
- The complete human-readable error shown by SignalDojo.
- Whether the result changes after **Workflow → Clear Processing Cache**.
- Screenshots only when they show a layout or rendering defect that text cannot describe.

## Privacy

Diagnostic reports do not intentionally include source-file contents. Review paths, project notes and log lines before sharing them. Never submit proprietary sensor data, credentials, personal data or unrestricted third-party plugins unless you are authorised to do so.

Send the report through the support or issue-tracking channel supplied by the organisation that distributed your SignalDojo build.
