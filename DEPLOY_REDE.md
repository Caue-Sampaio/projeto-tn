# 🖧 Guia de Deploy em Rede — TechNord TestFlow

Este guia explica como colocar o TechNord no **computador principal** (servidor) da rede
e permitir que os **outros PCs** usem o programa **sem precisar instalar Python** em cada máquina.

---

## 📋 Visão Geral da Arquitetura

```
┌─────────────────────────────────┐
│     COMPUTADOR PRINCIPAL        │
│         (Servidor)              │
│                                 │
│  📁 \\SERVIDOR\TechNord\        │  ← Pasta compartilhada (leitura+execução)
│     ├── TechNord.exe            │
│     ├── *.dll / *.pyd           │
│     └── network_config.json     │
│                                 │
│  📁 \\SERVIDOR\TechNordData\    │  ← Pasta compartilhada (leitura+escrita)
│     ├── db/technord.db          │  ← Banco SQLite único
│     ├── documents/              │  ← Manuais e datasheets
│     ├── board_images/           │  ← Imagens das placas
│     ├── reports/                │  ← Relatórios PDF
│     ├── logs/                   │  ← Logs
│     └── backups/                │  ← Backups automáticos
│                                 │
└─────────┬───────────────────────┘
          │  Rede Local (LAN)
          │
   ┌──────┴──────┐
   │             │
┌──▼──┐     ┌──▼──┐
│PC 1 │     │PC 2 │     ...
│     │     │     │
│ Atalho    │ Atalho
│  .lnk    │  .lnk
└─────┘     └─────┘
```

**Todos os PCs rodam o mesmo `.exe` direto da rede e acessam o mesmo banco de dados.**

---

## 🔧 Passo 1 — Empacotar o Programa (no seu PC de desenvolvimento)

### 1.1 Requisitos
- Python 3.10+ com todas as dependências instaladas
- PyInstaller (`pip install pyinstaller`)

### 1.2 Executar o Build

Dê **duplo clique** no arquivo `build.bat` ou execute no terminal:

```cmd
cd "C:\Users\leona\OneDrive\Documentos\PROJETO TN ELETROSISTEM 2"
build.bat
```

Isso vai:
1. Limpar builds anteriores
2. Rodar o PyInstaller com a configuração `technord.spec`
3. Gerar a pasta `dist\TechNord\` com o executável

> ⏱️ O build pode demorar **3 a 10 minutos** dependendo do PC.

### 1.3 Testar Localmente

Antes de enviar para o servidor, **teste o .exe localmente**:

```cmd
dist\TechNord\TechNord.exe
```

Verifique:
- ✅ A tela de login aparece
- ✅ Consegue fazer login
- ✅ As abas funcionam (Placas, Testes)
- ✅ Imagens carregam

---

## 🖥️ Passo 2 — Preparar o Servidor (computador principal)

### 2.1 Criar as pastas compartilhadas

No **computador principal**, crie duas pastas:

| Pasta | Permissão | Propósito |
|-------|-----------|-----------|
| `C:\TechNord` | Leitura + Execução | O programa (.exe e DLLs) |
| `C:\TechNordData` | Leitura + Escrita | Banco de dados e arquivos |

### 2.2 Compartilhar na rede

1. **Clique com botão direito** na pasta → **Propriedades** → **Compartilhamento**
2. Clique em **Compartilhamento Avançado...**
3. Marque **"Compartilhar esta pasta"**
4. Configure o **nome do compartilhamento**:
   - `C:\TechNord` → nome: `TechNord`
   - `C:\TechNordData` → nome: `TechNordData`
5. Clique em **Permissões**:

Para `TechNord` (programa):
| Usuário | Permissão |
|---------|-----------|
| Todos   | ✅ Leitura |

Para `TechNordData` (dados):
| Usuário | Permissão |
|---------|-----------|
| Todos   | ✅ Controle Total |

> 💡 **Dica:** Se os PCs usam contas diferentes, crie um usuário específico
> ou use "Todos" nas permissões de compartilhamento.

### 2.3 Verificar o nome do servidor

No computador principal, abra o CMD e execute:

```cmd
hostname
```

Anote o nome (ex: `SERVIDOR-TN`). Os PCs acessarão via `\\SERVIDOR-TN\TechNord`.

---

## 📤 Passo 3 — Copiar para o Servidor

### Opção A: Usar o script automático

Edite o arquivo `deploy_servidor.bat`, alterando a linha:

```bat
set "SERVIDOR=\\SERVIDOR-TN\TechNord"
```

Para o caminho correto do seu servidor, e depois execute:

```cmd
deploy_servidor.bat
```

Ou passe o caminho como argumento:

```cmd
deploy_servidor.bat "\\SERVIDOR-TN\TechNord"
```

### Opção B: Copiar manualmente

1. Copie **toda** a pasta `dist\TechNord\` para `\\SERVIDOR-TN\TechNord\`
2. Crie a pasta `\\SERVIDOR-TN\TechNordData\` com as subpastas:
   - `db\`
   - `documents\`
   - `board_images\`
   - `reports\`
   - `logs\`
   - `backups\`

### 3.1 Configurar o `network_config.json`

Crie/edite o arquivo `network_config.json` **dentro da pasta do programa** no servidor
(`\\SERVIDOR-TN\TechNord\network_config.json`):

```json
{
  "mode": "sqlite",
  "sqlite_path": "\\\\SERVIDOR-TN\\TechNordData\\db\\technord.db",
  "postgres": {
    "host": "",
    "port": 5432,
    "database": "technord",
    "user": "technord_app",
    "password": "",
    "connect_timeout": 5
  },
  "shared_storage": "\\\\SERVIDOR-TN\\TechNordData"
}
```

> ⚠️ **IMPORTANTE:** No JSON, as barras invertidas precisam ser **dobradas** (`\\`).
> O caminho real é `\\SERVIDOR-TN\TechNordData`, mas no JSON fica `\\\\SERVIDOR-TN\\TechNordData`.

---

## 💻 Passo 4 — Configurar os PCs Clientes

### Opção A: Script automático (recomendado)

Em cada PC cliente, execute:

```cmd
\\SERVIDOR-TN\TechNord\criar_atalho_cliente.bat "\\SERVIDOR-TN\TechNord\TechNord.exe"
```

Isso cria um atalho na área de trabalho automaticamente.

### Opção B: Criar atalho manualmente

1. Na área de trabalho do PC cliente, **clique com botão direito** → **Novo** → **Atalho**
2. No campo "Local do item", digite:
   ```
   \\SERVIDOR-TN\TechNord\TechNord.exe
   ```
3. Clique **Avançar**, dê o nome "TechNord", clique **Concluir**

### Opção C: Usar o VBS launcher

Copie o arquivo `Iniciar_TechNord_Rede.vbs` para a área de trabalho do PC cliente.

---

## ✅ Passo 5 — Testar

Em cada PC cliente:
1. Clique no atalho
2. A tela de login deve aparecer
3. Faça login
4. Verifique que os dados são os mesmos em todos os PCs

**Teste de consistência:**
1. No **PC 1**, cadastre uma placa nova
2. No **PC 2**, atualize a lista — a placa deve aparecer
3. No **PC 1**, exporte um relatório
4. No **PC 2**, verifique se o relatório está na pasta `reports/`

---

## ⚠️ Cuidados com SQLite em Rede

O SQLite funciona bem para **até 3-5 usuários simultâneos** em operações normais.
Porém, existem limitações:

| Situação | Recomendação |
|----------|-------------|
| 1-3 usuários simultâneos | ✅ SQLite funciona bem |
| 4-5 usuários simultâneos | ⚠️ Funciona, mas pode ter lentidão em escrita simultânea |
| 6+ usuários simultâneos | ❌ Use PostgreSQL (o programa já suporta!) |
| Rede WiFi instável | ⚠️ Prefira rede cabeada para o servidor |
| VPN / WAN | ❌ SQLite não é indicado, use PostgreSQL |

### Se precisar migrar para PostgreSQL futuramente:

1. Instale o PostgreSQL no servidor
2. Execute o script `server/setup_postgres.sql`
3. No programa, vá em **Configurações → Servidor e Rede**
4. Mude para PostgreSQL e configure o IP do servidor

---

## 🔄 Como Atualizar o Programa

Quando houver uma nova versão:

1. No PC de desenvolvimento, faça as alterações no código
2. Execute `build.bat` novamente
3. **Peça para todos os usuários fecharem o programa**
4. Execute `deploy_servidor.bat` (ou copie `dist\TechNord\` para o servidor)
5. Os usuários já podem abrir novamente — sem instalar nada!

---

## 🐛 Solução de Problemas

### "O programa não abre"
- Verifique se o PC consegue acessar `\\SERVIDOR-TN\TechNord\` pelo Explorador de Arquivos
- Verifique se o Windows Defender ou antivírus está bloqueando o .exe da rede
- Tente executar `\\SERVIDOR-TN\TechNord\TechNord.exe` diretamente pelo Explorador

### "Erro de banco de dados"
- Verifique se a pasta `\\SERVIDOR-TN\TechNordData\db\` existe e tem permissão de escrita
- Verifique se `network_config.json` aponta para o caminho correto
- Se o banco está corrompido, restaure do backup em `\\SERVIDOR-TN\TechNordData\backups\`

### "Imagens não aparecem"
- Verifique se `shared_storage` no `network_config.json` está apontando para `\\SERVIDOR-TN\TechNordData`
- As imagens precisam estar em `\\SERVIDOR-TN\TechNordData\board_images\`

### "Programa muito lento pela rede"
- Use **rede cabeada** (não WiFi) entre o servidor e os PCs
- Se houver muitos usuários, considere migrar para PostgreSQL
- Verifique se o antivírus não está escaneando o tráfego de rede

### "Apenas um PC consegue usar por vez"
- Isso é normal com SQLite se houver escritas simultâneas muito frequentes
- O programa já tem tratamento de lock, mas se persistir, migre para PostgreSQL

---

## 📁 Resumo dos Arquivos Criados

| Arquivo | Onde Executar | Função |
|---------|--------------|--------|
| `technord.spec` | PC de dev | Configuração do PyInstaller |
| `build.bat` | PC de dev | Empacota o programa |
| `deploy_servidor.bat` | PC de dev | Copia para o servidor |
| `criar_atalho_cliente.bat` | PC cliente | Cria atalho na área de trabalho |
| `network_config.json` | Servidor | Configura banco e pasta compartilhada |
