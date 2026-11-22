# Inven Auto — Gmail Report Integration

This page describes the Gmail reporting integration used by the personal **inven-auto** automation project.

## What the application does

Inven Auto runs scheduled personal automation tasks and records their results in GitHub Actions and GitHub Issues. The optional Gmail integration sends a daily status report to an address configured by the project owner. The report may contain task outcomes, timestamps, diagnostic summaries, and links to the corresponding GitHub issue and workflow run.

## Google account access

The integration requests only the Google OAuth scope `https://www.googleapis.com/auth/gmail.send`. It uses this permission to send the report. It does not request permission to read, search, modify, or delete mailbox messages.

## Operation and control

The integration is intended for the project owner's personal use. The owner can stop email delivery by removing the Gmail-related GitHub Actions secrets or disabling the integration, and can revoke Google account access from their Google Account security settings.

## Privacy

See the [Privacy Policy](privacy-policy.md) for details about information handled by this integration.

## Contact

For questions about this project or this policy, use the [project issue tracker](https://github.com/kdkim2810/inven-auto/issues).
