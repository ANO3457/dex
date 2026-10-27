**The release workflow refuses a tag `prepare_release.sh` did not write.** It
re-runs the script on the tagged commit and fails on any difference, so every file
the script owns is checked, the plugin manifests and the `claude/` folder
included, rather than only the wrapper pins and the changelog section. A stable
tag is also refused unless every plugin manifest carries its version.
