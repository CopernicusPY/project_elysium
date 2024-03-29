from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import fingerprint
import base64
import logging
import socket
import argparse

logging.basicConfig(level=logging.INFO)
parser = argparse.ArgumentParser()
parser.add_argument("--host", type=str, required=False, default="127.0.0.1")
parser.add_argument("--port", type=int, required=False, default=44454)

args = parser.parse_args()


def handle_serialized_params(
    serialized_parameters: bytes,
) -> tuple[dh.DHPrivateKey, dh.DHPublicKey]:
    """
    Takes serialized Diffie-Hellman parameters and generates a private and public key pair.

    Args:
        serialized_parameters (bytes): The serialized Diffie-Hellman parameters.

    Returns:
        tuple[dh.DHPrivateKey, dh.DHPublicKey]: A tuple containing the generated private and public keys.
    """
    parameters = serialization.load_pem_parameters(
        serialized_parameters, backend=default_backend()
    )
    private_key = parameters.generate_private_key()
    public_key = private_key.public_key()
    p_fingerprint = fingerprint.Fingerprint(hashes.SHA256(), default_backend())
    p_fingerprint.key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    logging.info(
        f"[*] Your public key's fingerprint:\n{p_fingerprint.bubble_babble()}"
    )
    return private_key, public_key


def handle_key_exchange(
    client: socket.socket, private_key: dh.DHPrivateKey, public_key: dh.DHPublicKey
) -> bytes:
    """
    Handles the key exchange process.

    Args:
        client (socket.socket): Client socket
        private_key (dh.DHPrivateKey): The private key to use when getting the shared key
        public_key (dh.DHPublicKey): The public key to send to the server
    """
    try:
        client.sendall(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        logging.info("[*] Sent public key to server")

        server_public_key = client.recv(1024)
        logging.info("[*] Received server's public key")

        # Authenticate party's public key fingerprint (SHA-256)
        fingerprint_ = fingerprint.Fingerprint(hashes.SHA256(), default_backend())
        fingerprint_.key = server_public_key
        fingerprint_.verify_fingerprint()

        server_public_key = serialization.load_pem_public_key(
            server_public_key, backend=default_backend()
        )
        shared_key = private_key.exchange(server_public_key)

        return shared_key
    except socket.error as e:
        logging.error(f"[>w<] {e}")
        logging.critical(
            "[!!!] There is a **possibility** the handshake was hijacked.\n(Please do not take this message too seriously)"
        )

def verify_keys(socket: socket.socket, shared_key: bytes):
    key_fingerprint = fingerprint.Fingerprint(
        hashes.SHA256(),
        backend=default_backend()
    )
    key_fingerprint.key = shared_key
    key_fingerprint = key_fingerprint.bubble_babble().encode()
    socket.sendall(key_fingerprint)
    c_key_fingerprint = socket.recv(1024)
    print(key_fingerprint)
    print(c_key_fingerprint)


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
    try:
        client.connect((args.host, args.port))
        logging.info("[*] Connected to server")

        serialized_parameters = client.recv(512)
        logging.info("[*] Received DH parameters")

        private_key, public_key = handle_serialized_params(serialized_parameters)
        logging.info("[*] Loaded parameters and generated key pair")

        shared_key = handle_key_exchange(client, private_key, public_key)
        verify_keys(client, shared_key)
        logging.info("[*] Successfull exchange")

        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            info=None,
            salt=None,
        ).derive(shared_key)

    except socket.error as e:
        logging.error(f"[>w<] {e}")
    except ConnectionRefusedError:
        logging.error("[>w<] Connection refused. Exiting")
        exit(1)
