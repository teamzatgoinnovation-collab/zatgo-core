#!/usr/bin/env python3
"""Create the ZatGo licence signing key -- run it ON THE ISSUER HOST, never on a customer server.

    python3 scripts/licence_keygen.py /secure/path/zatgo-licence-key.pem

Writes an Ed25519 private key (PEM, mode 600, never overwrites) and prints:
- the key id and the line to add to zatgo_core/licensing/keys/public_keys.json (commit + deploy it, so every
  site trusts licences signed with this key);
- the site_config line for the issuer site: "zg_licence_issuer_key": "<path>".

Keep the private key out of the bench's sites/ folder (backups copy it), out of every repository and out of any
licence file. Losing it means re-issuing licences with a new key; leaking it means anyone can sign licences --
then remove its public key from public_keys.json and re-issue.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CRYPTO = os.path.join(HERE, "..", "zatgo_core", "licensing", "crypto.py")


def _crypto():
    spec = importlib.util.spec_from_file_location("zatgo_licence_crypto", CRYPTO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    path = os.path.abspath(argv[1])
    if os.path.exists(path):
        print(f"refusing to overwrite {path}")
        return 1
    if f"{os.sep}sites{os.sep}" in path:
        print("refusing: keep the signing key outside any bench sites/ folder")
        return 1
    crypto = _crypto()
    key = crypto.generate_private_key()
    crypto.write_private_key(key, path)
    raw = crypto.raw_public(key.public_key())
    kid = crypto.key_id(raw)
    print(f"private key written: {path} (mode 600)")
    print(f"key id: {kid}")
    print("add to zatgo_core/licensing/keys/public_keys.json under \"keys\":")
    print(f"  {json.dumps(kid)}: {json.dumps(crypto.b64e(raw))}")
    print("issuer site_config:")
    print(f"  \"zg_licence_issuer_key\": {json.dumps(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
