**The documentation site keeps the four previous minor releases readable.** A
version switcher on docs.exmergo.com/dex lists the latest minor release, marked
Latest and kept at the routes every shared link already uses, and each earlier
one at `/dex/vX.Y/`. Every older page opens with a notice naming the exact
release it shows and linking to the same page in the latest docs. Each older
version is rebuilt from the newest patch tag of its minor, so it shows that
release's references, changelog and CLI, and is kept out of search so a search
always lands on the latest docs. A patch release only updates the latest
version.
