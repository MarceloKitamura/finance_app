"""
Modelo (entidade) SalaryConfig.

Representa a CONFIGURAÇÃO de salário do usuário: o salário bruto, os
descontos que se aplicam a ele e como o recebimento é dividido ao longo
do mês (ex: metade no dia 15, metade no dia 30).

É uma configuração ÚNICA do app (single-user): existe no máximo uma. Por
isso ela é guardada na tabela genérica `settings` (chave/valor JSON), e
não numa tabela própria — ver SettingsRepository.

A estrutura é FLEXÍVEL de propósito: além dos descontos conhecidos (INSS,
IRRF, VT), há uma lista `other_discounts` para o usuário cadastrar
qualquer outro desconto (plano de saúde, pensão, etc.) sem precisar mudar
o código.
"""

from dataclasses import dataclass, field
from typing import List

# Modos de divisão do recebimento.
SPLIT_HALF = "metade"          # 50% no 1º dia, 50% no 2º
SPLIT_CUSTOM = "personalizado"  # valores informados manualmente p/ cada dia


@dataclass
class OtherDiscount:
    """Um desconto avulso configurável (plano de saúde, pensão, etc.)."""
    label: str
    amount: float

    def to_dict(self) -> dict:
        return {"label": self.label, "amount": round(float(self.amount), 2)}

    @classmethod
    def from_dict(cls, data: dict) -> "OtherDiscount":
        return cls(
            label=str(data.get("label", "")).strip() or "Desconto",
            amount=float(data.get("amount", 0) or 0),
        )


@dataclass
class SalaryConfig:
    """Configuração de salário e divisão de recebimento.

    Campos:
        gross: salário BRUTO mensal (antes dos descontos).
        dependents: nº de dependentes (reduz a base do IRRF).
        inss_enabled / irrf_enabled: permitem desligar um desconto caso o
            usuário queira informar o líquido por outra via.
        vt_enabled: se há desconto de vale-transporte.
        vt_monthly_cost: custo real do VT no mês. Se 0, usa o teto de 6%.
        other_discounts: descontos avulsos (lista flexível).
        pay_day_1 / pay_day_2: dias do mês em que o salário cai (15 e 30).
        split_mode: "metade" (50/50) ou "personalizado".
        amount_day_1 / amount_day_2: valores LÍQUIDOS por dia quando o modo
            é "personalizado" (ignorados no modo "metade").
        enabled: liga/desliga o uso do salário na previsão.
    """
    gross: float = 0.0
    dependents: int = 0
    inss_enabled: bool = True
    irrf_enabled: bool = True
    vt_enabled: bool = False
    vt_monthly_cost: float = 0.0
    other_discounts: List[OtherDiscount] = field(default_factory=list)
    pay_day_1: int = 15
    pay_day_2: int = 30
    split_mode: str = SPLIT_HALF
    amount_day_1: float = 0.0
    amount_day_2: float = 0.0
    enabled: bool = True

    def validate(self) -> None:
        """Valida os campos básicos (chamado antes de salvar)."""
        if self.gross < 0:
            raise ValueError("O salário bruto não pode ser negativo.")
        if not (1 <= self.pay_day_1 <= 31) or not (1 <= self.pay_day_2 <= 31):
            raise ValueError("Os dias de pagamento devem estar entre 1 e 31.")
        if self.split_mode not in (SPLIT_HALF, SPLIT_CUSTOM):
            raise ValueError("Modo de divisão inválido (use 'metade' ou 'personalizado').")
        if self.dependents < 0:
            raise ValueError("O número de dependentes não pode ser negativo.")

    # ---------- Serialização para a tabela settings (JSON) ----------

    def to_dict(self) -> dict:
        return {
            "gross": round(float(self.gross), 2),
            "dependents": int(self.dependents),
            "inss_enabled": bool(self.inss_enabled),
            "irrf_enabled": bool(self.irrf_enabled),
            "vt_enabled": bool(self.vt_enabled),
            "vt_monthly_cost": round(float(self.vt_monthly_cost), 2),
            "other_discounts": [d.to_dict() for d in self.other_discounts],
            "pay_day_1": int(self.pay_day_1),
            "pay_day_2": int(self.pay_day_2),
            "split_mode": self.split_mode,
            "amount_day_1": round(float(self.amount_day_1), 2),
            "amount_day_2": round(float(self.amount_day_2), 2),
            "enabled": bool(self.enabled),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SalaryConfig":
        """Reconstrói a config a partir do JSON salvo (tolerante a faltas)."""
        data = data or {}
        return cls(
            gross=float(data.get("gross", 0) or 0),
            dependents=int(data.get("dependents", 0) or 0),
            inss_enabled=bool(data.get("inss_enabled", True)),
            irrf_enabled=bool(data.get("irrf_enabled", True)),
            vt_enabled=bool(data.get("vt_enabled", False)),
            vt_monthly_cost=float(data.get("vt_monthly_cost", 0) or 0),
            other_discounts=[
                OtherDiscount.from_dict(d) for d in (data.get("other_discounts") or [])
            ],
            pay_day_1=int(data.get("pay_day_1", 15) or 15),
            pay_day_2=int(data.get("pay_day_2", 30) or 30),
            split_mode=data.get("split_mode", SPLIT_HALF) or SPLIT_HALF,
            amount_day_1=float(data.get("amount_day_1", 0) or 0),
            amount_day_2=float(data.get("amount_day_2", 0) or 0),
            enabled=bool(data.get("enabled", True)),
        )
