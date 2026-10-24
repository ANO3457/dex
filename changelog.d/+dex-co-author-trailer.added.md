**`transform apply` hands back a co-author trailer that credits Dex.** dex never
commits: the agent or person driving it does, so a commit of files dex wrote
carried no sign of it. An apply that writes at least one file now returns
`data.commit_trailer`, the line `Co-authored-by: Dex <dex@exmergo.com>`, and the
three skills tell the agent to end the message of the commit carrying those
files with it, after a blank line. GitHub credits the trailer to the
[dex-app-ai](https://github.com/dex-app-ai) account, so Dex appears among a
repository's contributors once that commit is on its default branch. The typed
API carries it as `ApplyResult.commit_trailer`. An apply that wrote nothing, or
stopped at `needs_confirmation`, returns no trailer. To leave the credit out,
remove the line from the commit message.
