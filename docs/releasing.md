# Release checks

From the checkout, install development and small integration dependencies:

```sh
python -m pip install -e '.[dev,notifications,cast]'
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
node --check okabebot/web/app.js
bash -n scripts/start-linux.sh
python -m build
python scripts/check-release.py dist
```

The wheel contains the controller package, web UI and provider metadata. The
source distribution additionally includes Pi services/assets, setup skill,
examples, launcher and docs. The artifact audit checks required resources,
private state/config paths and common credential patterns without printing
credential contents. It complements review; it is not a guarantee that arbitrary
sensitive content is absent.

Keep `.env`, `.local`, device configs, tokens, audio/video captures, keys and
runtime databases out of Git and release archives. Review newly added files,
not only the tracked diff. Test an installed wheel from outside the source
checkout so editable imports cannot hide missing package resources.

CI runs the checks on Ubuntu with Python 3.10 and 3.12. A green local run does not
mean the remote workflow has run; that happens after a push/PR. Hardware, account
sign-in, actual speech volume and the complete Dell cutover require separate
live validation. Do not run two controllers against the same hardware to test
a package build.

## Documentation review

Enable local hooks with `git config core.hooksPath .githooks`. Every commit needs
a staged README update or an explanatory `README-Reviewed:` trailer. Changes to
hosting/device/service/integration files additionally need a staged
`docs/deployment.md` update or an explanatory `Topology-Reviewed:` trailer. A README
edit alone does not satisfy the inventory requirement. Review the README Mermaid
diagram as well; the hook cannot determine whether its nodes and edges are true.
See [deployment inventory](deployment.md) and [repository instructions](../AGENTS.md).
