# Privacy Policy — Inven Auto Gmail Report Integration

**Last updated: 2026-11-22**

This policy describes the Gmail reporting integration for the personal Inven Auto automation project.

## Information processed

To create and deliver a report, the integration may process:
- Automation task status, execution timestamps, and concise diagnostic messages.
- Links to relevant GitHub Issues, GitHub Actions workflow runs, and job logs.
- The recipient email address configured by the project owner.
- OAuth credentials required to send mail, including a refresh token.

The report content is generated from the project's automation results. It may include operational details about the project owner's own devices or automation, so report recipients should be limited to addresses chosen by the owner.

## Google permissions and use

The integration requests the Google OAuth scope `https://www.googleapis.com/auth/gmail.send` only. This permission is used to send report emails. The integration is not designed to read, search, label, modify, or delete Gmail messages.

OAuth access tokens are obtained when needed and used to submit the email. The refresh token and OAuth client credentials are stored as GitHub Actions repository secrets, not in source code. The project owner controls those secrets and can revoke the integration at any time.

## Storage and sharing

The integration does not sell personal information or use report data for advertising. Report data and execution logs may be processed and retained by GitHub as part of GitHub Actions and Issues, subject to GitHub's own terms and retention settings. Email is delivered through Google Gmail and is subject to Google's terms and privacy practices.

No data is intentionally shared with unrelated third parties by this integration. GitHub and Google receive the information necessary to run the automation and deliver the email.

## Retention and deletion

The project owner can remove configured GitHub Actions secrets, delete relevant workflow artifacts or issues, and revoke the Google OAuth grant. Copies already delivered to an email inbox are controlled by the recipient and their email provider.

## Security

OAuth secrets should be stored only in GitHub Actions secrets and must never be committed to the repository or posted publicly. Access to the repository and its automation should be restricted to authorized users.

## Changes to this policy

This policy may be updated if the integration's data handling or requested Google permissions change. The revision date above will be updated accordingly.

## Contact

For questions or privacy requests concerning this integration, contact the project owner through the [Inven Auto GitHub issue tracker](https://github.com/kdkim2810/inven-auto/issues).
