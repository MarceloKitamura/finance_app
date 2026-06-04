"""
Service de transações.

A camada de service contém a REGRA DE NEGÓCIO:
- normaliza os dados de entrada (pix/PIX/Pix -> "Pix");
- valida (via Transaction.validate);
- persiste (via repository);
- registra logs.

A interface (CLI ou Streamlit) deve sempre conversar com o service,
nunca diretamente com o repository.

Mudança em relação à versão anterior:
- Agora normalizamos categoria, pagamento e tipo aqui dentro,
  antes de construir o objeto Transaction. Isso garante que o banco
  só receba dados padronizados.
"""

from typing import List

from app.constants.people import DEFAULT_PERSON
from app.models.transaction import Transaction
from app.repositories.transaction_repository import TransactionRepository
from app.utils.logger import get_logger
from app.utils.normalizers import (
    normalize_category,
    normalize_payment_method,
    normalize_transaction_type,
)

logger = get_logger(__name__)


class TransactionService:
    """Regras de negócio para transações."""

    def __init__(self, repository: TransactionRepository | None = None):
        # Permite injetar um repository diferente (útil em testes).
        self.repository = repository or TransactionRepository()

    def add_transaction(
        self,
        date: str,
        description: str,
        amount: float,
        type_: str,
        category: str,
        payment_method: str,
        spent_by: str = DEFAULT_PERSON,
        account: str = "Carteira",
        card: str = "",
    ) -> Transaction:
        """
        Cria, normaliza, valida e persiste uma nova transação.

        Os parâmetros podem vir "sujos" (pix/PIX/Pix). A normalização
        acontece antes da validação.

        Lança ValueError se algum campo for inválido.
        """
        # Passo 1: normalização.
        normalized_type = normalize_transaction_type(type_)
        normalized_category = normalize_category(category, normalized_type)
        normalized_payment = normalize_payment_method(payment_method)
        # "Quem gastou" vem de uma lista fixa (ou texto livre em "Outro"),
        # então só limpamos espaços e caímos no padrão se vier vazio.
        normalized_spent_by = (spent_by or "").strip() or DEFAULT_PERSON
        # Conta vem de uma lista (ou texto): só limpamos e caímos no padrão.
        normalized_account = (account or "").strip() or "Carteira"
        # Cartão é opcional (vazio = não foi no cartão).
        normalized_card = (card or "").strip()

        # Passo 2: construir o objeto com dados já canônicos.
        transaction = Transaction(
            date=date,
            description=description.strip(),
            amount=amount,
            type=normalized_type,
            category=normalized_category,
            payment_method=normalized_payment,
            spent_by=normalized_spent_by,
            account=normalized_account,
            card=normalized_card,
        )

        # Passo 3: validar regras de domínio.
        transaction.validate()

        # Passo 4: persistir e logar.
        try:
            saved = self.repository.create(transaction)
            logger.info(
                "Transação criada: id=%s, tipo=%s, valor=%.2f, categoria=%s",
                saved.id, saved.type, saved.amount, saved.category,
            )
            return saved
        except Exception:
            logger.exception("Erro ao salvar transação")
            raise

    def list_all(self) -> List[Transaction]:
        return self.repository.list_all()

    def list_by_month(self, year: int, month: int) -> List[Transaction]:
        return self.repository.find_by_month(year, month)

    def list_by_category(self, category: str) -> List[Transaction]:
        # Também normalizamos a busca, para "pix" achar resultados de "Pix".
        # Para categorias, usamos um tipo "fictício" porque a busca não tem tipo.
        # Estratégia: passamos a string como veio e o repo busca case-insensitive.
        return self.repository.find_by_category(category)

    def list_by_person(self, spent_by: str) -> List[Transaction]:
        """Lista transações de uma pessoa (busca case-insensitive no repo)."""
        return self.repository.find_by_person(spent_by)

    def get_transaction(self, transaction_id: int) -> Transaction | None:
        """Busca uma transação pelo id (None se não existir)."""
        return self.repository.get_by_id(transaction_id)

    def delete_transaction(self, transaction_id: int) -> bool:
        """Remove uma transação. Retorna True se removeu, False se não achou."""
        deleted = self.repository.delete(transaction_id)
        if deleted:
            logger.info("Transação removida: id=%s", transaction_id)
        return deleted
