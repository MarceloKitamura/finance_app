"""
Tabelas de descontos do salário (INSS e IRRF).

═══════════════════════════════════════════════════════════════════
⭐ POR QUE ISTO FICA NUM ARQUIVO SÓ DE CONSTANTES?
═══════════════════════════════════════════════════════════════════
As alíquotas de INSS e IRRF mudam quase todo ano. Mantendo as faixas
isoladas aqui, ajustar o cálculo no futuro é só editar estes números —
nenhuma regra de negócio (salary_service.py) precisa mudar.

Os valores abaixo são as tabelas vigentes em 2025 (Brasil). Se o governo
publicar novas faixas, basta atualizar as listas mantendo o formato.

Cada faixa é uma tupla:
    INSS:  (limite_superior_da_faixa, aliquota)        # progressivo
    IRRF:  (limite_superior_da_faixa, aliquota, parcela_a_deduzir)
═══════════════════════════════════════════════════════════════════
"""

# ───────────────────────────────────────────────────────────
# INSS — contribuição progressiva (2025)
# ───────────────────────────────────────────────────────────
# O cálculo é POR FAIXA: cada parte do salário paga a alíquota da sua
# faixa (igual ao imposto de renda). O salary_service implementa isso.
# float("inf") na última faixa significa "até o teto" (tratado abaixo).
INSS_BRACKETS = [
    (1518.00, 0.075),
    (2793.88, 0.09),
    (4190.83, 0.12),
    (8157.41, 0.14),
]

# Teto de contribuição: salários acima disto pagam sempre o INSS máximo.
INSS_CEILING = 8157.41

# ───────────────────────────────────────────────────────────
# IRRF — Imposto de Renda Retido na Fonte (tabela 2025)
# ───────────────────────────────────────────────────────────
# Diferente do INSS, o IRRF NÃO é por faixa: aplica-se a alíquota da
# faixa em que a base se encaixa e subtrai-se a "parcela a deduzir".
#   imposto = base * aliquota - parcela_a_deduzir
IRRF_BRACKETS = [
    (2428.80, 0.0, 0.0),        # isento
    (2826.65, 0.075, 182.16),
    (3751.05, 0.15, 394.16),
    (4664.68, 0.225, 675.49),
    (float("inf"), 0.275, 908.73),
]

# Dedução por dependente na base do IRRF.
IRRF_DEPENDENT_DEDUCTION = 189.59

# ───────────────────────────────────────────────────────────
# Vale-transporte
# ───────────────────────────────────────────────────────────
# Por lei, o desconto de VT é limitado a 6% do salário bruto. Se o custo
# real do transporte for menor que 6%, desconta-se o custo real.
VT_MAX_RATE = 0.06
