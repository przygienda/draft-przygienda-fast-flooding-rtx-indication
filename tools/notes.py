#!/usr/bin/env python3
"""Private working notes for this draft, encrypted into the public repo.

    ciphertext  .github/private-notes.md.enc   (committed, public)
    plaintext   ~/.copilot/instructions/rtx-draft.instructions.md
                                               (never inside the repo)

The plaintext path is deliberately outside the working tree. No gitignore
rule stands between the notes and a `git add -A`, because the notes are
never in the tree to begin with.

Key handling
------------
The key is derived from your SSH key, via the running ssh-agent. We ask the
agent to sign a fixed challenge. RSA PKCS#1 v1.5 and Ed25519 signatures are
deterministic, so the same key over the same challenge always yields the
same bytes. Those bytes are hashed into an encryption key and a separate
MAC key.

Note carefully: the input is a *signature*, which only the private key can
produce. It is emphatically not the key fingerprint. A fingerprint is a
public identifier, published at https://github.com/<user>.keys and present
in authorized_keys on every host you log into. Using one as a passphrase
would let anyone decrypt this file.

Consequences, all intended:

  * Nothing secret is on disk. The repo holds ciphertext; the key material
    lives only inside the agent.
  * No passphrase is typed, so none can leak into shell history, an
    environment variable, an argv entry visible in /proc, or an agent
    transcript.
  * It works unchanged on every machine whose agent holds the same SSH key.
  * It fails closed. No agent, or the wrong key, means no access.
  * Losing the SSH key loses the notes. They are working notes, not the
    draft, so that is an acceptable trade.

The challenge is a fixed constant. We never sign file-derived bytes, so a
tampered ciphertext cannot steer the derivation.

Format: magic || HMAC-SHA256(mac_key, body) || body, where body is an
OpenSSL "Salted__" AES-256-CBC stream. Encrypt-then-MAC, so a wrong key or
a tampered file is rejected before any plaintext is produced.

Only python3, openssl and a running ssh-agent are required. No GPG.

Usage:  tools/notes.py {decrypt|encrypt|status|diff}
"""

import base64
import hashlib
import hmac
import os
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile

CHALLENGE = b"rtx-draft-private-notes/v1 key-derivation"
MAGIC = b"RTXNOTES\x01"
PBKDF2_ITER = 600000
SSH_FP = os.environ.get("RTX_NOTES_SSH_FP", "SHA256:I0IUofqFqCTUeasvsQcEX9DL5Bu66JTmmOxF6QB58qw")

REPO = pathlib.Path(__file__).resolve().parent.parent
CIPHER = REPO / ".github" / "private-notes.md.enc"
PLAIN = pathlib.Path.home() / ".copilot" / "instructions" / "rtx-draft.instructions.md"

SSH_AGENT_RSA_SHA2_256 = 2


def die(msg):
    print(f"notes.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _str(b):
    return struct.pack(">I", len(b)) + b


class Agent:
    """Minimal ssh-agent client (RFC 4251 framing, draft-miller-ssh-agent)."""

    def __init__(self):
        path = os.environ.get("SSH_AUTH_SOCK")
        if not path:
            die("SSH_AUTH_SOCK is not set; start ssh-agent and load your key")
        self.sock = socket.socket(socket.AF_UNIX)
        try:
            self.sock.connect(path)
        except OSError as exc:
            die(f"cannot reach ssh-agent at {path}: {exc}")

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                die("ssh-agent closed the connection")
            buf += chunk
        return buf

    def _round_trip(self, payload):
        self.sock.sendall(_str(payload))
        (length,) = struct.unpack(">I", self._read(4))
        return self._read(length)

    def identities(self):
        reply = self._round_trip(bytes([11]))
        if not reply or reply[0] != 12:
            die("ssh-agent refused to list identities")
        off = 1
        (count,) = struct.unpack(">I", reply[off:off + 4])
        off += 4
        out = []
        for _ in range(count):
            (n,) = struct.unpack(">I", reply[off:off + 4])
            off += 4
            blob = reply[off:off + n]
            off += n
            (n,) = struct.unpack(">I", reply[off:off + 4])
            off += 4
            comment = reply[off:off + n].decode("utf-8", "replace")
            off += n
            out.append((blob, comment))
        return out

    def sign(self, blob, data):
        payload = (bytes([13]) + _str(blob) + _str(data)
                   + struct.pack(">I", SSH_AGENT_RSA_SHA2_256))
        reply = self._round_trip(payload)
        if not reply or reply[0] != 14:
            die("ssh-agent refused to sign; is the key loaded and unlocked?")
        (n,) = struct.unpack(">I", reply[1:5])
        return reply[5:5 + n]


def openssh_fingerprint(blob):
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def derive_keys():
    """Return (enc_passphrase, mac_key) derived from an ssh-agent signature."""
    agent = Agent()
    ids = agent.identities()
    if not ids:
        die("ssh-agent holds no identities; run ssh-add")

    chosen = None
    for blob, comment in ids:
        if openssh_fingerprint(blob) == SSH_FP:
            chosen = (blob, comment)
            break
    if chosen is None:
        loaded = "\n  ".join(f"{openssh_fingerprint(b)}  {c}" for b, c in ids)
        die(f"key {SSH_FP} is not loaded. Agent currently holds:\n  {loaded}")

    blob, _ = chosen
    sig = agent.sign(blob, CHALLENGE)
    if len(sig) < 32:
        die("implausibly short signature from ssh-agent")

    # Independent subkeys by domain separation. The signature is the only
    # input, and only the private key can produce it.
    enc = base64.b64encode(hashlib.sha512(b"rtx-notes/v1/enc\x00" + sig).digest())
    mac = hashlib.sha256(b"rtx-notes/v1/mac\x00" + sig).digest()
    return enc, mac


def _openssl(args, passphrase, data):
    """Run openssl with the passphrase on an inherited fd, never in argv."""
    read_fd, write_fd = os.pipe()
    os.set_inheritable(read_fd, True)
    try:
        proc = subprocess.Popen(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2",
             "-iter", str(PBKDF2_ITER), "-md", "sha512",
             "-pass", f"fd:{read_fd}"] + args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, pass_fds=(read_fd,),
        )
        os.close(read_fd)
        read_fd = -1
        os.write(write_fd, passphrase + b"\n")
        os.close(write_fd)
        write_fd = -1
        out, err = proc.communicate(data)
        return proc.returncode, out, err
    finally:
        if read_fd >= 0:
            os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


def cmd_encrypt():
    if not PLAIN.exists():
        die(f"no plaintext at {PLAIN}; run 'decrypt' first")
    enc_pass, mac_key = derive_keys()
    rc, body, err = _openssl(["-salt"], enc_pass, PLAIN.read_bytes())
    if rc != 0:
        die(f"openssl encrypt failed: {err.decode(errors='replace').strip()}")
    tag = hmac.new(mac_key, MAGIC + body, hashlib.sha256).digest()
    CIPHER.parent.mkdir(parents=True, exist_ok=True)
    CIPHER.write_bytes(MAGIC + tag + body)
    size = CIPHER.stat().st_size
    print(f"encrypted -> {CIPHER.relative_to(REPO)}  ({size} bytes)  [commit this]")


def _decrypt_bytes():
    if not CIPHER.exists():
        die(f"no ciphertext at {CIPHER}")
    raw = CIPHER.read_bytes()
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 32:
        die(f"{CIPHER.name} is not a notes container")
    tag, body = raw[len(MAGIC):len(MAGIC) + 32], raw[len(MAGIC) + 32:]

    enc_pass, mac_key = derive_keys()
    expect = hmac.new(mac_key, MAGIC + body, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        die("authentication failed: wrong SSH key, or the file was modified. "
            "Nothing was decrypted.")

    rc, out, err = _openssl(["-d"], enc_pass, body)
    if rc != 0:
        die(f"openssl decrypt failed: {err.decode(errors='replace').strip()}")
    return out


def cmd_decrypt():
    data = _decrypt_bytes()
    PLAIN.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(PLAIN.parent), prefix=".notes-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, PLAIN)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print(f"decrypted -> {PLAIN}  ({len(data)} bytes)")


def cmd_status():
    print(f"ssh key    {SSH_FP}")
    try:
        ids = Agent().identities()
        held = any(openssh_fingerprint(b) == SSH_FP for b, _ in ids)
        print(f"agent      {len(ids)} identities loaded; required key {'present' if held else 'MISSING'}")
    except SystemExit:
        print("agent      unavailable")
    for label, path in (("plaintext ", PLAIN), ("ciphertext", CIPHER)):
        if path.exists():
            st = path.stat()
            print(f"{label} {path}  {st.st_size} bytes")
        else:
            print(f"{label} {path}  ABSENT")
    if PLAIN.exists() and CIPHER.exists():
        if PLAIN.stat().st_mtime > CIPHER.stat().st_mtime:
            print("\nSTALE: plaintext is newer than ciphertext. Run: tools/notes.py encrypt")
            return 1
    return 0


def cmd_diff():
    if not PLAIN.exists():
        die(f"no plaintext at {PLAIN}")
    current = _decrypt_bytes()
    if current == PLAIN.read_bytes():
        print("ciphertext is up to date")
        return 0
    with tempfile.NamedTemporaryFile("wb", suffix=".committed.md") as fh:
        fh.write(current)
        fh.flush()
        subprocess.run(["diff", "-u", fh.name, str(PLAIN)])
    return 1


def main():
    # Never let plaintext land inside the repository.
    if REPO in PLAIN.resolve().parents:
        die("plaintext path resolves inside the repo; refusing")

    commands = {
        "decrypt": cmd_decrypt,
        "encrypt": cmd_encrypt,
        "status": cmd_status,
        "diff": cmd_diff,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        die("usage: tools/notes.py {decrypt|encrypt|status|diff}")
    raise SystemExit(commands[sys.argv[1]]() or 0)


if __name__ == "__main__":
    main()
