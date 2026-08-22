#!/usr/bin/env bash
# Renomeia ui/pages/backups/ -> ui/pages/timeshift/, seguindo o padrão de
# clonezilla_page.py/eggs_page.py (arquivo principal com o mesmo nome da pasta).
#
# Uso: rode da raiz do projeto (~/carbonara-py)
#   bash rename_to_timeshift.sh
#
# Depois de rodar, copie por cima os 3 arquivos que a Claude já te mandou
# com os imports corrigidos:
#   - timeshift_page.py    -> ui/pages/timeshift/timeshift_page.py
#   - timeshift_panel.py   -> ui/pages/timeshift/timeshift_panel.py
#   - main_window.py       -> ui/main_window.py
#
# v2: move arquivo por arquivo (em vez de `git mv` na pasta inteira) —
# a v1 quebrava se houvesse qualquer arquivo não rastreado ou com nome
# esquisito (espaço, parênteses etc.) dentro da pasta.

set -uo pipefail

cd "$(dirname "$0")" 2>/dev/null || true
ROOT="$HOME/carbonara-py"
cd "$ROOT"

OLD_DIR="ui/pages/backups"
NEW_DIR="ui/pages/timeshift"

if [ ! -d "$OLD_DIR" ]; then
    echo "ERRO: $OLD_DIR não existe. Rode este script da raiz do projeto ou ajuste o caminho."
    exit 1
fi

echo "==> Criando $NEW_DIR"
mkdir -p "$NEW_DIR"

echo "==> Movendo arquivos de $OLD_DIR pra $NEW_DIR (um por um, tolera nomes esquisitos)"
find "$OLD_DIR" -maxdepth 1 -mindepth 1 -print0 | while IFS= read -r -d '' item; do
    name="$(basename "$item")"
    dest="$NEW_DIR/$name"
    if git ls-files --error-unmatch "$item" > /dev/null 2>&1; then
        git mv "$item" "$dest"
        echo "  [git mv]  $name"
    else
        mv "$item" "$dest"
        echo "  [mv]      $name  (não estava rastreado pelo git)"
    fi
done

if [ -z "$(ls -A "$OLD_DIR" 2>/dev/null)" ]; then
    rmdir "$OLD_DIR"
    echo "==> $OLD_DIR removida (estava vazia)"
else
    echo "AVISO: $OLD_DIR não ficou vazia, sobrou algo — confira manualmente:"
    ls -la "$OLD_DIR"
fi

cd "$NEW_DIR"

echo ""
echo "==> Renomeando arquivos dentro de $NEW_DIR pro padrão timeshift_*"

[ -f "backups_page.py" ] && git mv "backups_page.py" "timeshift_page.py" && echo "  backups_page.py -> timeshift_page.py"
[ -f "snapshots_page.py" ] && git mv "snapshots_page.py" "timeshift_panel.py" && echo "  snapshots_page.py -> timeshift_panel.py"
[ -f "restore_page.py" ] && git mv "restore_page.py" "timeshift_restore.py" && echo "  restore_page.py -> timeshift_restore.py"
[ -f "integrity_page.py" ] && git mv "integrity_page.py" "timeshift_integrity.py" && echo "  integrity_page.py -> timeshift_integrity.py"

if [ -f "backup_progress.py" ]; then
    if git ls-files --error-unmatch "backup_progress.py" > /dev/null 2>&1; then
        git rm "backup_progress.py"
    else
        rm "backup_progress.py"
    fi
    echo "  backup_progress.py removido (duplicata morta, sem imports apontando pra ela)"
fi

cd "$ROOT"

echo ""
echo "==> Arquivos que sobraram em $NEW_DIR (confira se tem algo estranho, tipo aquela cópia manual):"
ls -la "$NEW_DIR"

echo ""
echo "==> Verificação: procurando referências que ainda apontem pro caminho/nome antigo"
echo "    (deve vir vazio depois que você copiar os 3 arquivos corrigidos por cima)"
grep -rn "pages\.backups\|pages/backups\|backups_page\|snapshots_page\|restore_page\|integrity_page" \
    --include="*.py" . || echo "  Nenhuma referência antiga encontrada."

echo ""
echo "==> Pronto. Próximos passos:"
echo "    1. Copie timeshift_page.py e timeshift_panel.py pra $NEW_DIR/"
echo "    2. Copie main_window.py pra ui/"
echo "    3. Rode o app e teste a tela do Timeshift"
echo "    4. git add -A && git commit -m 'Rename backups module to timeshift'"
