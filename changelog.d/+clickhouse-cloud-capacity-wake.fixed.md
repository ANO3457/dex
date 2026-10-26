**ClickHouse Cloud's capacity probe waits out a waking service.** A service
resuming from idle answers `clusterAllReplicas` in part, or not at all, for a few
seconds, and every billed command refused with advice to grant access the
identity already held. The probe now re-reads for about 15 seconds before
refusing, the refusal names the server's own reason, and a denied grant still
refuses at once.
