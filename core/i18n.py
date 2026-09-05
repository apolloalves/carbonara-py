"""
Sistema de tradução do Carbonara — dicionário próprio, sem QTranslator/.ts/.qm.

Como usar numa página:

    from core.i18n import tr, i18n

    label = QLabel(tr("clonezilla.title"))
    ...
    # pra atualizar sozinho quando o idioma trocar em tempo real:
    i18n.language_changed.connect(lambda: label.setText(tr("clonezilla.title")))

Adicionar um idioma novo: só criar o dict em TRANSLATIONS abaixo. Adicionar uma
chave nova: colocar em TODOS os idiomas (se faltar em algum, cai no fallback
pt->chave crua, nunca quebra/lança exceção).
"""
from __future__ import annotations

import json
import os
import pwd
from pathlib import Path

from PySide6.QtCore import QObject, Signal


def _resolve_config_home() -> Path:
    """Acha o $HOME de quem PEDIU a ação, não o do processo em si.

    Funções deste módulo (via tr()) rodam tanto no app normal (como o
    usuário, ex: apollo) quanto DENTRO do processo privilegiado do
    carbonara-helper (como root, via pkexec) — ex: os logs do
    core/eggs/eggs.py durante um install/update. Usar Path.home() puro
    nesse segundo caso resolve pra /root (raiz nunca tem
    ~/.config/carbonara/language.json de verdade), e o idioma salvo do
    usuário de verdade era ignorado silenciosamente, sempre caindo no
    padrão — mesmo com o app inteiro configurado noutro idioma.

    pkexec exporta PKEXEC_UID com o UID de quem chamou; sudo exporta
    SUDO_UID. Se nenhum dos dois existir (processo comum, não
    privilegiado), Path.home() já resolve certo sozinho."""
    if os.geteuid() == 0:
        for env_var in ("PKEXEC_UID", "SUDO_UID"):
            uid_str = os.environ.get(env_var)
            if uid_str:
                try:
                    return Path(pwd.getpwuid(int(uid_str)).pw_dir)
                except (ValueError, KeyError):
                    pass
    return Path.home()


# ── Onde a escolha de idioma fica salva entre sessões ──────────────────────
_CONFIG_PATH = _resolve_config_home() / ".config" / "carbonara" / "language.json"

# ── Dicionário de traduções ─────────────────────────────────────────────────
# Chaves com namespace por página (ex: "clonezilla.title") pra evitar colisão
# entre páginas que usam a mesma palavra em contextos diferentes.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "pt": {
        "eggs_core.status_syncing_dbs": "Sincronizando bancos de pacotes...",
        "eggs_core.op_cancelled": "Operação cancelada.",
        "eggs_core.log_error_prefix": "ERRO: {msg}",
        "eggs_core.log_removed": "Removido: {file}",
        "eggs_core.log_removed_count": "--- {count} arquivo(s) removido(s) de {directory} ---",
        "eggs_core.log_cleanup_warning": "AVISO: não foi possível limpar {directory}: {exc}",
        "eggs_core.log_broken_symlink": "ERRO: link '{src}' aponta para '{real_src}', que não existe.",
        "eggs_core.status_moving_to": "Movendo para {dest_dir}...",
        "eggs_core.log_moving": "Movendo: {src} -> {dest}",
        "eggs_core.log_iso_created": "--- ISO criada com sucesso: {name} ---",
        "eggs_core.status_backing_up": "Fazendo backup em {path}...",
        "eggs_core.log_backup_start": "Iniciando cópia de segurança para {path}...",
        "eggs_core.log_ready_both": "--- arquivo '{name}' pronto no Ventoy e no MDSATA ---",
        "eggs_core.log_backup_failed_ventoy_ok": "AVISO: backup no MDSATA falhou ({msg}), mas ISO já está no Ventoy.",
        "eggs_core.log_move_error": "ERRO ao mover para {dest_dir}: {msg}",
        "eggs_core.log_space_insufficient_header": "AVISO: Espaço insuficiente nos destinos:",
        "eggs_core.log_space_mdsata_detail": "  ✗ MDSATA ({path}): {free:.1f} GB livres — necessário ~{needed:.1f} GB",
        "eggs_core.log_space_estimate": "\nEstimativa de tamanho da ISO: ~{gb:.1f} GB (comprimido, baseado no uso atual de /)",
        "eggs_core.status_space_mdsata_fail": "Espaço insuficiente no MDSATA — verifique o backup.",
        "eggs_core.log_space_ok": "INFO: Espaço verificado: ISO estimada ~{gb:.1f} GB | {dest} {dest_free:.1f} GB livres | MDSATA {mdsata_free:.1f} GB livres",
        "eggs_core.log_space_dest_insufficient": "AVISO: {dest} tem apenas {free:.1f} GB livres — necessário ~{needed:.1f} GB.",
        "eggs_core.log_no_alt_disk": "Nenhum disco alternativo com espaço suficiente encontrado.",
        "eggs_core.status_space_fail": "Espaço insuficiente — verifique os destinos.",
        "eggs_core.log_suggesting_alt": "Sugerindo {count} disco(s) alternativo(s) com espaço suficiente...",
        "eggs_core.log_no_alt_chosen": "Nenhum destino alternativo escolhido — operação cancelada.",
        "eggs_core.status_user_cancelled": "Cancelado pelo usuário.",
        "eggs_core.log_new_dest_chosen": "Novo destino escolhido: {chosen}",
        "eggs_core.status_checking_devices": "Verificando dispositivos...",
        "eggs_core.log_header_create": "=== CREATE PENGUIN'S EGGS ===",
        "eggs_core.log_dest_chosen": "Destino escolhido: {dest_dir}",
        "eggs_core.log_updated_before_build": "Penguin's Eggs atualizado para v{version} antes desta build.",
        "eggs_core.log_already_latest": "Penguin's Eggs já estava na versão mais recente — build sem atualização prévia.",
        "eggs_core.status_mount_fail": "Falha ao montar dispositivos.",
        "eggs_core.log_invalid_dest": "ERRO: destino '{dest_dir}' não existe ou não está montado.",
        "eggs_core.status_invalid_dest": "Destino inválido.",
        "eggs_core.log_existing_iso_found": "ISO já existente encontrada em {parent} — aproveitando em vez de gerar outra.",
        "eggs_core.status_done_ok": "Concluído com sucesso.",
        "eggs_core.status_op_failed": "Falha na operação.",
        "eggs_core.log_cleaning": "Limpando: {dir}",
        "eggs_core.status_generating_iso": "Gerando nova ISO (eggs produce)...",
        "eggs_core.log_starting_generate": "INICIANDO: Nenhuma .iso encontrada — gerando nova ISO via eggs produce...",
        "eggs_core.log_iso_generated": "--- ISO gerada com sucesso ---",
        "eggs_core.status_iso_generated_not_found": "ISO gerada, mas não encontrada para mover.",
        "eggs_core.status_generate_fail": "Falha ao gerar ISO.",
        "eggs_core.log_header_check": "=== CHECK PENGUIN'S EGGS ===",
        "eggs_core.log_iso_found_count": "{count} arquivo(s) .iso encontrado(s) em {dir}",
        "eggs_core.log_no_iso_found": "Nenhum .iso encontrado em {a}, {b} ou {c}",
        "eggs_core.status_dir_cleaned_nothing": "Diretório limpo — nada para fazer.",
        "eggs_core.log_lock_real_process": "AVISO: /var/lib/pacman/db.lck existe e há um processo pacman/paru/yay rodando de verdade — não mexendo nele.",
        "eggs_core.log_lock_removed": "Lock órfão do pacman removido (/var/lib/pacman/db.lck) — nenhum processo pacman/paru/yay estava rodando de verdade.",
        "eggs_core.log_lock_remove_fail": "AVISO: falha ao remover lock do pacman: {exc}",
        "eggs_core.log_installing_pacman_contrib": "pacman-contrib não encontrado — instalando (necessário pra checar atualizações do penguins-eggs)...",
        "eggs_core.log_pacman_contrib_installed": "pacman-contrib instalado.",
        "eggs_core.log_pacman_contrib_fail": "Não foi possível instalar pacman-contrib (checagem de update via checkupdates ficará indisponível): {err}",
        "eggs_core.status_checking_install": "Verificando instalação...",
        "eggs_core.log_header_install": "=== INSTALL PENGUIN'S EGGS ===",
        "eggs_core.log_eggs_not_found": "penguins-eggs não encontrado — será instalado.",
        "eggs_core.log_eggs_already_checking": "penguins-eggs já instalado — verificando atualização...",
        "eggs_core.log_eggs_via_repo": "penguins-eggs disponível via repo (chaotic-aur) — usando pacman.",
        "eggs_core.title_installing": "Instalando...",
        "eggs_core.title_checking_updates": "Verificando atualizações...",
        "eggs_core.log_pacman_no_update": "pacman confirma: nenhuma atualização disponível pro penguins-eggs.",
        "eggs_core.log_fallback_fresh_eggs": "penguins-eggs não encontrado em nenhum repo configurado — recorrendo ao fresh-eggs.sh (fallback).",
        "eggs_core.log_calamares_not_found": "módulo Calamares não encontrado — será instalado.",
        "eggs_core.log_calamares_already_checking": "módulo Calamares já instalado — verificando atualização...",
        "eggs_core.log_settings_autofix": "auto-cura: settings.yml copiado para settings.yaml (bug conhecido de empacotamento do penguins-eggs no Arch).",
        "eggs_core.log_settings_autofix_fail": "aviso: falha ao auto-corrigir settings.yaml ({exc}).",
        "eggs_core.log_verification_done": "--- verificação concluída ---",
        "eggs_core.status_no_update": "Nenhuma atualização disponível.",
        "eggs_core.word_update": "Atualização",
        "eggs_core.word_install": "Instalação",
        "eggs_core.log_action_done": "--- {action} concluída ---",
        "eggs_core.status_action_done_ok": "{action} concluída com sucesso.",
        "eggs_core.status_install_fail": "Falha na instalação.",
        "menu.idioma": "Idioma",
        "menu.temas": "Temas",
        "menu.central_logs": "Central de logs",
        "menu.verificar_atualizacao": "Verificar atualização",
        "menu.atalhos_teclado": "Atalhos de teclado",
        "menu.sobre": "Sobre",
        "menu.temas_placeholder_msg": "Personalização de tema (claro/escuro/cores de destaque) ainda não foi implementada.",
        "menu.verificar_atualizacao_placeholder_msg": "Checagem de atualização do próprio Carbonara (via git) ainda não foi implementada.",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Fechar",
        "common.cancel": "Cancelar",
        "common.confirm": "Confirmar",
        "common.delete": "Excluir",
        "common.restore": "Restaurar",

        # ── Clonezilla Backups ──────────────────────────────────────────
        "clonezilla.title": "CLONEZILLA BACKUPS",
        "clonezilla.subtitle": "Compressão e gerenciamento das imagens do Clonezilla",
        "clonezilla.empty": (
            "Nenhum backup encontrado em /mnt/MDSATA/CLONEZILLA.\n\n"
            "Gere um backup no Clonezilla primeiro — a pasta gerada por ele "
            "aparece aqui automaticamente assim que existir."
        ),
        "clonezilla.refresh_tooltip": "Atualizar",
        "clonezilla.section_pending_title": "PENDENTES",
        "clonezilla.section_pending_subtitle": "Ainda não comprimidos — aguardando ação",
        "clonezilla.section_compressed_eyebrow": "BACKUPS COMPRIMIDOS",
        "clonezilla.count_file_singular": "1 arquivo",
        "clonezilla.count_file_plural": "{n} arquivos",
        "clonezilla.total_suffix": "total",
        "clonezilla.uploaded_singular": "1 no Google Drive",
        "clonezilla.uploaded_plural": "{n} no Google Drive",

        "clonezilla.action_compress": "Comprimir",
        "clonezilla.action_upload": "Enviar para Google Drive",
        "clonezilla.action_view_details": "Ver detalhes do envio",
        "clonezilla.action_delete": "Excluir",
        "clonezilla.tooltip_uploaded_at": "Já enviado em {when} — clique pra reenviar",
        "clonezilla.tooltip_uploaded_no_date": "Já enviado — clique pra reenviar",

        "clonezilla.dialog_compress_title": "Comprimir backup",
        "clonezilla.dialog_compress_message": "Comprimir '{name}' em .tar.zst?{estimate}",
        "clonezilla.dialog_compress_estimate": (
            "\n\nTamanho: {gb} GB — pode levar bastante tempo (uso intenso de CPU)."
        ),
        "clonezilla.dialog_compress_confirm": "Comprimir",
        "clonezilla.dialog_insufficient_space_title": "Espaço insuficiente",
        "clonezilla.dialog_insufficient_space_message": (
            "Não há espaço livre suficiente em {dir} para comprimir '{name}' "
            "com segurança.\n\nNecessário (estimado): {needed} GB\n"
            "Disponível: {free} GB\n\nLibere espaço no destino antes de tentar novamente."
        ),
        "clonezilla.dialog_check_space_error": "Não foi possível checar o espaço livre em {dir}: {exc}",
        "clonezilla.dialog_delete_title": "Excluir backup",
        "clonezilla.dialog_delete_message": (
            "Excluir {what} de '{name}'?\n\n{path}\n\nEssa ação não pode ser desfeita."
        ),
        "clonezilla.dialog_delete_confirm": "Excluir",
        "clonezilla.what_folder": "a pasta original",
        "clonezilla.what_archive": "o arquivo .tar.zst",
        "clonezilla.dialog_upload_title": "Enviar para o Google Drive",
        "clonezilla.dialog_upload_message": (
            "Enviar '{filename}' para o Google Drive?{size_txt}\n\n"
            "Destino: CLONEZILLA/{year}/{month}\n\nEnvia via rclone (remote 'gdrive')."
        ),
        "clonezilla.dialog_upload_confirm": "Enviar",
        "clonezilla.size_suffix": "\n\nTamanho: {size}",
        "clonezilla.dialog_reupload_title": "Reenviar para o Google Drive",
        "clonezilla.dialog_reupload_message": (
            "'{filename}' já foi enviado{when}.\n\n"
            "Reenviar mesmo assim? Isso vai sobrescrever a cópia no Drive."
        ),
        "clonezilla.dialog_reupload_confirm": "Reenviar",
        "clonezilla.reupload_when": " em {sent_at}",
        "clonezilla.operation_in_progress": "Outra operação exclusiva já está em andamento: {current}",
        "clonezilla.operation_in_progress_generic": "Outra operação exclusiva já está em andamento.",
        "clonezilla.compress_op_label": "Comprimindo {name}",
        "clonezilla.delete_op_label": "Excluindo {name}",
        "clonezilla.upload_op_label": "Enviando {name} para o Drive",
        "clonezilla.list_error": "Erro ao listar backups: {exc}",

        "clonezilla.upload_progress_title": "Enviando {name}",
        "clonezilla.upload_progress_body_title": "Envio em andamento",
        "clonezilla.upload_progress_subtitle": "Enviando {filename} para o Google Drive.",
        "clonezilla.upload_progress_preparing": "Preparando envio de {filename}...",
        "clonezilla.upload_log_header": "=== UPLOAD {filename} ===",
        "clonezilla.upload_log_dest": "Destino: CLONEZILLA/{year}/{month}",
        "clonezilla.upload_done_status": "Envio concluído.",
        "clonezilla.upload_log_fetching_link": "Obtendo link da pasta no Drive...",
        "clonezilla.upload_log_link": "Link: {link}",
        "clonezilla.upload_log_no_link": "Não foi possível obter o link (rclone link falhou).",
        "clonezilla.upload_failed_status": "Envio falhou.",
        "clonezilla.upload_log_error": "ERRO: {msg}",
        "clonezilla.compress_process_error": "Processo de compressão terminou com código {rc}.",
        "clonezilla.delete_process_error": "Processo de exclusão terminou com código {rc}.",

        "clonezilla.details_title": "Backup no Google Drive",
        "clonezilla.details_sent_at": "ENVIADO EM",
        "clonezilla.details_size": "TAMANHO",
        "clonezilla.details_drive_folder": "PASTA NO DRIVE",
        "clonezilla.details_open_drive": "Abrir no Drive",
        "clonezilla.details_no_link_tooltip": "Link do Drive não disponível para este envio",

        # ── Snapshots/Timeshift — painel principal + escolha de restore ──
        "snapshots.synced_today": "sincronizado hoje",
        "snapshots.synced_1_day": "último sync há 1 dia",
        "snapshots.synced_n_days": "último sync há {n} dias",
        "snapshots.never_synced": "nunca sincronizado",
        "snapshots.size_label": "tamanho do snapshot",
        "snapshots.last_sync": "último sync  {date}",
        "snapshots.tooltip_restore": "Restaurar este snapshot",
        "snapshots.tooltip_sync": "Sincronizar este snapshot",
        "snapshots.tooltip_delete": "Excluir este snapshot",
        "snapshots.destination_label": "Destino",
        "snapshots.scope_label": "Escopo",
        "snapshots.scope_root_title": "SOMENTE ROOT",
        "snapshots.scope_root_subtitle": "Snapshot só da raiz do sistema",
        "snapshots.scope_home_title": "SOMENTE HOME",
        "snapshots.scope_home_subtitle": "Snapshot só do /home",
        "snapshots.scope_both_title": "ROOT+HOME",
        "snapshots.scope_both_subtitle": "Snapshot da raiz e do home juntos",
        "snapshots.select_destination": "Selecione um destino de backup",
        "snapshots.btn_refresh_space": "ATUALIZAR ESPAÇO",
        "snapshots.btn_create_snapshot": "CRIAR SNAPSHOT",
        "snapshots.fab_verify_tooltip": "Sincronizar Snapshots",
        "snapshots.no_destinations_found": "Nenhum destino de backup encontrado",
        "snapshots.mount_a_disk": "Monte um disco em /mnt ou /media",
        "snapshots.free_of_total": "{free} livre de {total} • {mountpoint} • {fs_type}",
        "snapshots.free_percent": "{pct}% livre",
        "snapshots.combo_item": " {label}  •  {free} livre  •  {mountpoint}  •  {fs_type}",
        "snapshots.empty_title": "Nenhum snapshot ainda",
        "snapshots.empty_subtitle": "Use Criar Snapshot acima pra começar.",
        "snapshots.select_destination_first": "Selecione um destino primeiro.",
        "snapshots.op_already_running": "Outra operação já está em andamento: {name}",
        "snapshots.op_exclusive_running": "Outra operação exclusiva já está em andamento.",
        "snapshots.backup_exit_code": "Processo de backup terminou com código {rc}.",
        "snapshots.restore_dialog_title": "Restaurar Snapshot",
        "snapshots.choose_restore_type": "ESCOLHA O TIPO DE RESTORE",
        "snapshots.restore_full_title": "Restauração Completa do Sistema",
        "snapshots.restore_full_desc": "Gera script bash para restaurar o sistema completo via live ISO.",
        "snapshots.restore_full_badge": "requer reboot",
        "snapshots.restore_browser_title": "Navegador de Arquivos",
        "snapshots.restore_browser_desc": "Navega e restaura arquivos/pastas individuais do snapshot sem reboot.",
        "snapshots.restore_alt_title": "Restore para disco alternativo",
        "snapshots.restore_alt_desc": "Copia o snapshot inteiro para outro disco/partição montado.",
        "snapshots.restore_home_live_title": "Restaurar HOME sem reboot",
        "snapshots.restore_home_live_desc": (
            "Restaura a HOME inteira no sistema rodando agora — sem live ISO. "
            "Encerra a sessão ao final (logout)."
        ),
        "snapshots.instructions_dialog_title": "Script de Restore Gerado",
        "snapshots.instructions_step1": "1.  Boot pelo Ventoy → selecione uma ISO Arch:",
        "snapshots.instructions_no_iso": "⚠  Nenhuma ISO encontrada em /mnt/VENTOY",
        "snapshots.instructions_step2": "2.  No shell do live ISO, execute:",
        "snapshots.instructions_script_desc": "O script monta os discos, restaura e reinstala o GRUB automaticamente.",
        "snapshots.instructions_confirm_warning": "Confirme digitando RESTAURAR quando solicitado.",
        "snapshots.instructions_files_generated": "Arquivos gerados em:",
        "snapshots.instructions_script_label": "  Script:       {path}",
        "snapshots.instructions_notes_label": "  Instruções:   {path}",
        "snapshots.btn_understood": "Entendido",

        # ── File Browser / Confirmar Restore / Restore disco alternativo ──
        "snapshots.filebrowser_title": "File Browser",
        "snapshots.filebrowser_selected_label": "Selecionados para restore:",
        "snapshots.filebrowser_selected_placeholder": "Nenhum item selecionado.\nSelecione arquivos/pastas na árvore.",
        "snapshots.filebrowser_conflict_label": "Se o arquivo já existir no sistema:",
        "snapshots.filebrowser_overwrite": "Sobrescrever",
        "snapshots.filebrowser_skip": "Pular existentes",
        "snapshots.filebrowser_btn_restore": "  Restaurar selecionados",
        "snapshots.filebrowser_loading": "carregando...",
        "snapshots.filebrowser_restore_done": "─── Restore concluído ───",
        "snapshots.filebrowser_error": "ERRO: {msg}",
        "snapshots.confirm_restore_title": "Confirmar Restore",
        "snapshots.confirm_restore_overwriting": "sobrescrevendo existentes",
        "snapshots.confirm_restore_skipping": "pulando existentes",
        "snapshots.confirm_restore_message": "Restaurar {label} para o sistema,\n{ct}?",
        "snapshots.altrestore_title": "Restore para disco alternativo",
        "snapshots.altrestore_select_dest": "Selecione o disco de destino:",
        "snapshots.altrestore_options_label": "Opções:",
        "snapshots.altrestore_opt_delete": "Sincronizar (--delete)",
        "snapshots.altrestore_opt_hardlinks": "Preservar hard-links (-H)",
        "snapshots.altrestore_warning": "O conteúdo existente no destino pode ser alterado.",
        "snapshots.altrestore_btn_start": "Iniciar Restore",
        "snapshots.altrestore_no_disks": "Nenhum disco alternativo disponível.",
        "snapshots.altrestore_combo_item": "{label}  •  {free} livre  •  {mountpoint}",
        "snapshots.altrestore_dest_info": "{free} livre de {total} • {fs_type}",
        "snapshots.altrestore_insufficient_space": (
            "{base_info}  —  espaço insuficiente (snapshot tem {size}, faltam {missing})"
        ),

        # ── Confirmar exclusão / progresso de remoção ──
        "snapshots.delete_confirm_window_title": "Confirmar exclusão",
        "snapshots.delete_confirm_header": "Excluir Snapshot",
        "snapshots.delete_warning": "Esta ação é irreversível. O snapshot será permanentemente removido do disco.",
        "snapshots.delete_last_root_warning": (
            "Este é o último snapshot ROOT — o carbonara-restore.sh também será "
            "removido, já que não sobrará nada para restaurar."
        ),
        "snapshots.delete_password_note": "Será solicitada a senha de root para concluir a exclusão.",
        "snapshots.delete_progress_title": "Removendo Snapshot",
        "snapshots.delete_awaiting_auth": "Aguardando autenticação...",
        "snapshots.delete_failed_message": "Falha ao remover snapshot:\n\n{msg}",
        "snapshots.delete_cancelled": "Operação cancelada.",
        "snapshots.delete_success": "Snapshot {name} removido com sucesso.",

        # ── Sincronização automática (badge + diálogo) ──
        "snapshots.sync_badge_title": "Sync automática",
        "snapshots.sync_badge_disabled": "desativada",
        "snapshots.sync_badge_next": "próxima {when}",
        "snapshots.sync_dialog_title": "Sincronização Automática",
        "snapshots.sync_enabled": "Ativada",
        "snapshots.sync_disabled": "Desativada",
        "snapshots.sync_frequency_label": "FREQUÊNCIA",
        "snapshots.sync_freq_daily": "Diária",
        "snapshots.sync_freq_weekly": "Semanal",
        "snapshots.sync_freq_custom": "Personalizada",
        "snapshots.sync_time_label": "HORÁRIO",
        "snapshots.sync_scope_label": "ESCOPO",
        "snapshots.sync_last_run_label": "Última execução",
        "snapshots.sync_next_run_label": "Próxima execução",
        "snapshots.sync_never_run": "Nunca executado",
        "snapshots.sync_not_scheduled": "Não agendado",
        "snapshots.sync_weekday_label": "DIA DA SEMANA",
        "snapshots.sync_custom_label": "EXPRESSÃO PERSONALIZADA (systemd OnCalendar)",
        "snapshots.sync_custom_hint": "Ex: *-*-* 03:00:00 (todo dia às 3h) · Sun *-*-* 04:00:00 (domingos às 4h)",
        "snapshots.sync_weekday_mon": "Seg",
        "snapshots.sync_weekday_tue": "Ter",
        "snapshots.sync_weekday_wed": "Qua",
        "snapshots.sync_weekday_thu": "Qui",
        "snapshots.sync_weekday_fri": "Sex",
        "snapshots.sync_weekday_sat": "Sáb",
        "snapshots.sync_weekday_sun": "Dom",
        "snapshots.sync_save_button": "Salvar agendamento",
        "snapshots.sync_cancel_button": "Cancelar agendamento",
        "snapshots.sync_destinations_label": "DESTINOS PRA SINCRONIZAR",
        "snapshots.sync_no_destinations_found": "Nenhum destino de backup encontrado no sistema.",
        "snapshots.sync_no_destination": "Selecione um destino de backup antes de salvar o agendamento.",
        "snapshots.sync_install_failed": "Falha ao aplicar o agendamento no sistema:\n\n{msg}",
        "snapshots.sync_result_success": "sucesso",
        "snapshots.sync_result_failed": "falhou",
        "snapshots.sync_result_skipped": "pulado",
        "snapshots.sync_result_nothing": "nada a sincronizar",
        "snapshots.sync_last_run_value": "{when} · {result}",
        "snapshots.sync_toast_success": "Sincronização automática concluída — {kinds}",
        "snapshots.sync_toast_failed": "Sincronização automática falhou — veja o agendamento pra detalhes",
        "snapshots.sync_toast_nothing": "Sincronização automática ativa, mas não há nenhum snapshot pra sincronizar — crie um snapshot primeiro",

        # ── Confirmar criação de snapshot ──
        "snapshots.create_confirm_title": "Criar Snapshot",
        "snapshots.create_confirm_body": "Você está prestes a criar um snapshot com o escopo:",
        "snapshots.create_confirm_desc_root": "Isso vai gerar um novo snapshot de / no destino selecionado. Pode levar bastante tempo dependendo do tamanho.",
        "snapshots.create_confirm_desc_home": "Isso vai gerar um novo snapshot de /home no destino selecionado. Pode levar bastante tempo dependendo do tamanho.",
        "snapshots.create_confirm_desc_both": "Isso vai gerar novos snapshots de / e /home no destino selecionado. Pode levar bastante tempo dependendo do tamanho.",
        "snapshots.sync_backend_note": (
            "As alterações são aplicadas no sistema (systemd) assim que você salva."
        ),

        # ── Restaurar HOME sem reboot ──
        "snapshots.home_live_title": "Restaurar HOME sem reboot",
        "snapshots.home_live_warning": (
            "Isso substitui os arquivos atuais de /home pelos deste "
            "snapshot, no sistema já rodando (sem live ISO). Ao final, "
            "a sessão gráfica é encerrada (logout) — feche seu trabalho "
            "antes de continuar."
        ),
        "snapshots.home_live_checkbox": "Entendo que a sessão será encerrada e os arquivos atuais de /home serão substituídos",
        "snapshots.home_live_confirm": "Restaurar",
        "snapshots.sync_confirm_title": "Confirmar sincronização",
        "snapshots.sync_confirm_header": "Sincronizar Snapshot",
        "snapshots.sync_confirm_warning": "O snapshot será atualizado com o estado atual do sistema. Apenas arquivos modificados serão transferidos.",
        "snapshots.sync_confirm_button": "Sincronizar",
        "snapshots.pair_sync_title": "Sincronizar também?",
        "snapshots.pair_sync_message": "O snapshot {kind} correspondente também pode ser sincronizado agora, mantendo ROOT e HOME em par.",
        "snapshots.pair_sync_cancel": "Agora não",
        "snapshots.pair_sync_confirm": "Sincronizar {kind}",
        "snapshots.verify_select_title": "Escolher snapshots para verificar",
        "snapshots.verify_select_msg": "Por padrão só o mais recente de cada tipo vem marcado. Marque outros snapshots se quiser verificá-los também:",
        "snapshots.verify_select_confirm": "Verificar selecionados",
        "snapshots.verify_results_title_both": "ROOT e HOME estão desatualizados",
        "snapshots.verify_results_title_multi": "{count} snapshots {kind} estão desatualizados",
        "snapshots.verify_results_title_single": "{kind} está desatualizado",
        "snapshots.verify_results_msg": "O rsync --dry-run encontrou mudanças reais no sistema que ainda não estão nos snapshots abaixo. Escolha quais sincronizar:",
        "snapshots.verify_results_cancel": "Agora não",
        "snapshots.verify_results_sync": "Sincronizar",
        "snapshots.verify_results_sync_all": "Sincronizar todos ({count})",
        "snapshots.verify_results_sync_one": "Sincronizar {kind}",
        "snapshots.verify_results_sync_n": "Sincronizar {count} selecionados",

        # ── Diálogo Sobre ──
        "about.description": "Ferramenta de administração de sistema para Arch Linux —\nsnapshots, backups, ISOs live e diagnósticos.",
        "about.developed_by": "DESENVOLVIDO POR",

        # ── Penguin's Eggs ──
        "eggs.subtitle": "Create, check and install Arch Linux live ISOs",
        "eggs.destination_label": "Destino da ISO:",
        "eggs.not_mounted": "não montado",
        "eggs.no_iso_this_disk": "Sem ISO neste disco",
        "eggs.no_iso_yet": "Nenhuma ISO gerada ainda",
        "eggs.free_of_total": "{free} GB livres de {total} GB  •  {mount}  •  {fs}",
        "eggs.free_percent": "{pct}% livre",
        "eggs.disk_label_free": "livre",
        "eggs.btn_delete": "EXCLUIR",
        "eggs.create_title": "Criar Penguin's Eggs",
        "eggs.create_desc": "Gera uma ISO live (ou move a já pronta pro Ventoy).",
        "eggs.check_title": "Verificar Penguin's Eggs .iso",
        "eggs.check_desc": "Verifica .iso pendente e faz backup automático.",
        "eggs.badge_requires_root": "requer root",
        "eggs.open_broot_title": "Abrir arquivos — broot",
        "eggs.open_broot_desc": "Abre o Ventoy (destino da ISO) no broot.",
        "eggs.open_nautilus_title": "Abrir arquivos — Nautilus",
        "eggs.open_nautilus_desc": "Abre o Ventoy (destino da ISO) no Nautilus.",
        "eggs.install_title_not_installed": "Instalação do Penguin's Eggs e Calamares",
        "eggs.install_desc_not_installed": "Instala o penguins-eggs e o módulo Calamares, se necessário.",
        "eggs.install_action_install": "Instalar",
        "eggs.install_title_installed": "Atualizar Penguin's Eggs",
        "eggs.install_checked_suffix": '<br><span style="color:#60a5fa;">verificado às {time}</span>',
        "eggs.install_version_unknown": "versão instalada",
        "eggs.install_desc_update_available": "Atual: {current} — nova versão v{update} disponível no AUR.{suffix}",
        "eggs.install_action_update": "Atualizar",
        "eggs.install_desc_up_to_date": "Atual: {current} — atualizado, última versão.{suffix}",
        "eggs.install_action_check": "Verificar",
        "eggs.empty_iso_list": "Nenhuma ISO gerada ainda.",
        "eggs.iso_list_header": "ISOs existentes",
        "eggs.force_kill_link": "Parece travado? Forçar encerramento",
        "eggs.executing_prefix": "Executando: {title}",
        "eggs.delete_failed": "Falha ao remover: {err}",
        "eggs.error_running": "Erro ao executar:\n\n{err}",
        "eggs.error_opening": "Não foi possível abrir: {exc}",
        "eggs.creating_title": "Criando Penguin's Eggs...",
        "eggs.creating_status": "Criando ISO...",
        "eggs.updating_before_create_title": "Atualizando Penguin's Eggs...",
        "eggs.updating_before_create_status": "Atualizando antes de criar...",
        "eggs.checking_title": "Verificando Penguin's Eggs...",
        "eggs.checking_status": "Verificando .iso...",
        "eggs.installing_status": "Instalando...",
        "eggs.checking_updates_status": "Verificando atualizações...",
        "eggs.delete_iso_header": "Excluir ISO",
        "eggs.delete_iso_warning": "Esta ação é irreversível. A ISO será permanentemente removida do disco.",
    },
    "en": {
        "eggs_core.status_syncing_dbs": "Syncing package databases...",
        "eggs_core.op_cancelled": "Operation cancelled.",
        "eggs_core.log_error_prefix": "ERROR: {msg}",
        "eggs_core.log_removed": "Removed: {file}",
        "eggs_core.log_removed_count": "--- {count} file(s) removed from {directory} ---",
        "eggs_core.log_cleanup_warning": "WARNING: could not clean {directory}: {exc}",
        "eggs_core.log_broken_symlink": "ERROR: link '{src}' points to '{real_src}', which doesn't exist.",
        "eggs_core.status_moving_to": "Moving to {dest_dir}...",
        "eggs_core.log_moving": "Moving: {src} -> {dest}",
        "eggs_core.log_iso_created": "--- ISO created successfully: {name} ---",
        "eggs_core.status_backing_up": "Backing up to {path}...",
        "eggs_core.log_backup_start": "Starting backup copy to {path}...",
        "eggs_core.log_ready_both": "--- file '{name}' ready on Ventoy and MDSATA ---",
        "eggs_core.log_backup_failed_ventoy_ok": "WARNING: MDSATA backup failed ({msg}), but ISO is already on Ventoy.",
        "eggs_core.log_move_error": "ERROR moving to {dest_dir}: {msg}",
        "eggs_core.log_space_insufficient_header": "WARNING: Insufficient space on destinations:",
        "eggs_core.log_space_mdsata_detail": "  ✗ MDSATA ({path}): {free:.1f} GB free — needs ~{needed:.1f} GB",
        "eggs_core.log_space_estimate": "\nEstimated ISO size: ~{gb:.1f} GB (compressed, based on current / usage)",
        "eggs_core.status_space_mdsata_fail": "Insufficient space on MDSATA — check the backup.",
        "eggs_core.log_space_ok": "INFO: Space verified: estimated ISO ~{gb:.1f} GB | {dest} {dest_free:.1f} GB free | MDSATA {mdsata_free:.1f} GB free",
        "eggs_core.log_space_dest_insufficient": "WARNING: {dest} only has {free:.1f} GB free — needs ~{needed:.1f} GB.",
        "eggs_core.log_no_alt_disk": "No alternative disk with enough space found.",
        "eggs_core.status_space_fail": "Insufficient space — check the destinations.",
        "eggs_core.log_suggesting_alt": "Suggesting {count} alternative disk(s) with enough space...",
        "eggs_core.log_no_alt_chosen": "No alternative destination chosen — operation cancelled.",
        "eggs_core.status_user_cancelled": "Cancelled by user.",
        "eggs_core.log_new_dest_chosen": "New destination chosen: {chosen}",
        "eggs_core.status_checking_devices": "Checking devices...",
        "eggs_core.log_header_create": "=== CREATE PENGUIN'S EGGS ===",
        "eggs_core.log_dest_chosen": "Destination chosen: {dest_dir}",
        "eggs_core.log_updated_before_build": "Penguin's Eggs updated to v{version} before this build.",
        "eggs_core.log_already_latest": "Penguin's Eggs was already on the latest version — build without prior update.",
        "eggs_core.status_mount_fail": "Failed to mount devices.",
        "eggs_core.log_invalid_dest": "ERROR: destination '{dest_dir}' doesn't exist or isn't mounted.",
        "eggs_core.status_invalid_dest": "Invalid destination.",
        "eggs_core.log_existing_iso_found": "Existing ISO found at {parent} — reusing instead of generating another.",
        "eggs_core.status_done_ok": "Completed successfully.",
        "eggs_core.status_op_failed": "Operation failed.",
        "eggs_core.log_cleaning": "Cleaning: {dir}",
        "eggs_core.status_generating_iso": "Generating new ISO (eggs produce)...",
        "eggs_core.log_starting_generate": "STARTING: No .iso found — generating new ISO via eggs produce...",
        "eggs_core.log_iso_generated": "--- ISO generated successfully ---",
        "eggs_core.status_iso_generated_not_found": "ISO generated, but not found to move.",
        "eggs_core.status_generate_fail": "Failed to generate ISO.",
        "eggs_core.log_header_check": "=== CHECK PENGUIN'S EGGS ===",
        "eggs_core.log_iso_found_count": "{count} .iso file(s) found in {dir}",
        "eggs_core.log_no_iso_found": "No .iso found in {a}, {b} or {c}",
        "eggs_core.status_dir_cleaned_nothing": "Directory cleaned — nothing to do.",
        "eggs_core.log_lock_real_process": "WARNING: /var/lib/pacman/db.lck exists and a pacman/paru/yay process is genuinely running — leaving it alone.",
        "eggs_core.log_lock_removed": "Orphaned pacman lock removed (/var/lib/pacman/db.lck) — no pacman/paru/yay process was genuinely running.",
        "eggs_core.log_lock_remove_fail": "WARNING: failed to remove pacman lock: {exc}",
        "eggs_core.log_installing_pacman_contrib": "pacman-contrib not found — installing (needed to check for penguins-eggs updates)...",
        "eggs_core.log_pacman_contrib_installed": "pacman-contrib installed.",
        "eggs_core.log_pacman_contrib_fail": "Could not install pacman-contrib (update check via checkupdates will be unavailable): {err}",
        "eggs_core.status_checking_install": "Checking installation...",
        "eggs_core.log_header_install": "=== INSTALL PENGUIN'S EGGS ===",
        "eggs_core.log_eggs_not_found": "penguins-eggs not found — it will be installed.",
        "eggs_core.log_eggs_already_checking": "penguins-eggs already installed — checking for updates...",
        "eggs_core.log_eggs_via_repo": "penguins-eggs available via repo (chaotic-aur) — using pacman.",
        "eggs_core.title_installing": "Installing...",
        "eggs_core.title_checking_updates": "Checking for updates...",
        "eggs_core.log_pacman_no_update": "pacman confirms: no update available for penguins-eggs.",
        "eggs_core.log_fallback_fresh_eggs": "penguins-eggs not found in any configured repo — falling back to fresh-eggs.sh.",
        "eggs_core.log_calamares_not_found": "Calamares module not found — it will be installed.",
        "eggs_core.log_calamares_already_checking": "Calamares module already installed — checking for updates...",
        "eggs_core.log_settings_autofix": "auto-heal: settings.yml copied to settings.yaml (known penguins-eggs packaging bug on Arch).",
        "eggs_core.log_settings_autofix_fail": "warning: failed to auto-fix settings.yaml ({exc}).",
        "eggs_core.log_verification_done": "--- verification complete ---",
        "eggs_core.status_no_update": "No update available.",
        "eggs_core.word_update": "Update",
        "eggs_core.word_install": "Installation",
        "eggs_core.log_action_done": "--- {action} complete ---",
        "eggs_core.status_action_done_ok": "{action} completed successfully.",
        "eggs_core.status_install_fail": "Installation failed.",
        "menu.idioma": "Language",
        "menu.temas": "Themes",
        "menu.central_logs": "Log center",
        "menu.verificar_atualizacao": "Check for updates",
        "menu.atalhos_teclado": "Keyboard shortcuts",
        "menu.sobre": "About",
        "menu.temas_placeholder_msg": "Theme customization (light/dark/accent colors) hasn't been implemented yet.",
        "menu.verificar_atualizacao_placeholder_msg": "Update checking for Carbonara itself (via git) hasn't been implemented yet.",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Close",
        "common.cancel": "Cancel",
        "common.confirm": "Confirm",
        "common.delete": "Delete",
        "common.restore": "Restore",

        # ── Clonezilla Backups ──────────────────────────────────────────
        "clonezilla.title": "CLONEZILLA BACKUPS",
        "clonezilla.subtitle": "Compression and management of Clonezilla images",
        "clonezilla.empty": (
            "No backups found in /mnt/MDSATA/CLONEZILLA.\n\n"
            "Generate a backup in Clonezilla first — the folder it creates "
            "will show up here automatically once it exists."
        ),
        "clonezilla.refresh_tooltip": "Refresh",
        "clonezilla.section_pending_title": "PENDING",
        "clonezilla.section_pending_subtitle": "Not compressed yet — waiting for action",
        "clonezilla.section_compressed_eyebrow": "COMPRESSED BACKUPS",
        "clonezilla.count_file_singular": "1 file",
        "clonezilla.count_file_plural": "{n} files",
        "clonezilla.total_suffix": "total",
        "clonezilla.uploaded_singular": "1 on Google Drive",
        "clonezilla.uploaded_plural": "{n} on Google Drive",

        "clonezilla.action_compress": "Compress",
        "clonezilla.action_upload": "Upload to Google Drive",
        "clonezilla.action_view_details": "View upload details",
        "clonezilla.action_delete": "Delete",
        "clonezilla.tooltip_uploaded_at": "Already uploaded on {when} — click to re-upload",
        "clonezilla.tooltip_uploaded_no_date": "Already uploaded — click to re-upload",

        "clonezilla.dialog_compress_title": "Compress backup",
        "clonezilla.dialog_compress_message": "Compress '{name}' into .tar.zst?{estimate}",
        "clonezilla.dialog_compress_estimate": (
            "\n\nSize: {gb} GB — this may take a while (heavy CPU usage)."
        ),
        "clonezilla.dialog_compress_confirm": "Compress",
        "clonezilla.dialog_insufficient_space_title": "Not enough space",
        "clonezilla.dialog_insufficient_space_message": (
            "There isn't enough free space on {dir} to safely compress "
            "'{name}'.\n\nRequired (estimated): {needed} GB\n"
            "Available: {free} GB\n\nFree up space at the destination and try again."
        ),
        "clonezilla.dialog_check_space_error": "Couldn't check free space on {dir}: {exc}",
        "clonezilla.dialog_delete_title": "Delete backup",
        "clonezilla.dialog_delete_message": (
            "Delete {what} for '{name}'?\n\n{path}\n\nThis action cannot be undone."
        ),
        "clonezilla.dialog_delete_confirm": "Delete",
        "clonezilla.what_folder": "the original folder",
        "clonezilla.what_archive": "the .tar.zst file",
        "clonezilla.dialog_upload_title": "Upload to Google Drive",
        "clonezilla.dialog_upload_message": (
            "Upload '{filename}' to Google Drive?{size_txt}\n\n"
            "Destination: CLONEZILLA/{year}/{month}\n\nSent via rclone (remote 'gdrive')."
        ),
        "clonezilla.dialog_upload_confirm": "Upload",
        "clonezilla.size_suffix": "\n\nSize: {size}",
        "clonezilla.dialog_reupload_title": "Re-upload to Google Drive",
        "clonezilla.dialog_reupload_message": (
            "'{filename}' was already uploaded{when}.\n\n"
            "Upload it again anyway? This will overwrite the copy on Drive."
        ),
        "clonezilla.dialog_reupload_confirm": "Re-upload",
        "clonezilla.reupload_when": " on {sent_at}",
        "clonezilla.operation_in_progress": "Another exclusive operation is already running: {current}",
        "clonezilla.operation_in_progress_generic": "Another exclusive operation is already running.",
        "clonezilla.compress_op_label": "Compressing {name}",
        "clonezilla.delete_op_label": "Deleting {name}",
        "clonezilla.upload_op_label": "Uploading {name} to Drive",
        "clonezilla.list_error": "Error listing backups: {exc}",

        "clonezilla.upload_progress_title": "Uploading {name}",
        "clonezilla.upload_progress_body_title": "Upload in progress",
        "clonezilla.upload_progress_subtitle": "Uploading {filename} to Google Drive.",
        "clonezilla.upload_progress_preparing": "Preparing to upload {filename}...",
        "clonezilla.upload_log_header": "=== UPLOAD {filename} ===",
        "clonezilla.upload_log_dest": "Destination: CLONEZILLA/{year}/{month}",
        "clonezilla.upload_done_status": "Upload complete.",
        "clonezilla.upload_log_fetching_link": "Fetching folder link on Drive...",
        "clonezilla.upload_log_link": "Link: {link}",
        "clonezilla.upload_log_no_link": "Couldn't get the link (rclone link failed).",
        "clonezilla.upload_failed_status": "Upload failed.",
        "clonezilla.upload_log_error": "ERROR: {msg}",
        "clonezilla.compress_process_error": "Compression process exited with code {rc}.",
        "clonezilla.delete_process_error": "Delete process exited with code {rc}.",

        "clonezilla.details_title": "Backup on Google Drive",
        "clonezilla.details_sent_at": "UPLOADED ON",
        "clonezilla.details_size": "SIZE",
        "clonezilla.details_drive_folder": "DRIVE FOLDER",
        "clonezilla.details_open_drive": "Open on Drive",
        "clonezilla.details_no_link_tooltip": "Drive link not available for this upload",

        # ── Snapshots/Timeshift — main panel + restore chooser ──
        "snapshots.synced_today": "synced today",
        "snapshots.synced_1_day": "last sync 1 day ago",
        "snapshots.synced_n_days": "last sync {n} days ago",
        "snapshots.never_synced": "never synced",
        "snapshots.size_label": "snapshot size",
        "snapshots.last_sync": "last sync  {date}",
        "snapshots.tooltip_restore": "Restore this snapshot",
        "snapshots.tooltip_sync": "Sync this snapshot",
        "snapshots.tooltip_delete": "Delete this snapshot",
        "snapshots.destination_label": "Destination",
        "snapshots.scope_label": "Scope",
        "snapshots.scope_root_title": "ROOT ONLY",
        "snapshots.scope_root_subtitle": "Snapshot only the system root",
        "snapshots.scope_home_title": "HOME ONLY",
        "snapshots.scope_home_subtitle": "Snapshot only /home",
        "snapshots.scope_both_title": "ROOT+HOME",
        "snapshots.scope_both_subtitle": "Snapshot both root and home",
        "snapshots.select_destination": "Select a backup destination",
        "snapshots.btn_refresh_space": "REFRESH SPACE",
        "snapshots.btn_create_snapshot": "CREATE SNAPSHOT",
        "snapshots.fab_verify_tooltip": "Sync Snapshots",
        "snapshots.no_destinations_found": "No backup destinations found",
        "snapshots.mount_a_disk": "Mount a disk under /mnt or /media",
        "snapshots.free_of_total": "{free} free of {total} • {mountpoint} • {fs_type}",
        "snapshots.free_percent": "{pct}% free",
        "snapshots.combo_item": " {label}  •  {free} free  •  {mountpoint}  •  {fs_type}",
        "snapshots.empty_title": "No snapshots yet",
        "snapshots.empty_subtitle": "Use Create Snapshot above to get started.",
        "snapshots.select_destination_first": "Select a destination first.",
        "snapshots.op_already_running": "Another operation is already running: {name}",
        "snapshots.op_exclusive_running": "Another exclusive operation is already running.",
        "snapshots.backup_exit_code": "Backup process exited with code {rc}.",
        "snapshots.restore_dialog_title": "Restore Snapshot",
        "snapshots.choose_restore_type": "CHOOSE THE RESTORE TYPE",
        "snapshots.restore_full_title": "Full System Restore",
        "snapshots.restore_full_desc": "Generates a bash script to restore the complete system via live ISO.",
        "snapshots.restore_full_badge": "requires reboot",
        "snapshots.restore_browser_title": "File Browser",
        "snapshots.restore_browser_desc": "Browse and restore individual files/folders from the snapshot without a reboot.",
        "snapshots.restore_alt_title": "Restore to alternate disk",
        "snapshots.restore_alt_desc": "Copies the entire snapshot to another mounted disk/partition.",
        "snapshots.restore_home_live_title": "Restore HOME without reboot",
        "snapshots.restore_home_live_desc": (
            "Restores the entire HOME on the currently running system — no live ISO needed. "
            "Ends the session at the end (logout)."
        ),
        "snapshots.instructions_dialog_title": "Restore Script Generated",
        "snapshots.instructions_step1": "1.  Boot via Ventoy → select an Arch ISO:",
        "snapshots.instructions_no_iso": "⚠  No ISO found in /mnt/VENTOY",
        "snapshots.instructions_step2": "2.  In the live ISO shell, run:",
        "snapshots.instructions_script_desc": "The script mounts the disks, restores, and reinstalls GRUB automatically.",
        "snapshots.instructions_confirm_warning": "Confirm by typing RESTAURAR when prompted.",
        "snapshots.instructions_files_generated": "Files generated at:",
        "snapshots.instructions_script_label": "  Script:       {path}",
        "snapshots.instructions_notes_label": "  Notes:        {path}",
        "snapshots.btn_understood": "Understood",

        # ── File Browser / Confirm Restore / Restore to alternate disk ──
        "snapshots.filebrowser_title": "File Browser",
        "snapshots.filebrowser_selected_label": "Selected for restore:",
        "snapshots.filebrowser_selected_placeholder": "No items selected.\nSelect files/folders in the tree.",
        "snapshots.filebrowser_conflict_label": "If the file already exists on the system:",
        "snapshots.filebrowser_overwrite": "Overwrite",
        "snapshots.filebrowser_skip": "Skip existing",
        "snapshots.filebrowser_btn_restore": "  Restore selected",
        "snapshots.filebrowser_loading": "loading...",
        "snapshots.filebrowser_restore_done": "─── Restore complete ───",
        "snapshots.filebrowser_error": "ERROR: {msg}",
        "snapshots.confirm_restore_title": "Confirm Restore",
        "snapshots.confirm_restore_overwriting": "overwriting existing files",
        "snapshots.confirm_restore_skipping": "skipping existing files",
        "snapshots.confirm_restore_message": "Restore {label} to the system,\n{ct}?",
        "snapshots.altrestore_title": "Restore to alternate disk",
        "snapshots.altrestore_select_dest": "Select the destination disk:",
        "snapshots.altrestore_options_label": "Options:",
        "snapshots.altrestore_opt_delete": "Sync (--delete)",
        "snapshots.altrestore_opt_hardlinks": "Preserve hard-links (-H)",
        "snapshots.altrestore_warning": "Existing content at the destination may be altered.",
        "snapshots.altrestore_btn_start": "Start Restore",
        "snapshots.altrestore_no_disks": "No alternate disk available.",
        "snapshots.altrestore_combo_item": "{label}  •  {free} free  •  {mountpoint}",
        "snapshots.altrestore_dest_info": "{free} free of {total} • {fs_type}",
        "snapshots.altrestore_insufficient_space": (
            "{base_info}  —  insufficient space (snapshot is {size}, short by {missing})"
        ),

        # ── Confirm delete / removal progress ──
        "snapshots.delete_confirm_window_title": "Confirm Deletion",
        "snapshots.delete_confirm_header": "Delete Snapshot",
        "snapshots.delete_warning": "This action is irreversible. The snapshot will be permanently removed from disk.",
        "snapshots.delete_last_root_warning": (
            "This is the last ROOT snapshot — carbonara-restore.sh will also be "
            "removed, since there will be nothing left to restore."
        ),
        "snapshots.delete_password_note": "You'll be asked for the root password to complete the deletion.",
        "snapshots.delete_progress_title": "Removing Snapshot",
        "snapshots.delete_awaiting_auth": "Awaiting authentication...",
        "snapshots.delete_failed_message": "Failed to remove snapshot:\n\n{msg}",
        "snapshots.delete_cancelled": "Operation cancelled.",
        "snapshots.delete_success": "Snapshot {name} removed successfully.",

        # ── Automatic sync (badge + dialog) ──
        "snapshots.sync_badge_title": "Auto sync",
        "snapshots.sync_badge_disabled": "disabled",
        "snapshots.sync_badge_next": "next {when}",
        "snapshots.sync_dialog_title": "Automatic Sync",
        "snapshots.sync_enabled": "Enabled",
        "snapshots.sync_disabled": "Disabled",
        "snapshots.sync_frequency_label": "FREQUENCY",
        "snapshots.sync_freq_daily": "Daily",
        "snapshots.sync_freq_weekly": "Weekly",
        "snapshots.sync_freq_custom": "Custom",
        "snapshots.sync_time_label": "TIME",
        "snapshots.sync_scope_label": "SCOPE",
        "snapshots.sync_last_run_label": "Last run",
        "snapshots.sync_next_run_label": "Next run",
        "snapshots.sync_never_run": "Never ran",
        "snapshots.sync_not_scheduled": "Not scheduled",
        "snapshots.sync_weekday_label": "DAY OF WEEK",
        "snapshots.sync_custom_label": "CUSTOM EXPRESSION (systemd OnCalendar)",
        "snapshots.sync_custom_hint": "E.g: *-*-* 03:00:00 (every day at 3am) · Sun *-*-* 04:00:00 (Sundays at 4am)",
        "snapshots.sync_weekday_mon": "Mon",
        "snapshots.sync_weekday_tue": "Tue",
        "snapshots.sync_weekday_wed": "Wed",
        "snapshots.sync_weekday_thu": "Thu",
        "snapshots.sync_weekday_fri": "Fri",
        "snapshots.sync_weekday_sat": "Sat",
        "snapshots.sync_weekday_sun": "Sun",
        "snapshots.sync_save_button": "Save schedule",
        "snapshots.sync_cancel_button": "Cancel schedule",
        "snapshots.sync_destinations_label": "DESTINATIONS TO SYNC",
        "snapshots.sync_no_destinations_found": "No backup destination found on the system.",
        "snapshots.sync_no_destination": "Select a backup destination before saving the schedule.",
        "snapshots.sync_install_failed": "Failed to apply the schedule to the system:\n\n{msg}",
        "snapshots.sync_result_success": "success",
        "snapshots.sync_result_failed": "failed",
        "snapshots.sync_result_skipped": "skipped",
        "snapshots.sync_result_nothing": "nothing to sync",
        "snapshots.sync_last_run_value": "{when} · {result}",
        "snapshots.sync_toast_success": "Automatic sync completed — {kinds}",
        "snapshots.sync_toast_failed": "Automatic sync failed — check the schedule for details",
        "snapshots.sync_toast_nothing": "Automatic sync is enabled but there's no snapshot to sync yet — create one first",

        # ── Confirm snapshot creation ──
        "snapshots.create_confirm_title": "Create Snapshot",
        "snapshots.create_confirm_body": "You're about to create a snapshot with the scope:",
        "snapshots.create_confirm_desc_root": "This will generate a new snapshot of / on the selected destination. It can take a while depending on the size.",
        "snapshots.create_confirm_desc_home": "This will generate a new snapshot of /home on the selected destination. It can take a while depending on the size.",
        "snapshots.create_confirm_desc_both": "This will generate new snapshots of / and /home on the selected destination. It can take a while depending on the size.",
        "snapshots.sync_backend_note": (
            "Changes take effect on the system (systemd) as soon as you save."
        ),

        # ── Restore HOME without reboot ──
        "snapshots.home_live_title": "Restore HOME without reboot",
        "snapshots.home_live_warning": (
            "This replaces the current /home files with this snapshot's, "
            "on the already-running system (no live ISO). At the end, "
            "the graphical session ends (logout) — close your work "
            "before continuing."
        ),
        "snapshots.home_live_checkbox": "I understand the session will end and the current /home files will be replaced",
        "snapshots.home_live_confirm": "Restore",
        "snapshots.sync_confirm_title": "Confirm sync",
        "snapshots.sync_confirm_header": "Sync Snapshot",
        "snapshots.sync_confirm_warning": "The snapshot will be updated with the current system state. Only modified files will be transferred.",
        "snapshots.sync_confirm_button": "Sync",
        "snapshots.pair_sync_title": "Sync as well?",
        "snapshots.pair_sync_message": "The corresponding {kind} snapshot can also be synced now, keeping ROOT and HOME paired.",
        "snapshots.pair_sync_cancel": "Not now",
        "snapshots.pair_sync_confirm": "Sync {kind}",
        "snapshots.verify_select_title": "Choose snapshots to verify",
        "snapshots.verify_select_msg": "By default only the most recent of each type is checked. Check other snapshots too if you want to verify them as well:",
        "snapshots.verify_select_confirm": "Verify selected",
        "snapshots.verify_results_title_both": "ROOT and HOME are outdated",
        "snapshots.verify_results_title_multi": "{count} {kind} snapshots are outdated",
        "snapshots.verify_results_title_single": "{kind} is outdated",
        "snapshots.verify_results_msg": "rsync --dry-run found real changes on the system that aren't in the snapshots below yet. Choose which to sync:",
        "snapshots.verify_results_cancel": "Not now",
        "snapshots.verify_results_sync": "Sync",
        "snapshots.verify_results_sync_all": "Sync all ({count})",
        "snapshots.verify_results_sync_one": "Sync {kind}",
        "snapshots.verify_results_sync_n": "Sync {count} selected",

        # ── About dialog ──
        "about.description": "System administration tool for Arch Linux —\nsnapshots, backups, live ISOs, and diagnostics.",
        "about.developed_by": "DEVELOPED BY",

        # ── Penguin's Eggs ──
        "eggs.subtitle": "Create, check and install Arch Linux live ISOs",
        "eggs.destination_label": "ISO destination:",
        "eggs.not_mounted": "not mounted",
        "eggs.no_iso_this_disk": "No ISO on this disk",
        "eggs.no_iso_yet": "No ISO generated yet",
        "eggs.free_of_total": "{free} GB free of {total} GB  •  {mount}  •  {fs}",
        "eggs.free_percent": "{pct}% free",
        "eggs.disk_label_free": "free",
        "eggs.btn_delete": "DELETE",
        "eggs.create_title": "Create Penguin's Eggs",
        "eggs.create_desc": "Generates a live ISO (or moves the ready one to Ventoy).",
        "eggs.check_title": "Check Penguin's Eggs .iso",
        "eggs.check_desc": "Checks for a pending .iso and backs it up automatically.",
        "eggs.badge_requires_root": "requires root",
        "eggs.open_broot_title": "Open files — broot",
        "eggs.open_broot_desc": "Opens Ventoy (ISO destination) in broot.",
        "eggs.open_nautilus_title": "Open files — Nautilus",
        "eggs.open_nautilus_desc": "Opens Ventoy (ISO destination) in Nautilus.",
        "eggs.install_title_not_installed": "Penguin's Eggs and Calamares Install",
        "eggs.install_desc_not_installed": "Installs penguins-eggs and the Calamares module, if needed.",
        "eggs.install_action_install": "Install",
        "eggs.install_title_installed": "Update Penguin's Eggs",
        "eggs.install_checked_suffix": '<br><span style="color:#60a5fa;">checked at {time}</span>',
        "eggs.install_version_unknown": "installed version",
        "eggs.install_desc_update_available": "Current: {current} — new version v{update} available on the AUR.{suffix}",
        "eggs.install_action_update": "Update",
        "eggs.install_desc_up_to_date": "Current: {current} — up to date, latest version.{suffix}",
        "eggs.install_action_check": "Check",
        "eggs.empty_iso_list": "No ISO generated yet.",
        "eggs.iso_list_header": "Existing ISOs",
        "eggs.force_kill_link": "Seems stuck? Force stop",
        "eggs.executing_prefix": "Running: {title}",
        "eggs.delete_failed": "Failed to remove: {err}",
        "eggs.error_running": "Error running:\n\n{err}",
        "eggs.error_opening": "Could not open: {exc}",
        "eggs.creating_title": "Creating Penguin's Eggs...",
        "eggs.creating_status": "Creating ISO...",
        "eggs.updating_before_create_title": "Updating Penguin's Eggs...",
        "eggs.updating_before_create_status": "Updating before creating...",
        "eggs.checking_title": "Checking Penguin's Eggs...",
        "eggs.checking_status": "Checking .iso...",
        "eggs.installing_status": "Installing...",
        "eggs.checking_updates_status": "Checking for updates...",
        "eggs.delete_iso_header": "Delete ISO",
        "eggs.delete_iso_warning": "This action is irreversible. The ISO will be permanently removed from disk.",
    },
    "es": {
        "eggs_core.status_syncing_dbs": "Sincronizando bases de datos de paquetes...",
        "eggs_core.op_cancelled": "Operación cancelada.",
        "eggs_core.log_error_prefix": "ERROR: {msg}",
        "eggs_core.log_removed": "Eliminado: {file}",
        "eggs_core.log_removed_count": "--- {count} archivo(s) eliminado(s) de {directory} ---",
        "eggs_core.log_cleanup_warning": "AVISO: no se pudo limpiar {directory}: {exc}",
        "eggs_core.log_broken_symlink": "ERROR: el enlace '{src}' apunta a '{real_src}', que no existe.",
        "eggs_core.status_moving_to": "Moviendo a {dest_dir}...",
        "eggs_core.log_moving": "Moviendo: {src} -> {dest}",
        "eggs_core.log_iso_created": "--- ISO creada correctamente: {name} ---",
        "eggs_core.status_backing_up": "Haciendo copia de seguridad en {path}...",
        "eggs_core.log_backup_start": "Iniciando copia de seguridad a {path}...",
        "eggs_core.log_ready_both": "--- archivo '{name}' listo en Ventoy y en MDSATA ---",
        "eggs_core.log_backup_failed_ventoy_ok": "AVISO: la copia en MDSATA falló ({msg}), pero la ISO ya está en Ventoy.",
        "eggs_core.log_move_error": "ERROR al mover a {dest_dir}: {msg}",
        "eggs_core.log_space_insufficient_header": "AVISO: Espacio insuficiente en los destinos:",
        "eggs_core.log_space_mdsata_detail": "  ✗ MDSATA ({path}): {free:.1f} GB libres — necesita ~{needed:.1f} GB",
        "eggs_core.log_space_estimate": "\nTamaño estimado de la ISO: ~{gb:.1f} GB (comprimido, según el uso actual de /)",
        "eggs_core.status_space_mdsata_fail": "Espacio insuficiente en MDSATA — revise la copia de seguridad.",
        "eggs_core.log_space_ok": "INFO: Espacio verificado: ISO estimada ~{gb:.1f} GB | {dest} {dest_free:.1f} GB libres | MDSATA {mdsata_free:.1f} GB libres",
        "eggs_core.log_space_dest_insufficient": "AVISO: {dest} solo tiene {free:.1f} GB libres — necesita ~{needed:.1f} GB.",
        "eggs_core.log_no_alt_disk": "No se encontró ningún disco alternativo con espacio suficiente.",
        "eggs_core.status_space_fail": "Espacio insuficiente — revise los destinos.",
        "eggs_core.log_suggesting_alt": "Sugiriendo {count} disco(s) alternativo(s) con espacio suficiente...",
        "eggs_core.log_no_alt_chosen": "No se eligió ningún destino alternativo — operación cancelada.",
        "eggs_core.status_user_cancelled": "Cancelado por el usuario.",
        "eggs_core.log_new_dest_chosen": "Nuevo destino elegido: {chosen}",
        "eggs_core.status_checking_devices": "Verificando dispositivos...",
        "eggs_core.log_header_create": "=== CREATE PENGUIN'S EGGS ===",
        "eggs_core.log_dest_chosen": "Destino elegido: {dest_dir}",
        "eggs_core.log_updated_before_build": "Penguin's Eggs actualizado a v{version} antes de este build.",
        "eggs_core.log_already_latest": "Penguin's Eggs ya estaba en la versión más reciente — build sin actualización previa.",
        "eggs_core.status_mount_fail": "Error al montar dispositivos.",
        "eggs_core.log_invalid_dest": "ERROR: el destino '{dest_dir}' no existe o no está montado.",
        "eggs_core.status_invalid_dest": "Destino inválido.",
        "eggs_core.log_existing_iso_found": "ISO existente encontrada en {parent} — reutilizando en vez de generar otra.",
        "eggs_core.status_done_ok": "Completado correctamente.",
        "eggs_core.status_op_failed": "Falló la operación.",
        "eggs_core.log_cleaning": "Limpiando: {dir}",
        "eggs_core.status_generating_iso": "Generando nueva ISO (eggs produce)...",
        "eggs_core.log_starting_generate": "INICIANDO: No se encontró ninguna .iso — generando nueva ISO vía eggs produce...",
        "eggs_core.log_iso_generated": "--- ISO generada correctamente ---",
        "eggs_core.status_iso_generated_not_found": "ISO generada, pero no se encontró para mover.",
        "eggs_core.status_generate_fail": "Error al generar la ISO.",
        "eggs_core.log_header_check": "=== CHECK PENGUIN'S EGGS ===",
        "eggs_core.log_iso_found_count": "{count} archivo(s) .iso encontrado(s) en {dir}",
        "eggs_core.log_no_iso_found": "No se encontró ninguna .iso en {a}, {b} o {c}",
        "eggs_core.status_dir_cleaned_nothing": "Directorio limpiado — nada que hacer.",
        "eggs_core.log_lock_real_process": "AVISO: /var/lib/pacman/db.lck existe y hay un proceso pacman/paru/yay realmente en ejecución — no se tocará.",
        "eggs_core.log_lock_removed": "Bloqueo huérfano de pacman eliminado (/var/lib/pacman/db.lck) — ningún proceso pacman/paru/yay estaba realmente en ejecución.",
        "eggs_core.log_lock_remove_fail": "AVISO: no se pudo eliminar el bloqueo de pacman: {exc}",
        "eggs_core.log_installing_pacman_contrib": "pacman-contrib no encontrado — instalando (necesario para comprobar actualizaciones de penguins-eggs)...",
        "eggs_core.log_pacman_contrib_installed": "pacman-contrib instalado.",
        "eggs_core.log_pacman_contrib_fail": "No se pudo instalar pacman-contrib (la comprobación de actualizaciones vía checkupdates no estará disponible): {err}",
        "eggs_core.status_checking_install": "Verificando instalación...",
        "eggs_core.log_header_install": "=== INSTALL PENGUIN'S EGGS ===",
        "eggs_core.log_eggs_not_found": "penguins-eggs no encontrado — se instalará.",
        "eggs_core.log_eggs_already_checking": "penguins-eggs ya instalado — verificando actualización...",
        "eggs_core.log_eggs_via_repo": "penguins-eggs disponible vía repo (chaotic-aur) — usando pacman.",
        "eggs_core.title_installing": "Instalando...",
        "eggs_core.title_checking_updates": "Verificando actualizaciones...",
        "eggs_core.log_pacman_no_update": "pacman confirma: no hay actualización disponible para penguins-eggs.",
        "eggs_core.log_fallback_fresh_eggs": "penguins-eggs no encontrado en ningún repositorio configurado — recurriendo a fresh-eggs.sh (alternativa).",
        "eggs_core.log_calamares_not_found": "módulo Calamares no encontrado — se instalará.",
        "eggs_core.log_calamares_already_checking": "módulo Calamares ya instalado — verificando actualización...",
        "eggs_core.log_settings_autofix": "auto-corrección: settings.yml copiado a settings.yaml (bug conocido del empaquetado de penguins-eggs en Arch).",
        "eggs_core.log_settings_autofix_fail": "aviso: no se pudo auto-corregir settings.yaml ({exc}).",
        "eggs_core.log_verification_done": "--- verificación completada ---",
        "eggs_core.status_no_update": "No hay actualización disponible.",
        "eggs_core.word_update": "Actualización",
        "eggs_core.word_install": "Instalación",
        "eggs_core.log_action_done": "--- {action} completada ---",
        "eggs_core.status_action_done_ok": "{action} completada correctamente.",
        "eggs_core.status_install_fail": "Falló la instalación.",
        "menu.idioma": "Idioma",
        "menu.temas": "Temas",
        "menu.central_logs": "Centro de registros",
        "menu.verificar_atualizacao": "Buscar actualizaciones",
        "menu.atalhos_teclado": "Atajos de teclado",
        "menu.sobre": "Acerca de",
        "menu.temas_placeholder_msg": "La personalización de temas (claro/oscuro/colores de acento) todavía no está implementada.",
        "menu.verificar_atualizacao_placeholder_msg": "La verificación de actualizaciones del propio Carbonara (vía git) todavía no está implementada.",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Cerrar",
        "common.cancel": "Cancelar",
        "common.confirm": "Confirmar",
        "common.delete": "Eliminar",
        "common.restore": "Restaurar",

        # ── Clonezilla Backups — español a propósito con frases más largas
        # que pt/en, pra servir de stress-test do layout (botões, badges,
        # tooltips) antes de replicar pras outras páginas ──────────────
        "clonezilla.title": "COPIAS DE SEGURIDAD DE CLONEZILLA",
        "clonezilla.subtitle": "Compresión y administración de las imágenes de Clonezilla",
        "clonezilla.empty": (
            "No se encontraron copias de seguridad en /mnt/MDSATA/CLONEZILLA.\n\n"
            "Genere primero una copia de seguridad en Clonezilla — la carpeta "
            "que se crea aparecerá aquí automáticamente en cuanto exista."
        ),
        "clonezilla.refresh_tooltip": "Actualizar",
        "clonezilla.section_pending_title": "PENDIENTES",
        "clonezilla.section_pending_subtitle": "Todavía no comprimidos — esperando una acción",
        "clonezilla.section_compressed_eyebrow": "COPIAS DE SEGURIDAD COMPRIMIDAS",
        "clonezilla.count_file_singular": "1 archivo",
        "clonezilla.count_file_plural": "{n} archivos",
        "clonezilla.total_suffix": "en total",
        "clonezilla.uploaded_singular": "1 en Google Drive",
        "clonezilla.uploaded_plural": "{n} en Google Drive",

        "clonezilla.action_compress": "Comprimir",
        "clonezilla.action_upload": "Subir a Google Drive",
        "clonezilla.action_view_details": "Ver detalles del envío",
        "clonezilla.action_delete": "Eliminar",
        "clonezilla.tooltip_uploaded_at": "Ya se envió el {when} — haga clic para reenviar",
        "clonezilla.tooltip_uploaded_no_date": "Ya se envió — haga clic para reenviar",

        "clonezilla.dialog_compress_title": "Comprimir copia de seguridad",
        "clonezilla.dialog_compress_message": "¿Comprimir '{name}' en formato .tar.zst?{estimate}",
        "clonezilla.dialog_compress_estimate": (
            "\n\nTamaño: {gb} GB — esto puede tardar bastante tiempo "
            "(uso intensivo de CPU)."
        ),
        "clonezilla.dialog_compress_confirm": "Comprimir",
        "clonezilla.dialog_insufficient_space_title": "Espacio insuficiente",
        "clonezilla.dialog_insufficient_space_message": (
            "No hay suficiente espacio libre en {dir} para comprimir "
            "'{name}' de forma segura.\n\nNecesario (estimado): {needed} GB\n"
            "Disponible: {free} GB\n\nLibere espacio en el destino e "
            "inténtelo de nuevo."
        ),
        "clonezilla.dialog_check_space_error": (
            "No se pudo comprobar el espacio libre en {dir}: {exc}"
        ),
        "clonezilla.dialog_delete_title": "Eliminar copia de seguridad",
        "clonezilla.dialog_delete_message": (
            "¿Eliminar {what} de '{name}'?\n\n{path}\n\n"
            "Esta acción no se puede deshacer."
        ),
        "clonezilla.dialog_delete_confirm": "Eliminar",
        "clonezilla.what_folder": "la carpeta original",
        "clonezilla.what_archive": "el archivo .tar.zst",
        "clonezilla.dialog_upload_title": "Subir a Google Drive",
        "clonezilla.dialog_upload_message": (
            "¿Subir '{filename}' a Google Drive?{size_txt}\n\n"
            "Destino: CLONEZILLA/{year}/{month}\n\nSe envía mediante rclone (remote 'gdrive')."
        ),
        "clonezilla.dialog_upload_confirm": "Subir",
        "clonezilla.size_suffix": "\n\nTamaño: {size}",
        "clonezilla.dialog_reupload_title": "Reenviar a Google Drive",
        "clonezilla.dialog_reupload_message": (
            "'{filename}' ya se había enviado{when}.\n\n"
            "¿Enviarlo de nuevo de todas formas? Esto sobrescribirá la copia en Drive."
        ),
        "clonezilla.dialog_reupload_confirm": "Reenviar",
        "clonezilla.reupload_when": " el {sent_at}",
        "clonezilla.operation_in_progress": (
            "Ya hay otra operación exclusiva en curso: {current}"
        ),
        "clonezilla.operation_in_progress_generic": "Ya hay otra operación exclusiva en curso.",
        "clonezilla.compress_op_label": "Comprimiendo {name}",
        "clonezilla.delete_op_label": "Eliminando {name}",
        "clonezilla.upload_op_label": "Enviando {name} a Drive",
        "clonezilla.list_error": "Error al listar las copias de seguridad: {exc}",

        "clonezilla.upload_progress_title": "Enviando {name}",
        "clonezilla.upload_progress_body_title": "Envío en curso",
        "clonezilla.upload_progress_subtitle": "Enviando {filename} a Google Drive.",
        "clonezilla.upload_progress_preparing": "Preparando el envío de {filename}...",
        "clonezilla.upload_log_header": "=== ENVÍO {filename} ===",
        "clonezilla.upload_log_dest": "Destino: CLONEZILLA/{year}/{month}",
        "clonezilla.upload_done_status": "Envío completado.",
        "clonezilla.upload_log_fetching_link": "Obteniendo el enlace de la carpeta en Drive...",
        "clonezilla.upload_log_link": "Enlace: {link}",
        "clonezilla.upload_log_no_link": "No se pudo obtener el enlace (rclone link falló).",
        "clonezilla.upload_failed_status": "El envío falló.",
        "clonezilla.upload_log_error": "ERROR: {msg}",
        "clonezilla.compress_process_error": (
            "El proceso de compresión terminó con el código {rc}."
        ),
        "clonezilla.delete_process_error": (
            "El proceso de eliminación terminó con el código {rc}."
        ),

        "clonezilla.details_title": "Copia de seguridad en Google Drive",
        "clonezilla.details_sent_at": "ENVIADO EL",
        "clonezilla.details_size": "TAMAÑO",
        "clonezilla.details_drive_folder": "CARPETA EN DRIVE",
        "clonezilla.details_open_drive": "Abrir en Drive",
        "clonezilla.details_no_link_tooltip": "El enlace de Drive no está disponible para este envío",

        # ── Snapshots/Timeshift — panel principal + selector de restauración,
        # en español a propósito con frases más largas (mismo criterio del
        # Clonezilla) para seguir probando el layout ──────────────────────
        "snapshots.synced_today": "sincronizado hoy",
        "snapshots.synced_1_day": "última sincronización hace 1 día",
        "snapshots.synced_n_days": "última sincronización hace {n} días",
        "snapshots.never_synced": "nunca sincronizado",
        "snapshots.size_label": "tamaño del snapshot",
        "snapshots.last_sync": "última sincronización  {date}",
        "snapshots.tooltip_restore": "Restaurar este snapshot",
        "snapshots.tooltip_sync": "Sincronizar este snapshot",
        "snapshots.tooltip_delete": "Eliminar este snapshot",
        "snapshots.destination_label": "Destino",
        "snapshots.scope_label": "Alcance",
        "snapshots.scope_root_title": "SOLO ROOT",
        "snapshots.scope_root_subtitle": "Crear snapshot solo de la raíz del sistema",
        "snapshots.scope_home_title": "SOLO HOME",
        "snapshots.scope_home_subtitle": "Crear snapshot solo de /home",
        "snapshots.scope_both_title": "ROOT+HOME",
        "snapshots.scope_both_subtitle": "Crear snapshot de la raíz y de home juntos",
        "snapshots.select_destination": "Seleccione un destino de copia de seguridad",
        "snapshots.btn_refresh_space": "ACTUALIZAR ESPACIO",
        "snapshots.btn_create_snapshot": "CREAR SNAPSHOT",
        "snapshots.fab_verify_tooltip": "Sincronizar Snapshots",
        "snapshots.no_destinations_found": "No se encontraron destinos de copia de seguridad",
        "snapshots.mount_a_disk": "Monte un disco en /mnt o /media",
        "snapshots.free_of_total": "{free} libres de {total} • {mountpoint} • {fs_type}",
        "snapshots.free_percent": "{pct}% libre",
        "snapshots.combo_item": " {label}  •  {free} libres  •  {mountpoint}  •  {fs_type}",
        "snapshots.empty_title": "Todavía no hay snapshots",
        "snapshots.empty_subtitle": "Use Crear Snapshot arriba para empezar.",
        "snapshots.select_destination_first": "Seleccione primero un destino.",
        "snapshots.op_already_running": "Ya hay otra operación en curso: {name}",
        "snapshots.op_exclusive_running": "Ya hay otra operación exclusiva en curso.",
        "snapshots.backup_exit_code": "El proceso de copia de seguridad terminó con el código {rc}.",
        "snapshots.restore_dialog_title": "Restaurar Snapshot",
        "snapshots.choose_restore_type": "ELIJA EL TIPO DE RESTAURACIÓN",
        "snapshots.restore_full_title": "Restauración completa del sistema",
        "snapshots.restore_full_desc": (
            "Genera un script bash para restaurar el sistema completo mediante una ISO live."
        ),
        "snapshots.restore_full_badge": "requiere reinicio",
        "snapshots.restore_browser_title": "Explorador de archivos",
        "snapshots.restore_browser_desc": (
            "Explore y restaure archivos o carpetas individuales del snapshot sin reiniciar."
        ),
        "snapshots.restore_alt_title": "Restaurar en un disco alternativo",
        "snapshots.restore_alt_desc": (
            "Copia el snapshot completo a otro disco o partición montado."
        ),
        "snapshots.restore_home_live_title": "Restaurar HOME sin reiniciar",
        "snapshots.restore_home_live_desc": (
            "Restaura toda la carpeta HOME en el sistema que está ejecutándose ahora — "
            "sin necesidad de una ISO live. Cierra la sesión al finalizar (logout)."
        ),
        "snapshots.instructions_dialog_title": "Script de restauración generado",
        "snapshots.instructions_step1": "1.  Arranque mediante Ventoy → seleccione una ISO de Arch:",
        "snapshots.instructions_no_iso": "⚠  No se encontró ninguna ISO en /mnt/VENTOY",
        "snapshots.instructions_step2": "2.  En la shell de la ISO live, ejecute:",
        "snapshots.instructions_script_desc": (
            "El script monta los discos, restaura los datos y reinstala GRUB automáticamente."
        ),
        "snapshots.instructions_confirm_warning": (
            "Confirme escribiendo RESTAURAR cuando se le solicite."
        ),
        "snapshots.instructions_files_generated": "Archivos generados en:",
        "snapshots.instructions_script_label": "  Script:       {path}",
        "snapshots.instructions_notes_label": "  Notas:        {path}",
        "snapshots.btn_understood": "Entendido",

        # ── Explorador de archivos / Confirmar restauración / Restaurar
        # en disco alternativo ──────────────────────────────────────────
        "snapshots.filebrowser_title": "Explorador de archivos",
        "snapshots.filebrowser_selected_label": "Seleccionados para restaurar:",
        "snapshots.filebrowser_selected_placeholder": (
            "Ningún elemento seleccionado.\nSeleccione archivos/carpetas en el árbol."
        ),
        "snapshots.filebrowser_conflict_label": "Si el archivo ya existe en el sistema:",
        "snapshots.filebrowser_overwrite": "Sobrescribir",
        "snapshots.filebrowser_skip": "Omitir existentes",
        "snapshots.filebrowser_btn_restore": "  Restaurar seleccionados",
        "snapshots.filebrowser_loading": "cargando...",
        "snapshots.filebrowser_restore_done": "─── Restauración completada ───",
        "snapshots.filebrowser_error": "ERROR: {msg}",
        "snapshots.confirm_restore_title": "Confirmar restauración",
        "snapshots.confirm_restore_overwriting": "sobrescribiendo los existentes",
        "snapshots.confirm_restore_skipping": "omitiendo los existentes",
        "snapshots.confirm_restore_message": "¿Restaurar {label} en el sistema,\n{ct}?",
        "snapshots.altrestore_title": "Restaurar en un disco alternativo",
        "snapshots.altrestore_select_dest": "Seleccione el disco de destino:",
        "snapshots.altrestore_options_label": "Opciones:",
        "snapshots.altrestore_opt_delete": "Sincronizar (--delete)",
        "snapshots.altrestore_opt_hardlinks": "Conservar hard-links (-H)",
        "snapshots.altrestore_warning": "El contenido existente en el destino puede modificarse.",
        "snapshots.altrestore_btn_start": "Iniciar restauración",
        "snapshots.altrestore_no_disks": "No hay ningún disco alternativo disponible.",
        "snapshots.altrestore_combo_item": "{label}  •  {free} libres  •  {mountpoint}",
        "snapshots.altrestore_dest_info": "{free} libres de {total} • {fs_type}",
        "snapshots.altrestore_insufficient_space": (
            "{base_info}  —  espacio insuficiente (el snapshot pesa {size}, "
            "faltan {missing})"
        ),

        # ── Confirmar eliminación / progreso de eliminación ──
        "snapshots.delete_confirm_window_title": "Confirmar eliminación",
        "snapshots.delete_confirm_header": "Eliminar Snapshot",
        "snapshots.delete_warning": (
            "Esta acción es irreversible. El snapshot se eliminará permanentemente del disco."
        ),
        "snapshots.delete_last_root_warning": (
            "Este es el último snapshot ROOT — carbonara-restore.sh también se "
            "eliminará, ya que no quedará nada para restaurar."
        ),
        "snapshots.delete_password_note": (
            "Se le pedirá la contraseña de root para completar la eliminación."
        ),
        "snapshots.delete_progress_title": "Eliminando Snapshot",
        "snapshots.delete_awaiting_auth": "Esperando autenticación...",
        "snapshots.delete_failed_message": "Error al eliminar el snapshot:\n\n{msg}",
        "snapshots.delete_cancelled": "Operación cancelada.",
        "snapshots.delete_success": "Snapshot {name} eliminado correctamente.",

        # ── Sincronización automática (badge + diálogo) ──
        "snapshots.sync_badge_title": "Sincronización automática",
        "snapshots.sync_badge_disabled": "desactivada",
        "snapshots.sync_badge_next": "próxima {when}",
        "snapshots.sync_dialog_title": "Sincronización Automática",
        "snapshots.sync_enabled": "Activada",
        "snapshots.sync_disabled": "Desactivada",
        "snapshots.sync_frequency_label": "FRECUENCIA",
        "snapshots.sync_freq_daily": "Diaria",
        "snapshots.sync_freq_weekly": "Semanal",
        "snapshots.sync_freq_custom": "Personalizada",
        "snapshots.sync_time_label": "HORA",
        "snapshots.sync_scope_label": "ALCANCE",
        "snapshots.sync_last_run_label": "Última ejecución",
        "snapshots.sync_next_run_label": "Próxima ejecución",
        "snapshots.sync_never_run": "Nunca se ejecutó",
        "snapshots.sync_not_scheduled": "No programado",
        "snapshots.sync_weekday_label": "DÍA DE LA SEMANA",
        "snapshots.sync_custom_label": "EXPRESIÓN PERSONALIZADA (systemd OnCalendar)",
        "snapshots.sync_custom_hint": "Ej: *-*-* 03:00:00 (todos los días a las 3h) · Sun *-*-* 04:00:00 (domingos a las 4h)",
        "snapshots.sync_weekday_mon": "Lun",
        "snapshots.sync_weekday_tue": "Mar",
        "snapshots.sync_weekday_wed": "Mié",
        "snapshots.sync_weekday_thu": "Jue",
        "snapshots.sync_weekday_fri": "Vie",
        "snapshots.sync_weekday_sat": "Sáb",
        "snapshots.sync_weekday_sun": "Dom",
        "snapshots.sync_save_button": "Guardar programación",
        "snapshots.sync_cancel_button": "Cancelar programación",
        "snapshots.sync_destinations_label": "DESTINOS PARA SINCRONIZAR",
        "snapshots.sync_no_destinations_found": "No se encontró ningún destino de backup en el sistema.",
        "snapshots.sync_no_destination": "Seleccione un destino de backup antes de guardar la programación.",
        "snapshots.sync_install_failed": "Error al aplicar la programación en el sistema:\n\n{msg}",
        "snapshots.sync_result_success": "éxito",
        "snapshots.sync_result_failed": "falló",
        "snapshots.sync_result_skipped": "omitido",
        "snapshots.sync_result_nothing": "nada que sincronizar",
        "snapshots.sync_last_run_value": "{when} · {result}",
        "snapshots.sync_toast_success": "Sincronización automática completada — {kinds}",
        "snapshots.sync_toast_failed": "La sincronización automática falló — vea la programación para más detalles",
        "snapshots.sync_toast_nothing": "La sincronización automática está activa, pero no hay ningún snapshot para sincronizar — cree uno primero",

        # ── Confirmar creación de snapshot ──
        "snapshots.create_confirm_title": "Crear Snapshot",
        "snapshots.create_confirm_body": "Está a punto de crear un snapshot con el alcance:",
        "snapshots.create_confirm_desc_root": "Esto generará un nuevo snapshot de / en el destino seleccionado. Puede tardar bastante según el tamaño.",
        "snapshots.create_confirm_desc_home": "Esto generará un nuevo snapshot de /home en el destino seleccionado. Puede tardar bastante según el tamaño.",
        "snapshots.create_confirm_desc_both": "Esto generará nuevos snapshots de / y /home en el destino seleccionado. Puede tardar bastante según el tamaño.",
        "snapshots.sync_backend_note": (
            "Los cambios se aplican en el sistema (systemd) en cuanto guarda."
        ),

        # ── Restaurar HOME sin reiniciar ──
        "snapshots.home_live_title": "Restaurar HOME sin reiniciar",
        "snapshots.home_live_warning": (
            "Esto reemplaza los archivos actuales de /home por los de este "
            "snapshot, en el sistema que ya está ejecutándose (sin ISO live). "
            "Al finalizar, la sesión gráfica se cierra (logout) — guarde su "
            "trabajo antes de continuar."
        ),
        "snapshots.home_live_checkbox": "Entiendo que la sesión se cerrará y los archivos actuales de /home serán reemplazados",
        "snapshots.home_live_confirm": "Restaurar",
        "snapshots.sync_confirm_title": "Confirmar sincronización",
        "snapshots.sync_confirm_header": "Sincronizar Snapshot",
        "snapshots.sync_confirm_warning": "El snapshot se actualizará con el estado actual del sistema. Solo se transferirán los archivos modificados.",
        "snapshots.sync_confirm_button": "Sincronizar",
        "snapshots.pair_sync_title": "¿Sincronizar también?",
        "snapshots.pair_sync_message": "El snapshot {kind} correspondiente también se puede sincronizar ahora, manteniendo ROOT y HOME emparejados.",
        "snapshots.pair_sync_cancel": "Ahora no",
        "snapshots.pair_sync_confirm": "Sincronizar {kind}",
        "snapshots.verify_select_title": "Elegir snapshots para verificar",
        "snapshots.verify_select_msg": "Por defecto solo el más reciente de cada tipo viene marcado. Marque otros snapshots si también quiere verificarlos:",
        "snapshots.verify_select_confirm": "Verificar seleccionados",
        "snapshots.verify_results_title_both": "ROOT y HOME están desactualizados",
        "snapshots.verify_results_title_multi": "{count} snapshots {kind} están desactualizados",
        "snapshots.verify_results_title_single": "{kind} está desactualizado",
        "snapshots.verify_results_msg": "rsync --dry-run encontró cambios reales en el sistema que aún no están en los snapshots de abajo. Elija cuáles sincronizar:",
        "snapshots.verify_results_cancel": "Ahora no",
        "snapshots.verify_results_sync": "Sincronizar",
        "snapshots.verify_results_sync_all": "Sincronizar todos ({count})",
        "snapshots.verify_results_sync_one": "Sincronizar {kind}",
        "snapshots.verify_results_sync_n": "Sincronizar {count} seleccionados",

        # ── Diálogo Acerca de ──
        "about.description": "Herramienta de administración de sistema para Arch Linux —\nsnapshots, copias de seguridad, ISOs live y diagnósticos.",
        "about.developed_by": "DESARROLLADO POR",

        # ── Penguin's Eggs ──
        "eggs.subtitle": "Cree, verifique e instale ISOs live de Arch Linux",
        "eggs.destination_label": "Destino de la ISO:",
        "eggs.not_mounted": "no montado",
        "eggs.no_iso_this_disk": "Sin ISO en este disco",
        "eggs.no_iso_yet": "Todavía no se generó ninguna ISO",
        "eggs.free_of_total": "{free} GB libres de {total} GB  •  {mount}  •  {fs}",
        "eggs.free_percent": "{pct}% libre",
        "eggs.disk_label_free": "libre",
        "eggs.btn_delete": "ELIMINAR",
        "eggs.create_title": "Crear Penguin's Eggs",
        "eggs.create_desc": "Genera una ISO live (o mueve la que ya está lista a Ventoy).",
        "eggs.check_title": "Verificar Penguin's Eggs .iso",
        "eggs.check_desc": "Verifica si hay una .iso pendiente y la respalda automáticamente.",
        "eggs.badge_requires_root": "requiere root",
        "eggs.open_broot_title": "Abrir archivos — broot",
        "eggs.open_broot_desc": "Abre Ventoy (destino de la ISO) en broot.",
        "eggs.open_nautilus_title": "Abrir archivos — Nautilus",
        "eggs.open_nautilus_desc": "Abre Ventoy (destino de la ISO) en Nautilus.",
        "eggs.install_title_not_installed": "Instalación de Penguin's Eggs y Calamares",
        "eggs.install_desc_not_installed": "Instala penguins-eggs y el módulo Calamares, si es necesario.",
        "eggs.install_action_install": "Instalar",
        "eggs.install_title_installed": "Actualizar Penguin's Eggs",
        "eggs.install_checked_suffix": '<br><span style="color:#60a5fa;">verificado a las {time}</span>',
        "eggs.install_version_unknown": "versión instalada",
        "eggs.install_desc_update_available": (
            "Actual: {current} — nueva versión v{update} disponible en el AUR.{suffix}"
        ),
        "eggs.install_action_update": "Actualizar",
        "eggs.install_desc_up_to_date": "Actual: {current} — actualizado, última versión.{suffix}",
        "eggs.install_action_check": "Verificar",
        "eggs.empty_iso_list": "Todavía no se generó ninguna ISO.",
        "eggs.iso_list_header": "ISOs existentes",
        "eggs.force_kill_link": "¿Parece bloqueado? Forzar cierre",
        "eggs.executing_prefix": "Ejecutando: {title}",
        "eggs.delete_failed": "Error al eliminar: {err}",
        "eggs.error_running": "Error al ejecutar:\n\n{err}",
        "eggs.error_opening": "No se pudo abrir: {exc}",
        "eggs.creating_title": "Creando Penguin's Eggs...",
        "eggs.creating_status": "Creando ISO...",
        "eggs.updating_before_create_title": "Actualizando Penguin's Eggs...",
        "eggs.updating_before_create_status": "Actualizando antes de crear...",
        "eggs.checking_title": "Verificando Penguin's Eggs...",
        "eggs.checking_status": "Verificando .iso...",
        "eggs.installing_status": "Instalando...",
        "eggs.checking_updates_status": "Verificando actualizaciones...",
        "eggs.delete_iso_header": "Eliminar ISO",
        "eggs.delete_iso_warning": (
            "Esta acción es irreversible. La ISO se eliminará permanentemente del disco."
        ),
    },
}

DEFAULT_LANGUAGE = "pt"
LANGUAGE_NAMES = {"pt": "Português", "en": "English", "es": "Español"}


class _I18n(QObject):
    """Estado global do idioma atual + sinal pra widgets se atualizarem
    sozinhos quando o usuário trocar, sem precisar reiniciar o app."""

    language_changed = Signal(str)  # emite o novo código do idioma

    def __init__(self) -> None:
        super().__init__()
        self._language = self._load_saved_language()

    def _load_saved_language(self) -> str:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            lang = data.get("language", DEFAULT_LANGUAGE)
            if lang in TRANSLATIONS:
                return lang
        except (OSError, ValueError):
            pass
        return DEFAULT_LANGUAGE

    def _save_language(self, lang: str) -> None:
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump({"language": lang}, fh, indent=2)
        except OSError:
            pass

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, lang: str) -> None:
        if lang not in TRANSLATIONS:
            return
        if lang == self._language:
            return
        self._language = lang
        self._save_language(lang)
        self.language_changed.emit(lang)


# Instância única compartilhada por todo o app.
i18n = _I18n()


def tr(key: str) -> str:
    """Traduz `key` pro idioma atual. Se a chave não existir no idioma
    atual, cai pro português; se também não existir lá, devolve a
    própria chave (nunca lança exceção, nunca quebra a UI)."""
    table = TRANSLATIONS.get(i18n.language, TRANSLATIONS[DEFAULT_LANGUAGE])
    if key in table:
        return table[key]
    return TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
