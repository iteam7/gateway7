# Week 08 AI usage

## Tools and work

On 13 November 2026, Codex updated the Python checks workflow for task [#77](https://github.com/iteam7/gateway7/issues/77). The change adds Ubuntu and Windows runners with independent failure reporting and platform-specific commands for the installed-wheel smoke check. The Windows run exposed a test that assumed 40 ms sleeps finish before a 60 ms timer; its intervals are now 200 ms under a 300 ms shared hook budget, preserving the test while allowing Windows scheduling jitter. The exact-head Windows suite reached the 10-minute job limit before returning; the Python matrix timeout is now 20 minutes. Human assessment of this output: **TODO**.
