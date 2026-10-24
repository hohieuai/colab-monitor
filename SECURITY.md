# Security policy

## Supported versions

Security fixes go into the latest release only. Upgrade to it before you report a problem.

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Report a vulnerability

Report vulnerabilities privately. Don't open a public issue, discussion, or pull request, because
that discloses the problem before a fix exists.

1. Open the [private reporting form](https://github.com/hohieuai/colab-monitor/security/advisories/new).
   You can also reach it from the repository's **Security** tab, under **Report a vulnerability**.
2. Describe the problem and its impact. Say what an attacker can do, for example read a log file
   outside the configured folders.
3. List the steps to reproduce it. Include the output of `colab-monitor --version`, your operating
   system and browser, and the options you started Colab Monitor with.
4. Name the versions you know are affected, and any mitigation or fix you have found.

Only the maintainer and you can see the report. If you can't use GitHub, open a public issue that
asks for a private contact and contains no details of the problem.

## What happens after you report

1. The maintainer acknowledges your report within 7 days.
2. Within 14 days, the maintainer confirms the vulnerability or explains why it isn't one.
3. If it's confirmed, the maintainer develops the fix in a private fork of the advisory, releases
   it, and publishes a GitHub Security Advisory. A CVE ID is requested through GitHub when the issue
   warrants one.
4. The advisory credits you by name, unless you prefer to stay anonymous.

You get an update at least every 14 days while the report is open.

## Disclosure timeline

This project follows coordinated disclosure with a 90-day limit, as the
[OpenSSF vulnerability disclosure guide](https://github.com/ossf/oss-vulnerability-guide)
recommends. The fix and the advisory are published within 90 days of your report, and earlier when
the fix is ready. If a fix needs longer, the maintainer agrees a new date with you. Please keep the
details private until the advisory is published.

## Scope

These reports are in scope:

- The `colab-monitor` server, its HTTP API, and the web page in this repository.
- The published package, including the files it installs.

These reports are out of scope:

- Vulnerabilities in the `colab` CLI or in Colab itself. Report those to their own projects.
- Risks that come from an option you set on purpose, such as `--host 0.0.0.0`, which serves your
  logs to your network and prints a warning when you use it.
- Attacks that need administrator access to your computer, or physical access to it.
- Scanner output with no demonstrated impact on Colab Monitor.

## Security model

Measure a report against what Colab Monitor promises:

- The server listens on `127.0.0.1` by default. While it listens on a loopback address, it refuses
  requests whose `Host` header is not a loopback name or address, which blocks DNS-rebinding
  attacks.
- Access tokens and runtime URLs from the CLI's session file never reach the page. The server
  removes them first.
- `/api/log` serves only the files passed with `--log`, and `.log`, `.out`, and `.err` files
  directly inside a `--log-dir` folder. The server resolves each path, including symlinks, checks the result, and reads that same file. Other
  files come from a fixed list.
- The page loads nothing from other sites. Its Content Security Policy blocks inline scripts and
  scripts from other origins, and the page inserts log and history text as text, never as HTML.
- Colab Monitor is read-only. It sends two read requests to Colab per interval and never starts,
  stops, or connects to a machine.

[How Colab Monitor works](docs/how-it-works.md) explains the design behind these choices.
