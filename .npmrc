# Supply-chain cooldown: never install a version published in the last 7 days.
# Maps internally to `before = now - 7 days`, so npm picks the newest version
# that is at least a week old. Applies to `npm install` and `npm audit fix`.
# A freshly-compromised release is most likely to be live (and not yet pulled)
# within its first days, so we skip that window.
min-release-age=7
