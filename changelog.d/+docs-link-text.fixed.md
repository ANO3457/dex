**Links whose text is code keep their text on the documentation site.** A link
written as ``[`semantic-layer.md`](semantic-layer.md)`` was published with an
invisible placeholder where its text should be, on 66 links across the
reference pages, because the code span inside the link text was never put back.
The build now restores nested spans, and refuses any page that contains a
control character, so text lost this way cannot ship silently again.
