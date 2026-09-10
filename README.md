<div align="center">

<!-- start title -->

# <img src=".github/ghadocs/branding.svg" width="60px" align="center" alt="branding<icon:activity color:blue>" /> GitHub Action: Agent Marketplace Versioner

<!-- end title -->
<!-- start badges -->

<a href="https://github.com/Jamie-BitFlight/agent-marketplace-versioner/releases/latest"><img src="https://img.shields.io/github/v/release/Jamie-BitFlight/agent-marketplace-versioner?display_name=tag&amp;sort=semver&amp;logo=github&amp;style=flat-square" alt="Release by tag" /></a><a href="https://github.com/Jamie-BitFlight/agent-marketplace-versioner/releases/latest"><img src="https://img.shields.io/github/release-date/Jamie-BitFlight/agent-marketplace-versioner?display_name=tag&amp;sort=semver&amp;logo=github&amp;style=flat-square" alt="Release by date" /></a><img src="https://img.shields.io/github/last-commit/Jamie-BitFlight/agent-marketplace-versioner?logo=github&amp;style=flat-square" alt="Commit" /><a href="https://github.com/Jamie-BitFlight/agent-marketplace-versioner/issues"><img src="https://img.shields.io/github/issues/Jamie-BitFlight/agent-marketplace-versioner?logo=github&amp;style=flat-square" alt="Open Issues" /></a><img src="https://img.shields.io/github/downloads/Jamie-BitFlight/agent-marketplace-versioner/total?logo=github&amp;style=flat-square" alt="Downloads" />

<!-- end badges -->

</div>

<!-- start description -->

Check or synchronize native agent marketplace versions with the shared CLI.

<!-- end description -->

Documentation: <https://bitflight.io/agent-marketplace-versioner/>.

<!-- start usage -->

```yaml
- uses: Jamie-BitFlight/agent-marketplace-versioner@v0.1.1
  with:
    # Description: CLI command to run (check, audit, sync, repair, or reconcile). Only
    # check and audit are read-only.
    #
    # Default: check
    command: ''

    # Description: Set to true with command sync to reconcile and version marketplace
    # catalogs.
    #
    # Default: false
    marketplace: ''

    # Description: Consumer Git repository directory.
    #
    # Default: ${{ github.workspace }}
    repository: ''

    # Description: Base revision for check. The checkout must contain this revision.
    #
    # Default: ${{ github.event.pull_request.base.sha || github.event.before }}
    base-ref: ''

    # Description: Candidate revision for check.
    #
    # Default: ${{ github.event.pull_request.head.sha || github.sha }}
    head-ref: ''
```

<!-- end usage -->

<!-- start inputs -->

| **Input** | **Description** | **Default** | **Required** |
|---|---|---|---|
| <b><code>command</code></b> | CLI command to run (check, audit, sync, repair, or reconcile). Only check and audit are read-only. | <code>check</code> | __false__ |
| <b><code>marketplace</code></b> | Set to true with command sync to reconcile and version marketplace catalogs. | <code>false</code> | __false__ |
| <b><code>repository</code></b> | Consumer Git repository directory. | <code>${{ github.workspace }}</code> | __false__ |
| <b><code>base-ref</code></b> | Base revision for check. The checkout must contain this revision. | <code>${{ github.event.pull_request.base.sha \|\| github.event.before }}</code> | __false__ |
| <b><code>head-ref</code></b> | Candidate revision for check. | <code>${{ github.event.pull_request.head.sha \|\| github.sha }}</code> | __false__ |

<!-- end inputs -->

<!-- start outputs -->



<!-- end outputs -->
