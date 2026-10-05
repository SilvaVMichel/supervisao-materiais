# Supervisão Obras — Gestão de Materiais

Primeira versão funcional, preparada em 05/10/2026. Aplicação independente do ChatGPT: login com usuário e senha, Django 5.2 LTS, PostgreSQL em produção. Não está publicada. Nenhuma hospedagem ou domínio foi contratado.

## O que está implementado

- Cadastro de funcionários pelo administrador, com múltiplos perfis, desativação e redefinição de senha. Não existe cadastro público.
- Obras com endereço e supervisores autorizados.
- Pedidos por obra com materiais, unidades, quantidades e data necessária.
- Conferência manual por item: a quantidade disponível cria um lote para expedição; a falta cria uma pendência de compra.
- Cotação por item com fornecedor, preço, frete, previsão e destino.
- Aprovação por qualquer gestor; devolução para ajuste com motivo. Mudança de cotação invalida a aprovação anterior.
- Confirmação da compra apenas após aprovação.
- Recebimento no depósito e separação, inclusive em partes.
- Envio pela logística, com transportador, data e previsão.
- Compra entregue diretamente à obra: envio do fornecedor e recebimento na obra sem entrada fictícia no depósito.
- Confirmação de entrega por quantidade, recebedor, data/hora e observação de divergência.
- Histórico de autor, horário e ação em cada pedido, além de auditoria dos cadastros.
- Perfis aplicados no servidor, proteção CSRF, senhas protegidas pelo Django e bloqueio temporário após cinco falhas de login.
- Proteção contra atualização concorrente: o pedido tem versão e bloqueio transacional de linha no PostgreSQL. Envio repetido de uma movimentação já aplicada é rejeitado.

## Perfis

| Perfil | Responsabilidade |
|---|---|
| Administrador | Acessos, obras, histórico e todas as operações |
| Supervisor | Pedidos nas obras vinculadas e confirmação de recebimento |
| Almoxarifado | Conferência, chegada ao depósito, separação e registro de recebimento |
| Compras | Cotação, confirmação da compra e informação de envio pelo fornecedor |
| Gestor | Aprovação individual ou devolução de cotações |
| Logística | Envio para a obra e informação de transporte do fornecedor |

O supervisor vê pedidos de sua autoria ou de obras em que está vinculado. Perfis centrais veem todas as obras. O administrador tem acesso operacional completo para suporte. Para Giovanni, criar um usuário e marcar Gestor. Nenhum usuário real foi criado automaticamente.

## Uso local para revisão

Requer Python 3.12. Não é necessário Docker.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DEBUG=1
python manage.py migrate
python manage.py setup_roles
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

No Windows PowerShell, ative com `.venv\Scripts\Activate.ps1` e use `$env:DEBUG="1"`.

Acesse http://127.0.0.1:8000. Crie funcionários e depois obras, vinculando os supervisores. As senhas são escolhidas durante a configuração; não há senha padrão. O SQLite local serve para revisão e testes; produção exige PostgreSQL.

## Publicação gratuita de teste: Render + Neon

Configuração atualizada em 05/10/2026 para o piloto gratuito. `render.yaml` cria somente um serviço Render **Free**, na região Ohio. Não cria banco pago. O banco PostgreSQL será o projeto Neon já criado pela empresa. Não é necessário contratar domínio.

### Envio ao GitHub

Extraia o ZIP. Abra a pasta `supervisao-materiais` e envie seu conteúdo ao repositório privado. `manage.py`, `requirements.txt`, `render.yaml`, `build.sh` e `start.sh` devem aparecer na raiz do repositório, junto das pastas `config`, `logistica`, `templates` e `static`. Não envie o ZIP inteiro como arquivo nem a pasta externa adicional. O pacote não inclui banco local, senhas ou pedidos de demonstração.

### Configuração no Render

1. Conecte o repositório privado `supervisao-materiais`. Autorize somente o repositório necessário.
2. Pode usar o Blueprint `render.yaml` ou criar um Web Service manualmente. Na configuração manual: Python, região Ohio, branch main, Root Directory vazio, Build Command `bash build.sh`, Start Command `bash start.sh`, plano **Free**.
3. Configure as variáveis abaixo diretamente no painel. Nunca coloque os valores secretos no código, GitHub, chat ou prints.

| Variável | Valor |
|---|---|
| DEBUG | `0` |
| PYTHON_VERSION | `3.12.14` |
| SECRET_KEY | Segredo aleatório gerado pela hospedagem (pelo menos 50 caracteres) |
| DATABASE_URL | URL PostgreSQL obtida no botão Connect do Neon; copiar somente a URL, sem `psql` nem aspas; usar conexão direta (pooling desativado) com `sslmode=require` |
| INITIAL_ADMIN_USERNAME | Nome de acesso escolhido para o primeiro administrador |
| INITIAL_ADMIN_PASSWORD | Senha inédita forte, com ao menos 10 caracteres, escolhida pelo responsável |
| ALLOWED_HOSTS | `localhost,127.0.0.1`; o domínio Render é acrescentado automaticamente |

4. Confirme que o serviço está no plano Free antes de publicar. Se houver solicitação de plano pago, pare para revisar; essa versão não exige plano pago para o teste.
5. Na primeira inicialização, `start.sh` cria as tabelas, perfis e o administrador. As credenciais iniciais nunca são impressas nos logs. Não existe senha padrão.
6. Entre no sistema pelo endereço fornecido pelo Render. Após validar o acesso, remova `INITIAL_ADMIN_USERNAME` e `INITIAL_ADMIN_PASSWORD` do painel do Render. Reinicializações preservam contas e senhas existentes; não recriam ou redefinem o administrador.
7. Cadastre funcionários, Giovanni como Gestor, e uma obra fictícia. Execute um pedido de 20 sacos com 8 no depósito e 12 para compra. Repita o caminho direto do fornecedor à obra. Use cada perfil separadamente.

### Limites do piloto

O Render Free adormece após 15 minutos sem acesso e pode demorar aproximadamente um minuto para voltar. Existem franquias de uso e possibilidade de suspensão ao esgotá-las. O Neon Free também tem limites de armazenamento e processamento; acompanhe o consumo. O sistema guarda os dados no Neon, nunca no disco temporário do Render. Não utilize o PostgreSQL gratuito do Render, que expira após 30 dias.

A criação das tabelas ocorre durante a inicialização porque o serviço gratuito não dispõe do Shell/etapas de pré-publicação do serviço pago. Para operação empresarial contínua, planeje hospedagem paga, rotina de backups e restauração validada. O ambiente gratuito é destinado à validação do fluxo, não a uma promessa de disponibilidade contínua.

## Verificação realizada

18 testes automatizados, cobrindo fluxo dividido, compra direta, recebimentos parciais, permissões, limites de quantidade, aprovação obrigatória, recotação, reenvio de operação, isolamento de obras, CSRF e bloqueio de login, além da criação única do administrador inicial e falha segura sem credenciais. Testes executados com SQLite em ambiente de desenvolvimento. Verificação de configuração de produção executada sem avisos de segurança não silenciados. O aviso genérico Axes W006 é silenciado intencionalmente porque o bloqueio é por usuário, evitando bloquear toda a equipe por compartilhar IP.

```bash
DEBUG=1 python manage.py test
```

A prévia HTML usa as telas reais com dados fictícios e controles desativados. A verificação visual em navegador não foi concluída neste ambiente.

Ainda é necessário validar o PostgreSQL, concorrência real, TLS, backups e o acesso dos funcionários no ambiente de hospedagem. Isso depende da conta de hospedagem da empresa e faz parte da entrada em operação.

## Limites desta versão

- Conferência de estoque é manual por pedido, conforme definido. Não existe inventário global, entrada avulsa ou reserva automática entre pedidos; o almoxarifado deve considerar os materiais já separados.
- Uma cotação ativa por item; frete deve ser rateado entre itens quando houver uma compra conjunta. Não há comparação de vários fornecedores nem emissão automática de ordem de compra.
- Correções de movimentações confirmadas, cancelamentos, devoluções e trocas não têm telas próprias nesta versão. Para o piloto, registrar a divergência no recebimento. Definir a política de estorno antes de ampliar para operação completa.
- Sem anexos, fotos, assinatura digital, integração fiscal, pagamentos, mensagens por WhatsApp ou alertas externos. A fila do sistema mostra as pendências; não executa pagamento ao fornecedor.
- Data/hora é informada pelo operador, e o horário de registro é preservado na auditoria.
- Interface usa identificação tipográfica da Supervisão, não um arquivo de logotipo oficial fornecido pelo usuário.
- Não há botão para apagar o histórico. Administradores do banco ainda possuem acesso técnico aos dados; não é um arquivo imutável certificado.

## Fontes consultadas

- Plano gratuito: https://render.com/docs/free
- Neon: https://neon.com/pricing
- Hospedagem Django: https://render.com/docs/deploy-django
- Preços: https://render.com/pricing
- Armazenamento: https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses
- Especificação dos planos: https://render.com/docs/compute-plans
- Configuração Blueprint: https://render.com/docs/blueprint-spec
- Backups: https://render.com/docs/postgresql-backups
- Domínio: https://nic.br/noticia/releases/nic-br-oferece-novos-dominios-br-com-foco-em-tecnologia-e-identidade-digital/
- Configuração de segurança: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
