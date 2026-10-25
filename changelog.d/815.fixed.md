**Redshift Serverless works with an `aws login` profile.** botocore's login
credential provider needs `botocore[crt]`, which the `[redshift]` extra did not
install, so every command on such a profile failed with advice to configure the
AWS credential chain. The extra now installs `boto3[crt]`. If the dependency is
ever missing again, dex refuses with `reason: prerequisite` and botocore's own
message naming what to install, instead of the credential-chain advice.
