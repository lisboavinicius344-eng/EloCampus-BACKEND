import base64
import binascii
import io
import re
import warnings

from PIL import Image, ImageOps


# A foto guardada no banco tem no máximo 200 KB. Fotos maiores (até
# 10 MB, como as de celular) são reduzidas e comprimidas aqui.
TAMANHO_MAXIMO = 200 * 1024
TAMANHO_MAXIMO_ENVIO = 10 * 1024 * 1024

# Maior lado da foto guardada, e o menor a que se chega reduzindo.
LADO_MAXIMO = 1280
LADO_MINIMO = 240
QUALIDADES = (85, 75, 65, 55, 45)

# Imagens com mais pixels que isso são recusadas antes de abrir
# (protege contra arquivos pequenos que se expandem para gigabytes).
PIXELS_MAXIMOS = 40_000_000

FORMATOS = {"PNG", "JPEG", "WEBP", "GIF"}
TIPOS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}

DATA_URL = re.compile(
    r"^data:(?P<tipo>image/[a-z0-9.+-]+);base64,(?P<dados>.+)$",
    re.IGNORECASE | re.DOTALL,
)

MANTER = "manter"
REMOVER = "remover"
DEFINIR = "definir"

ERRO_FORMATO = "Formato de imagem não suportado. Use JPG, PNG, WebP ou GIF."


def ler(dados):
    """Interpreta o campo "imagem" do corpo de POST/PUT de equipamento.

    Retorna (acao, conteudo, tipo):
    - campo ausente ou "" -> (MANTER, None, None)
    - null                -> (REMOVER, None, None)
    - data URL de imagem  -> (DEFINIR, bytes de até 200 KB, "image/...")
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
    if len(texto) * 3 // 4 > TAMANHO_MAXIMO_ENVIO + 3:
        raise ValueError("A imagem enviada deve ter no máximo 10 MB.")

    try:
        conteudo = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("A imagem enviada está corrompida.") from None

    if len(conteudo) > TAMANHO_MAXIMO_ENVIO:
        raise ValueError("A imagem enviada deve ter no máximo 10 MB.")

    conteudo, tipo = comprimir(conteudo)
    return DEFINIR, conteudo, tipo


def comprimir(conteudo):
    """Devolve (bytes, tipo) da imagem com no máximo TAMANHO_MAXIMO.

    O formato é conferido pelo conteúdo, não pelo que o cliente declarou
    (SVG e outros ficam de fora). Imagens que já cabem no limite são
    guardadas como vieram; as demais viram JPEG, reduzidas aos poucos
    até caber.
    """
    imagem = _abrir(conteudo)

    if len(conteudo) <= TAMANHO_MAXIMO and not _precisa_girar(imagem):
        return conteudo, TIPOS[imagem.format]

    imagem = _preparar(imagem)
    lado = min(LADO_MAXIMO, max(imagem.size))

    while True:
        reduzida = imagem.copy()
        reduzida.thumbnail((lado, lado), Image.Resampling.LANCZOS)

        for qualidade in QUALIDADES:
            saida = io.BytesIO()
            reduzida.save(
                saida,
                format="JPEG",
                quality=qualidade,
                optimize=True,
                progressive=True,
            )

            if saida.tell() <= TAMANHO_MAXIMO:
                return saida.getvalue(), "image/jpeg"

        if lado <= LADO_MINIMO:
            raise ValueError(
                "Não foi possível reduzir a imagem para 200 KB. "
                "Tente outra foto."
            )

        lado = max(LADO_MINIMO, int(lado * 0.75))


def _abrir(conteudo):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            imagem = Image.open(io.BytesIO(conteudo))

            if imagem.format not in FORMATOS:
                raise ValueError(ERRO_FORMATO)

            largura, altura = imagem.size

            if largura * altura > PIXELS_MAXIMOS:
                raise ValueError(
                    "A imagem tem resolução grande demais. Use uma foto "
                    "de até 40 megapixels."
                )

            imagem.load()

    except ValueError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValueError(
            "A imagem tem resolução grande demais. Use uma foto de até "
            "40 megapixels."
        ) from None
    except Exception:
        raise ValueError(ERRO_FORMATO) from None

    return imagem


def _precisa_girar(imagem):
    # Fotos de celular guardam a rotação no EXIF; aplicamos para a foto
    # não aparecer deitada no navegador.
    try:
        return imagem.getexif().get(0x0112, 1) not in (1, None)
    except Exception:
        return False


def _preparar(imagem):
    imagem = ImageOps.exif_transpose(imagem)

    # JPEG não tem transparência: o fundo transparente fica branco.
    if imagem.mode in ("RGBA", "LA") or (
        imagem.mode == "P" and "transparency" in imagem.info
    ):
        imagem = imagem.convert("RGBA")
        fundo = Image.new("RGB", imagem.size, (255, 255, 255))
        fundo.paste(imagem, mask=imagem.getchannel("A"))
        return fundo

    return imagem.convert("RGB")
