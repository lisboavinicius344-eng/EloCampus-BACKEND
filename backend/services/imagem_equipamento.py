import base64
import binascii
import re


# A imagem é guardada no banco (coluna equipamentos.imagem). 3 MB cobre
# uma foto de celular reduzida; o frontend deve reduzir antes de enviar.
TAMANHO_MAXIMO = 3 * 1024 * 1024

DATA_URL = re.compile(
    r"^data:(?P<tipo>image/[a-z0-9.+-]+);base64,(?P<dados>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# O tipo é conferido pelos primeiros bytes do arquivo, não pelo que o
# cliente declarou. SVG fica de fora: pode conter scripts.
ASSINATURAS = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

MANTER = "manter"
REMOVER = "remover"
DEFINIR = "definir"


def _tipo_real(conteudo):
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"

    for assinatura, tipo in ASSINATURAS:
        if conteudo.startswith(assinatura):
            return tipo

    return None


def ler(dados):
    """Interpreta o campo "imagem" do corpo de POST/PUT de equipamento.

    Retorna (acao, conteudo, tipo):
    - campo ausente ou "" -> (MANTER, None, None)
    - null                -> (REMOVER, None, None)
    - data URL de imagem  -> (DEFINIR, bytes, "image/...")
    """
    if "imagem" not in dados:
        return MANTER, None, None

    valor = dados["imagem"]

    if valor is None:
        return REMOVER, None, None

    if not isinstance(valor, str):
        raise ValueError(
            "A imagem deve ser enviada como data URL "
            "(data:image/...;base64,...)."
        )

    valor = valor.strip()

    if not valor:
        return MANTER, None, None

    correspondencia = DATA_URL.match(valor)

    if correspondencia is None:
        raise ValueError(
            "A imagem deve ser enviada como data URL "
            "(data:image/...;base64,...)."
        )

    texto = re.sub(r"\s+", "", correspondencia.group("dados"))

    # Checa o tamanho antes de decodificar (base64 ocupa 4/3 do original).
    if len(texto) * 3 // 4 > TAMANHO_MAXIMO + 3:
        raise ValueError("A imagem deve ter no máximo 3 MB.")

    try:
        conteudo = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("A imagem enviada está corrompida.") from None

    if len(conteudo) > TAMANHO_MAXIMO:
        raise ValueError("A imagem deve ter no máximo 3 MB.")

    tipo = _tipo_real(conteudo)

    if tipo is None:
        raise ValueError(
            "Formato de imagem não suportado. Use JPG, PNG, WebP ou GIF."
        )

    return DEFINIR, conteudo, tipo
