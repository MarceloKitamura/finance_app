"""
Parsers de extrato bancário — CSV e OFX — usando SÓ a biblioteca padrão.

Fiel à filosofia do projeto (que evita dependências e usa urllib para a
Groq), aqui não usamos `ofxparse` nem `pandas`: CSV sai do módulo `csv` e
OFX é lido com regex, já que o corpo do OFX é SGML simples e previsível
(uma lista de blocos <STMTTRN>).

A separação é proposital:
- ESTES parsers só EXTRAEM dados crus (cabeçalhos/linhas, ou transações
  estruturadas). Não conhecem o banco nem as regras do app.
- O ImportService é quem normaliza, sugere categoria e detecta duplicatas.
"""

import csv
import io
import re
from typing import List, Optional


# ───────────────────────────────────────────────────────────
# CSV
# ───────────────────────────────────────────────────────────

def parse_csv(text: str) -> dict:
    """Lê um CSV e devolve {headers, rows, delimiter}.

    Detecta o separador automaticamente (vírgula, ponto-e-vírgula ou tab)
    com csv.Sniffer; se falhar, cai no ';' (comum em bancos brasileiros).
    O MAPEAMENTO de quais colunas são data/valor/descrição é decidido depois
    (no frontend), porque varia de banco para banco.
    """
    text = (text or "").lstrip("﻿")  # remove BOM se houver
    if not text.strip():
        return {"headers": [], "rows": [], "delimiter": ","}

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = [row for row in reader if any((c or "").strip() for c in row)]
    if not all_rows:
        return {"headers": [], "rows": [], "delimiter": delimiter}

    headers = [h.strip() for h in all_rows[0]]
    rows = [r for r in all_rows[1:]]
    return {"headers": headers, "rows": rows, "delimiter": delimiter}


def parse_amount(raw: str) -> Optional[float]:
    """Converte um valor de extrato em float (aceita formatos BR e US).

    Exemplos aceitos: "1.234,56" (BR), "1,234.56" (US), "-50.00", "R$ 80,00".
    Devolve None se não der para interpretar.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Remove tudo que não for dígito, sinal, vírgula ou ponto.
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s or s in ("-", ".", ","):
        return None

    # Decide o separador decimal pelo ÚLTIMO símbolo que aparece.
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma > last_dot:
        # Vírgula é o decimal (formato BR): tira os pontos de milhar.
        s = s.replace(".", "").replace(",", ".")
    else:
        # Ponto é o decimal (formato US): tira as vírgulas de milhar.
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date_flexible(raw: str) -> Optional[str]:
    """Converte uma data de extrato para ISO (YYYY-MM-DD).

    Aceita dd/mm/aaaa, dd-mm-aaaa, aaaa-mm-dd e o compacto aaaammdd (OFX).
    Devolve None se não reconhecer.
    """
    if not raw:
        return None
    s = str(raw).strip()
    # OFX costuma anexar hora/timezone: "20240115120000[-3:GMT]". Cortamos no
    # "[" para não confundir o hífen do fuso com um separador de data.
    s = s.split("[", 1)[0].strip()

    # Compacto do OFX: 20240115 (ou com hora 20240115120000). Só quando a
    # string COMEÇA com 8+ dígitos seguidos (sem separador no meio).
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:\d+)?$", s)
    if m:
        y, mo, d = m.groups()
        return _safe_iso(y, mo, d)

    # ISO: 2024-01-15.
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return _safe_iso(y, mo, d)

    # BR: 15/01/2024 ou 15-01-2024.
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", s)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        return _safe_iso(y, mo, d)

    return None


def _safe_iso(y: str, mo: str, d: str) -> Optional[str]:
    """Monta YYYY-MM-DD validando o intervalo dos campos."""
    try:
        yi, mi, di = int(y), int(mo), int(d)
        if not (1 <= mi <= 12 and 1 <= di <= 31):
            return None
        return f"{yi:04d}-{mi:02d}-{di:02d}"
    except ValueError:
        return None


# ───────────────────────────────────────────────────────────
# Parcelamento (detecção na descrição da fatura)
# ───────────────────────────────────────────────────────────
# Faturas de cartão costumam anexar a parcela à descrição da compra:
#   "NETFLIX.COM 03/12", "MAGALU PARC 02/10", "LOJA X PARCELA 3 DE 12".
# Detectar isso permite lançar a compra PARCELADA (com as parcelas futuras),
# em vez de tratar cada linha como uma compra à vista isolada.
#
# Como ESTES parsers não conhecem regra de negócio, aqui só EXTRAÍMOS a
# informação (base + nº/total da parcela). Quem decide o que fazer com ela
# (gerar faturas futuras, deduplicar) é o ImportService/TransactionService.

# Cartão parcela em no máximo ~72x. Acima disso é quase certo que "N/M" é uma
# data (ex.: 12/2025) e não uma parcela — limite defensivo contra falso positivo.
_MAX_INSTALLMENTS = 72

# "N/M" (com ou sem zeros à esquerda). É ambíguo com data, então só vale como
# parcela com a palavra "parc"/"parcela" perto OU no fim da descrição.
_PARC_SLASH_RE = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})")
# "N de M" (ex.: "3 de 12", "parcela 3 de 12") — sinal forte, pouco ambíguo.
_PARC_DE_RE = re.compile(r"\b(\d{1,2})\s+de\s+(\d{1,2})\b", re.IGNORECASE)


def parse_installment(description: str) -> Optional[dict]:
    """Detecta parcela "N/M" (ou "N de M") na descrição de uma linha de fatura.

    Devolve {"base", "installment_no", "installments_total"} quando reconhece
    uma parcela plausível (1 <= N <= M e 2 <= M <= 72); senão, None. `base` é a
    descrição sem o trecho da parcela (ex.: "NETFLIX.COM").

    Conservador de propósito: como "03/12" também pode ser uma data, a forma
    com barra só é aceita quando vem com "parc"/"parcela" por perto OU no FIM
    da descrição (padrão das faturas). O usuário ainda revê tudo na prévia.
    """
    if not description:
        return None
    text = " ".join(str(description).split())

    # 1) "N de M" — aceito sempre (sinal forte).
    m = _PARC_DE_RE.search(text)
    if m:
        result = _installment_from_match(text, m)
        if result:
            return result

    # 2) "N/M" — só com palavra-chave por perto ou no fim da linha.
    for m in _PARC_SLASH_RE.finditer(text):
        n, total = int(m.group(1)), int(m.group(2))
        if not (1 <= n <= total and 2 <= total <= _MAX_INSTALLMENTS):
            continue
        before = text[max(0, m.start() - 9):m.start()]
        has_keyword = bool(re.search(r"parc", before, re.IGNORECASE))
        at_end = text[m.end():].strip(" )].-") == ""
        if has_keyword or at_end:
            result = _installment_from_match(text, m)
            if result:
                return result
    return None


def _installment_from_match(text: str, m: "re.Match") -> Optional[dict]:
    """Valida o casamento e monta o dict de parcela (ou None)."""
    n, total = int(m.group(1)), int(m.group(2))
    if not (1 <= n <= total and 2 <= total <= _MAX_INSTALLMENTS):
        return None
    # Remove o trecho da parcela e a palavra "parc/parcela" que o antecede.
    base = (text[:m.start()] + " " + text[m.end():])
    base = re.sub(r"\bparc(?:ela)?\.?\s*$", "", base.strip(), flags=re.IGNORECASE)
    base = " ".join(base.strip(" -–—.,/").split())
    return {
        "base": base or text,
        "installment_no": n,
        "installments_total": total,
    }


# ───────────────────────────────────────────────────────────
# OFX
# ───────────────────────────────────────────────────────────

# Captura cada bloco de transação do OFX.
_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)


def _ofx_tag(block: str, tag: str) -> str:
    """Extrai o valor de uma tag SGML do OFX (sem fechamento obrigatório).

    No OFX as tags muitas vezes não têm fechamento: o valor vai até a
    próxima tag ou quebra de linha. Ex: "<TRNAMT>-49.90\n".
    """
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_ofx(text: str) -> List[dict]:
    """Lê um arquivo OFX e devolve transações estruturadas.

    Cada item: {date (ISO), amount (abs > 0), description, type, raw_amount}.
    O tipo é inferido pelo sinal do TRNAMT (negativo = despesa).
    """
    if not text:
        return []

    items: List[dict] = []
    for block in _STMTTRN_RE.findall(text):
        raw_amount = _ofx_tag(block, "TRNAMT")
        value = parse_amount(raw_amount)
        if value is None:
            continue

        raw_date = _ofx_tag(block, "DTPOSTED") or _ofx_tag(block, "DTUSER")
        iso = parse_date_flexible(raw_date)

        # Descrição: NAME, ou MEMO, ou o código da transação.
        desc = (
            _ofx_tag(block, "NAME")
            or _ofx_tag(block, "MEMO")
            or _ofx_tag(block, "CHECKNUM")
            or "Transação importada"
        )

        items.append({
            "date": iso,
            "amount": abs(value),
            "description": desc,
            "type": "despesa" if value < 0 else "receita",
            "raw_amount": value,
        })
    return items
