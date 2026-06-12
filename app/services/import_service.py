"""
Service de importação de extratos (CSV e OFX).

Fluxo em dois passos (igual ao que o usuário vê na tela):

1. PREVIEW — recebe o conteúdo do arquivo, extrai as transações candidatas
   (via import_parsers), e para cada uma:
     - normaliza tipo/pagamento;
     - sugere a categoria reusando o AIService (palavras-chave/LLM);
     - marca se é DUPLICATA (já existe transação com mesma data+valor+descrição).
   Nada é gravado aqui — o usuário confere e ajusta na tela.

2. CONFIRMAÇÃO — recebe a lista final (já revisada) e grava cada item
   reusando o TransactionService, que aplica toda a validação/normalização
   padrão do projeto. Itens marcados para ignorar (ou duplicatas não
   confirmadas) são pulados.

Reaproveitamento proposital: este service não duplica regra de transação —
ele só orquestra parsers + IA + TransactionService.
"""

import unicodedata
from typing import List, Optional

from app.services.ai_service import AIService
from app.services.transaction_service import TransactionService
from app.repositories.transaction_repository import TransactionRepository
from app.utils.import_parsers import (
    parse_amount,
    parse_csv,
    parse_date_flexible,
    parse_installment,
    parse_ofx,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _norm(text: str) -> str:
    """Minúsculas, sem acento, espaços colapsados — para comparar descrições."""
    text = (text or "").strip().lower()
    nfd = unicodedata.normalize("NFD", text)
    sem = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return " ".join(sem.split())


class ImportService:
    """Orquestra a importação de extratos."""

    def __init__(
        self,
        transaction_service: TransactionService | None = None,
        ai_service: AIService | None = None,
        transaction_repository: TransactionRepository | None = None,
    ):
        self.transaction_service = transaction_service or TransactionService()
        self.ai_service = ai_service or AIService(use_llm=True)
        self.transaction_repository = transaction_repository or TransactionRepository()

    # ═══════════════════════════════════════════════════════
    # PREVIEW
    # ═══════════════════════════════════════════════════════

    def preview(self, format_: str, content: str, mapping: Optional[dict] = None) -> dict:
        """Roteia para o parser certo e devolve {headers, items}.

        Para CSV ainda sem mapeamento, devolve só os headers (para o frontend
        montar os seletores de coluna) e items vazio.
        """
        fmt = (format_ or "").lower()
        # Se o extrato for de um CARTÃO (fatura), o nome do cartão vem no
        # mapping. Nesse caso cada linha vira um GASTO NO CARTÃO (origem
        # 'card'), em vez de receita/despesa na conta. Vale para CSV e OFX.
        card = ((mapping or {}).get("card") or "").strip() or None

        if fmt == "ofx":
            raw = parse_ofx(content)
            items = self._build_items(raw, card=card)
            return {"headers": [], "delimiter": "", "items": items}

        if fmt == "csv":
            parsed = parse_csv(content)
            if not mapping or mapping.get("date") is None or mapping.get("amount") is None:
                # Sem mapeamento ainda: devolve cabeçalhos + amostra para a tela.
                return {
                    "headers": parsed["headers"],
                    "delimiter": parsed["delimiter"],
                    "sample": parsed["rows"][:5],
                    "items": [],
                }
            raw = self._rows_to_raw(parsed["rows"], mapping)
            items = self._build_items(raw, default_account=mapping.get("default_account"),
                                      default_payment=mapping.get("default_payment"), card=card)
            return {"headers": parsed["headers"], "delimiter": parsed["delimiter"], "items": items}

        raise ValueError(f"Formato de importação inválido: {format_!r}. Use 'csv' ou 'ofx'.")

    def _rows_to_raw(self, rows: List[list], mapping: dict) -> List[dict]:
        """Aplica o mapeamento de colunas do CSV → transações cruas."""
        ci_date = int(mapping["date"])
        ci_amount = int(mapping["amount"])
        ci_desc = mapping.get("description")
        ci_desc = int(ci_desc) if ci_desc is not None else None
        default_type = mapping.get("default_type", "auto")

        raw = []
        for row in rows:
            def cell(i):
                return row[i].strip() if (i is not None and i < len(row)) else ""

            value = parse_amount(cell(ci_amount))
            if value is None:
                continue
            iso = parse_date_flexible(cell(ci_date))
            desc = cell(ci_desc) if ci_desc is not None else "Importado"

            if default_type in ("despesa", "receita"):
                tipo = default_type
            else:
                tipo = "despesa" if value < 0 else "receita"

            raw.append({
                "date": iso,
                "amount": abs(value),
                "description": desc or "Importado",
                "type": tipo,
            })
        return raw

    def _build_items(
        self,
        raw_items: List[dict],
        default_account: Optional[str] = None,
        default_payment: Optional[str] = None,
        card: Optional[str] = None,
    ) -> List[dict]:
        """Enriquece transações cruas: sugere categoria e detecta duplicatas.

        Se `card` for informado, o extrato é a FATURA de um cartão: cada linha
        vira um gasto no cartão (despesa, forma de pagamento 'Crédito'). Como
        não há gasto no cartão "negativo", lançamentos que não são compras
        (pagamento de fatura, estornos) devem ser desmarcados pelo usuário na
        tela de pré-visualização.
        """
        existing = self._existing_keys()
        card_name = (card or "").strip()
        account = (default_account or "Carteira").strip() or "Carteira"
        payment = "Crédito" if card_name else (default_payment or "Outros").strip() or "Outros"

        items = []
        for r in raw_items:
            # Fatura de cartão: tudo é despesa no cartão.
            tipo = "despesa" if card_name else (r.get("type") or "despesa")
            desc = r.get("description") or "Importado"
            amount = r.get("amount") or 0.0
            iso = r.get("date")

            # Numa FATURA de cartão, detecta se a linha é uma parcela
            # ("NETFLIX 03/12"). Em conta/extrato comum não faz sentido parcelar.
            inst = parse_installment(desc) if card_name else None
            base_desc = inst["base"] if inst else desc
            installment_no = inst["installment_no"] if inst else 1
            installments_total = inst["installments_total"] if inst else 1

            # Sugestão de categoria reusando o AIService (sobre a descrição-base,
            # para o "03/12" não atrapalhar o casamento por palavra-chave).
            category, confidence = self.ai_service.suggest_category(base_desc, tipo)

            dup = False
            if iso:
                key = (iso, round(float(amount), 2), _norm(desc))
                dup = key in existing
                # Parcela já lançada (inclui as projetadas de outra fatura): o
                # casamento por descrição não pega "3/12" vs "03/12", então
                # checamos pelo purchase_group via TransactionService.
                if not dup and inst:
                    dup = self.transaction_service.installment_already_imported(
                        date=iso,
                        base_description=base_desc,
                        installment_no=installment_no,
                        installments_total=installments_total,
                        card=card_name,
                    )

            items.append({
                "date": iso or "",
                "description": desc,
                "amount": round(float(amount), 2),
                "type": tipo,
                "category_suggested": category,
                "confidence": confidence,
                "payment_method": payment,
                "spent_by": "Eu",
                "account": account,
                "card": card_name,
                # Parcelamento detectado (1/1 = à vista). project_future liga a
                # projeção das próximas parcelas nas faturas seguintes.
                "base_description": base_desc,
                "installment_no": installment_no,
                "installments_total": installments_total,
                "project_future": bool(inst),
                "duplicate": dup,
                # Por padrão, importa tudo que NÃO é duplicata e tem data válida.
                "include": bool(iso) and not dup,
            })
        return items

    def _existing_keys(self) -> set:
        """Conjunto (date, amount, desc_normalizada) das transações já gravadas."""
        keys = set()
        for t in self.transaction_repository.list_all():
            keys.add((t.date[:10], round(float(t.amount), 2), _norm(t.description)))
        return keys

    # ═══════════════════════════════════════════════════════
    # CONFIRMAÇÃO (gravação)
    # ═══════════════════════════════════════════════════════

    def import_transactions(self, items: List[dict]) -> dict:
        """Grava as transações revisadas. Pula as marcadas com include=False.

        Retorna {imported, skipped, errors:[...]}. Cada item deve trazer ao
        menos date, description, amount e type; categoria vem do campo
        `category` (escolhido na tela) ou da sugestão.
        """
        imported = 0
        skipped = 0
        errors: List[str] = []

        for it in items:
            if not it.get("include", True):
                skipped += 1
                continue

            category = (it.get("category") or it.get("category_suggested") or "").strip()
            if not category:
                category = "Outros"  # sem palpite: cai em "Outros".

            installments_total = int(it.get("installments_total") or 1)

            try:
                # Linha de fatura PARCELADA: grava a parcela e projeta as
                # futuras (sem duplicar). Delega a regra ao TransactionService.
                if it.get("card") and installments_total > 1:
                    result = self.transaction_service.register_card_installment_line(
                        date=it["date"],
                        base_description=(
                            it.get("base_description") or it.get("description") or "Compra"
                        ),
                        parcela_amount=float(it["amount"]),
                        installment_no=int(it.get("installment_no") or 1),
                        installments_total=installments_total,
                        category=category,
                        payment_method=it.get("payment_method", "Crédito"),
                        spent_by=it.get("spent_by", "Eu"),
                        card=it.get("card", ""),
                        account=it.get("account", "Carteira"),
                        project_future=bool(it.get("project_future", True)),
                    )
                    n_created = len(result["created"])
                    if n_created:
                        imported += n_created
                    else:
                        # Tudo já existia (reimportação): conta como pulada.
                        skipped += 1
                    continue

                self.transaction_service.add_transaction(
                    date=it["date"],
                    description=it.get("description", "Importado"),
                    amount=float(it["amount"]),
                    type_=it.get("type", "despesa"),
                    category=category,
                    payment_method=it.get("payment_method", "Outros"),
                    spent_by=it.get("spent_by", "Eu"),
                    account=it.get("account", "Carteira"),
                    card=it.get("card", ""),
                    # Linha de fatura de cartão → gasto no cartão (à vista).
                    payment_origin="card" if it.get("card") else None,
                )
                imported += 1
            except (ValueError, KeyError) as exc:
                skipped += 1
                errors.append(f"{it.get('description', '?')}: {exc}")

        logger.info("Importação: %d gravadas, %d puladas, %d erros",
                    imported, skipped, len(errors))
        return {"imported": imported, "skipped": skipped, "errors": errors}
