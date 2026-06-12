"""
Service de salário.

═══════════════════════════════════════════════════════════════════
⭐ O QUE ESTE SERVICE FAZ
═══════════════════════════════════════════════════════════════════
1. Guarda/lê a configuração de salário do usuário (SalaryConfig), via
   a tabela genérica `settings`.

2. Calcula uma ESTIMATIVA do salário LÍQUIDO a partir do bruto,
   aplicando os descontos: INSS, IRRF, vale-transporte e descontos
   avulsos. As tabelas de alíquotas ficam em constants/salary_tables.py,
   para serem fáceis de atualizar quando o governo mudar as faixas.

3. Divide o líquido nos dias de recebimento (ex: dia 15 e dia 30),
   no modo "metade" (50/50) ou "personalizado" (valores informados).

IMPORTANTE: este é um cálculo ESTIMADO e simplificado. Folhas reais têm
particularidades (adiantamentos, benefícios, FGTS que não desconta do
líquido, etc.). O objetivo aqui é dar uma previsão boa o suficiente para
planejamento — e a estrutura é flexível para o usuário ajustar/desligar
descontos.
═══════════════════════════════════════════════════════════════════
"""

from typing import Optional

from app.constants.salary_tables import (
    INSS_BRACKETS,
    INSS_CEILING,
    IRRF_BRACKETS,
    IRRF_DEPENDENT_DEDUCTION,
    VT_MAX_RATE,
)
from app.models.salary import SPLIT_CUSTOM, SalaryConfig
from app.repositories.settings_repository import SettingsRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Chave usada na tabela settings para guardar a configuração de salário.
SALARY_CONFIG_KEY = "salary_config"


class SalaryService:
    """Configuração de salário + cálculo de líquido + divisão por dia."""

    def __init__(self, repository: SettingsRepository | None = None):
        self.repository = repository or SettingsRepository()

    # ═══════════════════════════════════════════════════════
    # CONFIGURAÇÃO (persistência)
    # ═══════════════════════════════════════════════════════

    def get_config(self) -> SalaryConfig:
        """Lê a configuração salva. Se não houver, devolve uma config vazia
        (salário 0) — o app funciona normalmente sem salário cadastrado."""
        data = self.repository.get(SALARY_CONFIG_KEY)
        return SalaryConfig.from_dict(data or {})

    def config_updated_at(self) -> Optional[str]:
        """Data/hora da última alteração da config (para invalidar caches)."""
        return self.repository.get_updated_at(SALARY_CONFIG_KEY)

    def save_config(self, config: SalaryConfig) -> SalaryConfig:
        """Valida e persiste a configuração de salário."""
        config.validate()
        self.repository.set(SALARY_CONFIG_KEY, config.to_dict())
        logger.info(
            "Configuração de salário salva: bruto=%.2f, split=%s",
            config.gross, config.split_mode,
        )
        return config

    # ═══════════════════════════════════════════════════════
    # CÁLCULO DO LÍQUIDO
    # ═══════════════════════════════════════════════════════

    def calculate_net(self, config: SalaryConfig | None = None) -> dict:
        """Calcula o líquido estimado e devolve o detalhamento dos descontos.

        Retorna um dict pronto para a interface, com cada desconto separado
        para o usuário entender de onde veio cada valor.
        """
        config = config or self.get_config()
        gross = max(0.0, float(config.gross))

        inss = self._calc_inss(gross) if config.inss_enabled else 0.0
        # A base do IRRF é o bruto MENOS o INSS e MENOS a dedução por
        # dependentes (regra da Receita Federal).
        irrf_base = max(0.0, gross - inss - config.dependents * IRRF_DEPENDENT_DEDUCTION)
        irrf = self._calc_irrf(irrf_base) if config.irrf_enabled else 0.0
        vt = self._calc_vt(gross, config) if config.vt_enabled else 0.0
        others = sum(max(0.0, d.amount) for d in config.other_discounts)

        total_discounts = inss + irrf + vt + others
        net = max(0.0, gross - total_discounts)

        return {
            "gross": round(gross, 2),
            "inss": round(inss, 2),
            "irrf": round(irrf, 2),
            "vt": round(vt, 2),
            "other_discounts": round(others, 2),
            "other_discounts_detail": [d.to_dict() for d in config.other_discounts],
            "total_discounts": round(total_discounts, 2),
            "net": round(net, 2),
        }

    def _calc_inss(self, gross: float) -> float:
        """INSS progressivo: cada faixa do salário paga sua própria alíquota.

        Ex: parte até 1.518 paga 7,5%; a parte entre 1.518 e 2.793,88 paga
        9%; e assim por diante, até o teto de contribuição.
        """
        base = min(gross, INSS_CEILING)
        inss = 0.0
        lower = 0.0
        for upper, rate in INSS_BRACKETS:
            if base <= lower:
                break
            tramo = min(base, upper) - lower
            if tramo > 0:
                inss += tramo * rate
            lower = upper
        return inss

    @staticmethod
    def _calc_irrf(base: float) -> float:
        """IRRF: aplica a alíquota da faixa da base e subtrai a parcela a deduzir."""
        for upper, rate, deduction in IRRF_BRACKETS:
            if base <= upper:
                return max(0.0, base * rate - deduction)
        return 0.0

    @staticmethod
    def _calc_vt(gross: float, config: SalaryConfig) -> float:
        """Vale-transporte: o desconto é limitado a 6% do bruto.

        Se o custo real do transporte (vt_monthly_cost) for informado e for
        menor que 6%, desconta-se o custo real. Se não for informado (0),
        assume-se o teto de 6%.
        """
        cap = gross * VT_MAX_RATE
        if config.vt_monthly_cost and config.vt_monthly_cost > 0:
            return min(config.vt_monthly_cost, cap)
        return cap

    # ═══════════════════════════════════════════════════════
    # DIVISÃO DO RECEBIMENTO (dias 15 e 30)
    # ═══════════════════════════════════════════════════════

    def split_payment(self, config: SalaryConfig | None = None) -> dict:
        """Divide o líquido nos dois dias de recebimento configurados.

        Modo "metade": 50% em cada dia (o 2º dia recebe o arredondamento,
        para a soma bater exatamente com o líquido). Modo "personalizado":
        usa os valores que o usuário informou para cada dia.
        """
        config = config or self.get_config()
        net = self.calculate_net(config)["net"]

        if config.split_mode == SPLIT_CUSTOM:
            day1 = round(max(0.0, config.amount_day_1), 2)
            day2 = round(max(0.0, config.amount_day_2), 2)
        else:
            day1 = round(net / 2, 2)
            day2 = round(net - day1, 2)  # garante day1 + day2 == net

        return {
            "net": round(net, 2),
            "pay_day_1": config.pay_day_1,
            "pay_day_2": config.pay_day_2,
            "amount_day_1": day1,
            "amount_day_2": day2,
            "split_mode": config.split_mode,
        }

    def summary(self, config: SalaryConfig | None = None) -> dict:
        """Resumo completo p/ a API: config + descontos + divisão."""
        config = config or self.get_config()
        breakdown = self.calculate_net(config)
        split = self.split_payment(config)
        return {
            "config": config.to_dict(),
            "breakdown": breakdown,
            "split": split,
            "enabled": config.enabled and config.gross > 0,
        }
