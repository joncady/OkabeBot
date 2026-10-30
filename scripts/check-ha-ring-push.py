#!/usr/bin/env python3
"""Offline synthetic crypto check. Run inside the HA container after the backport.
No accounts, network requests, cameras or real push packets are used.
"""

import asyncio
import base64
import os
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
)
from http_ece import encrypt
from firebase_messaging.fcmpushclient import FcmPushClient
from firebase_messaging.proto.mcs_pb2 import DataMessageStanza


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


receiver = ec.generate_private_key(ec.SECP256R1())
sender = ec.generate_private_key(ec.SECP256R1())
secret = os.urandom(16)
salt = os.urandom(16)
credentials = {
    "keys": {
        "private": b64(receiver.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())),
        "secret": b64(secret),
    },
    "gcm": {"app_id": "synthetic"},
}
client = FcmPushClient.__new__(FcmPushClient)
client.credentials = credentials
client.callback = Mock()
client.callback_context = None
client._log_verbose = Mock()
client._log_warn_with_limit = Mock()
client._reset_error_count = Mock()
client.persistent_ids = []
client.config = SimpleNamespace(send_selective_acknowledgements=True)
client._send_selective_ack = AsyncMock()
client.input_stream_id = 0
client.last_input_stream_id_reported = 0

client._new_input_stream_id_available = Mock(return_value=False)
msg = DataMessageStanza(persistent_id="synthetic-valid")
for key, value in [
    (
        "crypto-key",
        "p256ecdsa=unused;dh="
        + b64(sender.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
    ),
    ("encryption", "rs=4096;salt=" + b64(salt)),
    ("subtype", "synthetic"),
]:
    msg.app_data.add(key=key, value=value)
msg.raw_data = encrypt(
    b'{"synthetic":true}',
    salt=salt,
    private_key=sender,
    dh=receiver.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint),
    version="aesgcm",
    auth_secret=secret,
)


async def main():
    await client._handle_message(msg)
    assert client.callback.call_args.args[0] == {"synthetic": True}
    msg.app_data[0].value = "dh=not-a-valid-key"
    msg.persistent_id = "synthetic-invalid"
    await client._handle_message(msg)
    assert client.callback.call_count == 1
    assert client._log_warn_with_limit.call_count == 1
    assert client._send_selective_ack.await_count == 2
    print(
        "Synthetic encrypted push decrypted; malformed packet skipped and acknowledged; listener dispatch returned normally"
    )


asyncio.run(main())
