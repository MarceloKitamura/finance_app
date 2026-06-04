"""
Palavras-chave para categorização automática (a "inteligência" simples da IA).

Como funciona:
A IA olha a descrição da transação ("MERCADO EXTRA JUNDIAI") e procura
por palavras-chave conhecidas ("mercado") para sugerir uma categoria.

Por que isso fica em constants/?
Porque são DADOS (um mapa de palavras → categoria), não lógica.
A lógica de busca fica em app/services/ai_service.py.
Separar permite que você adicione palavras novas sem entender o código da IA.

Como adicionar uma palavra nova:
Encontre a categoria certa abaixo e adicione a palavra na lista.
Exemplo: para "ifood" cair em Alimentação, adicione "ifood" na lista de Alimentação.

IMPORTANTE: as palavras devem estar em minúsculas e sem acento, porque
o ai_service normaliza a descrição antes de comparar.
"""

# Mapa: categoria de DESPESA → lista de palavras-chave que indicam essa categoria.
# A ordem importa: categorias no topo têm prioridade se houver empate.
EXPENSE_PATTERNS: dict[str, list[str]] = {
    "Mercado": [
        "mercado", "supermercado", "atacadao", "atacado", "carrefour",
        "extra", "pao de acucar", "assai", "sacolao", "hortifruti",
        "quitanda", "mercadinho",
    ],
    "Alimentação": [
        "restaurante", "lanchonete", "padaria", "bar", "cafe", "cafeteria",
        "pizzaria", "hamburgueria", "ifood", "rappi", "uber eats",
        "mcdonalds", "burger", "subway", "acougue", "doceria", "sorveteria",
        "food", "comida", "almoco", "jantar", "delivery",
    ],
    "Transporte": [
        "uber", "99", "taxi", "onibus", "metro", "trem", "cptm",
        "combustivel", "gasolina", "etanol", "alcool", "posto",
        "estacionamento", "pedagio", "bilhete unico", "passagem",
        "blablacar", "cabify",
    ],
    "Moradia": [
        "aluguel", "condominio", "iptu", "imobiliaria", "reforma",
        "material de construcao", "moveis", "mobilia",
    ],
    "Contas": [
        "luz", "energia", "agua", "saneamento", "gas", "internet",
        "telefone", "celular", "vivo", "claro", "tim", "oi", "net",
        "conta de", "fatura", "boleto",
    ],
    "Saúde": [
        "farmacia", "drogaria", "medico", "hospital", "clinica",
        "dentista", "exame", "laboratorio", "consulta", "remedio",
        "plano de saude", "unimed", "amil", "academia", "psicologo",
        "terapia", "fisioterapia",
    ],
    "Educação": [
        "escola", "faculdade", "universidade", "curso", "livro",
        "livraria", "material escolar", "mensalidade", "udemy",
        "alura", "ingles", "idiomas", "apostila",
    ],
    "Lazer": [
        "cinema", "teatro", "show", "ingresso", "parque", "viagem",
        "hotel", "airbnb", "passeio", "festa", "balada", "jogo",
        "game", "playstation", "xbox", "steam",
    ],
    "Assinaturas": [
        "netflix", "spotify", "disney", "hbo", "max", "prime",
        "amazon prime", "youtube premium", "deezer", "globoplay",
        "paramount", "apple", "icloud", "google one", "assinatura",
        "mensalidade streaming",
    ],
    "Compras": [
        "loja", "shopping", "amazon", "mercado livre", "magazine",
        "magalu", "americanas", "shopee", "aliexpress", "roupa",
        "calcado", "sapato", "tenis", "eletronico", "celular novo",
        "presente", "vestuario",
    ],
    "Cartão de crédito": [
        "fatura cartao", "pagamento cartao", "anuidade", "cartao de credito",
    ],
    "Investimentos": [
        "investimento", "aplicacao", "tesouro", "cdb", "acoes",
        "fundo", "previdencia", "bitcoin", "cripto", "corretora",
        "xp", "nuinvest", "rico", "clear",
    ],
    "Família": [
        "filho", "filha", "crianca", "escola infantil", "creche",
        "brinquedo", "fralda", "bebe",
    ],
    "Pets": [
        "pet", "petshop", "veterinario", "racao", "cachorro", "gato",
        "animal", "vacina pet",
    ],
}

# Mapa: categoria de RECEITA → palavras-chave.
INCOME_PATTERNS: dict[str, list[str]] = {
    "Salário": [
        "salario", "pagamento", "holerite", "folha", "ordenado",
        "remuneracao", "vencimento",
    ],
    "Freelance": [
        "freelance", "freela", "projeto", "servico", "consultoria",
        "bico", "job", "trabalho extra",
    ],
    "Reembolso": [
        "reembolso", "estorno", "devolucao", "ressarcimento", "cashback",
    ],
    "Investimentos": [
        "rendimento", "rendimentos", "dividendo", "dividendos", "juros",
        "lucro", "lucros", "resgate", "proventos", "aluguel recebido",
        "acoes",
    ],
    "Presente": [
        "presente", "doacao", "mesada", "premio", "gift",
    ],
}
