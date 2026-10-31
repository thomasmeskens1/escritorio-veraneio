"""Segredos no backup diário, criptografados (pedido do Thomas, 30/10/2026).

As senhas dos usuários (usuarios.json), os tokens de login e o .env do projeto entram no zip do Drive só
criptografados, no arquivo segredos.cripto. O PC guarda apenas a chave PÚBLICA (backend/dados/backup_chave_publica.pem):
com ela o backup tranca, mas não abre. A chave PRIVADA fica na pasta dos backups no Drive, protegida por uma
frase-senha que só o Thomas sabe; sem a frase, nem quem tiver acesso ao Drive (ou ao PC) abre os segredos.

Uso (no PC, na pasta do projeto):
  python scripts/segredos_backup.py gerar-chave              # uma vez: pede a frase-senha e cria as duas chaves
  python scripts/segredos_backup.py restaurar backup.zip     # pede a frase e extrai os segredos numa pasta

Formato: RSA-OAEP (3072 bits) tranca uma chave AES-256-GCM aleatória, que tranca um zip com os arquivos.
"""

import getpass
import io
import os
import struct
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "backend" / "dados"
CHAVE_PUBLICA = DADOS / "backup_chave_publica.pem"
DESTINO = Path(os.getenv("ESCRITORIO_BACKUP", r"G:\Meu Drive\Backups Escritório Veraneio"))
CHAVE_PRIVADA = DESTINO / "backup_chave_privada.pem"
ARQUIVO_NO_ZIP = "segredos.cripto"
ASSINATURA = b"CVSEG1"
FRASE_MINIMA = 16


def _oaep():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def trancar(arquivos: dict[str, bytes], publica_pem: bytes) -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zip_interno:
        for nome, conteudo in arquivos.items():
            zip_interno.writestr(nome, conteudo)
    chave, nonce = AESGCM.generate_key(256), os.urandom(12)
    embrulhada = serialization.load_pem_public_key(publica_pem).encrypt(chave, _oaep())
    return (ASSINATURA + struct.pack(">H", len(embrulhada)) + embrulhada + nonce
            + AESGCM(chave).encrypt(nonce, pacote.getvalue(), ASSINATURA))


def abrir(dados: bytes, privada_pem: bytes, frase: str) -> dict[str, bytes]:
    """Levanta ValueError com a frase errada ou com o arquivo alterado."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not dados.startswith(ASSINATURA):
        raise ValueError("arquivo de segredos desconhecido")
    privada = serialization.load_pem_private_key(privada_pem, password=frase.encode())
    inicio = len(ASSINATURA)
    tamanho = struct.unpack(">H", dados[inicio:inicio + 2])[0]
    embrulhada = dados[inicio + 2:inicio + 2 + tamanho]
    nonce = dados[inicio + 2 + tamanho:inicio + 14 + tamanho]
    from cryptography.exceptions import InvalidTag

    try:
        chave = privada.decrypt(embrulhada, _oaep())
        conteudo = AESGCM(chave).decrypt(nonce, dados[inicio + 14 + tamanho:], ASSINATURA)
    except InvalidTag as erro:
        raise ValueError("segredos alterados ou de outra chave") from erro
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zip_interno:
        return {nome: zip_interno.read(nome) for nome in zip_interno.namelist()}


def gerar_chaves(frase: str) -> tuple[bytes, bytes]:
    """(pública, privada protegida pela frase), em PEM."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    publica = privada.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
    protegida = privada.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.BestAvailableEncryption(frase.encode()))
    return publica, protegida


def _gerar_chave() -> None:
    if CHAVE_PRIVADA.exists() or CHAVE_PUBLICA.exists():
        sys.exit(f"Já existe chave ({CHAVE_PRIVADA} ou {CHAVE_PUBLICA}). Trocar a chave deixa os backups antigos "
                 "presos à frase antiga: apague as duas de propósito antes de gerar outra.")
    print(f"Escolha uma frase-senha com pelo menos {FRASE_MINIMA} caracteres (ex.: quatro palavras soltas).")
    print("Guarde-a fora do PC: sem ela, os segredos do backup não abrem.")
    frase = getpass.getpass("Frase-senha: ")
    if len(frase) < FRASE_MINIMA:
        sys.exit("Frase curta demais.")
    if getpass.getpass("Repita a frase: ") != frase:
        sys.exit("As frases não conferem.")
    publica, privada = gerar_chaves(frase)
    DESTINO.mkdir(parents=True, exist_ok=True)
    CHAVE_PRIVADA.write_bytes(privada)
    CHAVE_PUBLICA.write_bytes(publica)
    print(f"Pronto. Chave pública: {CHAVE_PUBLICA}\nChave privada (protegida pela frase): {CHAVE_PRIVADA}")
    print("A partir do próximo backup diário, os segredos entram criptografados.")


def _restaurar(backup: Path) -> None:
    with zipfile.ZipFile(backup) as pacote:
        dados = pacote.read(ARQUIVO_NO_ZIP)
    privada = Path(sys.argv[3]) if len(sys.argv) > 3 else CHAVE_PRIVADA
    try:
        arquivos = abrir(dados, privada.read_bytes(), getpass.getpass("Frase-senha: "))
    except ValueError:
        sys.exit("Frase errada (ou o arquivo foi alterado).")
    saida = DADOS / "segredos_restaurados"
    for nome, conteudo in arquivos.items():
        alvo = saida / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
    print(f"{len(arquivos)} arquivo(s) em {saida} (caminhos a partir da pasta do projeto). Copie para o lugar e "
          "apague essa pasta depois.")


if __name__ == "__main__":
    if sys.argv[1:2] == ["gerar-chave"]:
        _gerar_chave()
    elif sys.argv[1:2] == ["restaurar"] and len(sys.argv) > 2:
        _restaurar(Path(sys.argv[2]))
    else:
        sys.exit(__doc__)
