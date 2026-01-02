# Antigravity Command Research

## Findings

- **Security Model**: Antigravity utilizes an **allowlist** approach rather than
  a denylist.
- **Configuration**: The setting `antigravityAgent.trustedCommands` in
  `~/Library/Application Support/Antigravity/User/settings.json` controls which
  commands are permitted.
- **Default Behavior**: Any command not explicitly listed in the
  `trustedCommands` array is treated as untrusted/restricted.
- **Exploration**: Searched application settings, extension manifests
  (`package.json`), and the product configuration (`product.json`) for "deny",
  "block", or "blacklist" and found no evidence of a dedicated denylist.

## TODO

- [ ] Investigate if there are any hardcoded command restrictions within the
      binary or core extensions that cannot be overridden by `trustedCommands`.
