# Security policy

## Reporting a vulnerability

Please **don't open a public issue**. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on the repository page. You'll get a reply within a week,
and we'll agree on a disclosure date once a fix is ready.

Only the latest release receives security fixes.

## How Colab Monitor protects your data

Useful context for a report:

- **Local only by default.** The server binds to `127.0.0.1`. Binding to another address prints a
  warning, because anyone who can reach the port can read your job logs.
- **DNS-rebinding guard.** While bound to loopback, requests with a non-local `Host` header are
  refused.
- **No secrets reach the browser.** Colab session tokens and runtime proxy URLs are stripped on the
  server before any response is sent.
- **Restricted file access.** `/api/log` serves only files you configured, or `*.log`, `*.out` and
  `*.err` files directly inside a configured folder; paths are resolved before checking. Static
  files come from a fixed allow-list.
- **Strict page policy.** The page loads nothing from other sites and runs no inline scripts
  (`Content-Security-Policy: default-src 'self'; script-src 'self'; ...`). Text from logs and
  history is inserted as text, never as HTML.
- **Read-only.** It never creates, stops or connects to Colab machines. It calls two read
  endpoints on Colab, on a fixed interval.

Issues in the `colab` CLI or in Colab itself should be reported to those projects.
