"""
Pessoas que podem ter realizado um gasto.

Mesma ideia das formas de pagamento: uma lista central e imutável,
fonte única da verdade. Assim, para adicionar/remover uma pessoa,
muda-se só este arquivo.

Hoje isto resolve o caso "quem usou o cartão?". No futuro, quando o
projeto virar um app para o casal com login, esta lista pode evoluir
para vir do banco de dados (uma tabela de usuários). Ver comentário
sobre multiusuário no final do README/plano.
"""

# "Eu" é o primeiro item de propósito: é o caso mais comum e será o
# valor padrão sugerido no cadastro.
PEOPLE: tuple[str, ...] = (
    "Eu",
    "Namorada",
    "Mãe",
    "Pai",
    "Irmão",
    "Amigo",
    "Outro",
)

# Valor padrão quando nada for informado.
DEFAULT_PERSON: str = "Eu"

# Rótulo que dispara a digitação livre (igual ao "Outros" das categorias).
OTHER_PERSON_LABEL: str = "Outro"
