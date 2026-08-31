# Pacotes de compatibilidade do Port Doctor

Esta pasta aceita pacotes opcionais de bibliotecas livres para ports antigos.
O Port Doctor não confia apenas no nome do arquivo: cada pacote precisa conter
um `pack.json`, licença declarada, hash SHA-256 e arquitetura de cada ELF.

Estrutura sugerida:

```text
compat-packs/
  ffmpeg4-aarch64/
    pack.json
    LICENSE.txt
    aarch64/
      libavcodec.so.58
```

Exemplo de `pack.json`:

```json
{
  "format": 1,
  "id": "ffmpeg4-aarch64",
  "license": "LGPL-2.1-or-later",
  "source": "URL do código-fonte e da compilação reproduzível",
  "files": [
    {
      "name": "libavcodec.so.58",
      "path": "aarch64/libavcodec.so.58",
      "architecture": "aarch64",
      "sha256": "64 caracteres hexadecimais"
    }
  ]
}
```

Não inclua bibliotecas proprietárias, drivers Mali/EGL/GLES, `libc`, o
carregador do sistema ou arquivos retirados de jogos comerciais. O pacote deve
acompanhar seus avisos de licença e a oferta de código-fonte quando exigida.
