# Live experiment results

Observed on 2026-09-06 UTC. The catalog and the 10/10 validation gate stayed fixed
across the network trials.

| Run | Runner / change | Result | Preserved evidence |
|---|---|---:|---|
| [34065153916](https://github.com/jcval94/AI-News-Daily/actions/runs/34065153916) | Ubuntu; initial runtime | Not a valid media trial: `ffmpeg` was absent | Workflow log |
| [34065237133](https://github.com/jcval94/AI-News-Daily/actions/runs/34065237133) | Ubuntu; runtime fixed | 0/10; YouTube bot challenge | Artifact `youtube-sample-clips-34065237133-1` |
| [34065600788](https://github.com/jcval94/AI-News-Daily/actions/runs/34065600788) | Ubuntu; embedded player client | 0/10; same challenge | Artifact `youtube-sample-clips-34065600788-1` |
| [34065747172](https://github.com/jcval94/AI-News-Daily/actions/runs/34065747172) | macOS 15; separate hosted fleet | 0/10; same challenge | Artifact `youtube-sample-clips-34065747172-1` |

The three uploaded artifacts contain the exact catalog snapshot, manifest, summary,
attribution scaffold, and sanitized per-video errors. They contain no MP4 files because
all ten requests were rejected before media URLs were issued. Artifacts expire after
seven days by design.

## Conclusion

The artifact packaging and deterministic checks work, but anonymous downloads from
the tested GitHub-hosted networks are not currently viable. A new run should use an
operator-controlled `self-hosted` runner on a network where YouTube access and the
download are authorized. The experiment deliberately does not add account cookies,
public relay services, VPN setup, or a bypass for YouTube's challenge.
