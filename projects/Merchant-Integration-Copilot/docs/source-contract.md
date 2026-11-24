# Source Contract

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

Upload a ZIP with `package.json` at the root or under one wrapping repository directory. Limits: **2 MB compressed and expanded**, **100 text files**, **256 KB per file**, and **150 archive entries**. Include TypeScript and an Express dependency. Exclude dependencies, `.git`, credentials, binary assets, and symlinks. Common secret patterns are rejected; this is not a general-purpose secret scanner. Remove all secrets before upload.

Each patch identifies the exact original source and patch digests. Apply only against that original snapshot:

```sh
git apply --check /path/to/ralio-BASE.patch
git apply /path/to/ralio-BASE.patch
```

Repository files and provider documents are untrusted data. The agent cannot run commands, access host files, edit the evaluator, or choose arbitrary documentation URLs. Its proposed TypeScript replacements are validated before storage.
