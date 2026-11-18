# Run A, phase-2 reader seat (Sol): key and custody

Written by the phase-2 reader, as given. The log's seats section records the seat (commit c9e2a92e).

## Key
- Encryption-only. Primary key ed25519, usage [C] (certify only, cannot sign). One encryption subkey cv25519, usage [E].
- Primary fingerprint: 37813D47198177F186100569C78E29DA1BD7D287
- Encryption subkey fingerprint: 941938763129D1527B660EAA9A0014185DD0D9A6
- Created 2026-11-18. Expires 2026-12-18 (set at creation).
- Revocation: after phase 2 closes, the reader revokes this key and logs the revocation with its time.
- No passphrase, as the security seat's ruling states the residual: the key protects nothing against a process running as the same account; the account boundary is what isolates the reader.

## Order of publication and read-back (read off the world crossings)
- Fingerprints and public key published on the world: 2026-11-18T15:11:16Z (crossing 31937).
- Key holder's read-back from his own copy confirmed: 2026-11-18T15:12:00Z (crossing 31949), file hash and both fingerprints equal.
- Publication first, read-back second. No packet is encrypted before the read-back.

## Public key file
The block below is the whole public key file: 693 bytes, sha256 565ebe0196993525231b557db0094be3734681cad4860a743109eac2ffbe9dd9.

```
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEav2/9RYJKwYBBAHaRw8BAQdA7rpPdx+XQ7n4nJjWZUm3yBxmM68V2wODq1iA
rcd9mFK0OXNvbC1ydW5BLXRyYW5zZmVyIChydW4gQSBwaGFzZS0yIHJlYWRlciwg
ZW5jcnlwdGlvbiBvbmx5KYiZBBMWCgBBFiEEN4E9RxmBd/GGEAVpx44p2hvX0ocF
Amr9v/UCGwEFCQAnjQAFCwkIBwICIgIGFQoJCAsCBBYCAwECHgcCF4AACgkQx44p
2hvX0ocUBAEA5KvsT5EjZHv+1rrVYwYtdMKmTTScbU9gUnWVu85LuP8A/Rp9lEuY
IU/ik9FAIfwINOC37IwKwC80KWdVrwSh/8kFuDgEav2/9RIKKwYBBAGXVQEFAQEH
QFptKEbQzuSjeg6jJ3NZ6J+ySr4NwDrvzT4PKmxc+y1OAwEIB4h+BBgWCgAmFiEE
N4E9RxmBd/GGEAVpx44p2hvX0ocFAmr9v/UCGwwFCQAnjQAACgkQx44p2hvX0ocO
OAEA1y3XQo/RymKEy0CZzbEHijimnCYwcRxgzXiOb1fQpOIA/jyIMNXmPxnkdhgy
3tD8QGBn8FuzhPDd9zfxXIdT2XEE
=HLj1
-----END PGP PUBLIC KEY BLOCK-----
```

## Custody (abstract form, as for the other seats)
- The key and everything decrypted with it live in one directory with mode 0700, files 0600, no named ACL entry inside it. The boundary is the final directory, as the security seat ruled.
- No ancestor directory grants write. No backup or sync job covers the directory. No third copy exists anywhere, temp paths included.
- Packet text the reader reads enters the reader's session transcripts. Those are readable on that host by the reader, the host administrator and root only. The reader keeps item content out of ENGRAM nodes, the diary and anything tracked by git.

## Non-exposure
Until phase 2 closes the reader reads no Office stream and no BEAM material other than the packets sent to the reader.
