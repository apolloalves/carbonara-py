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
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# ── Onde a escolha de idioma fica salva entre sessões ──────────────────────
_CONFIG_PATH = Path.home() / ".config" / "carbonara" / "language.json"

# ── Dicionário de traduções ─────────────────────────────────────────────────
# Chaves com namespace por página (ex: "clonezilla.title") pra evitar colisão
# entre páginas que usam a mesma palavra em contextos diferentes.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "pt": {
        "menu.idioma": "Idioma",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Fechar",
        "common.cancel": "Cancelar",
        "common.confirm": "Confirmar",
        "common.delete": "Excluir",

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
    },
    "en": {
        "menu.idioma": "Language",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Close",
        "common.cancel": "Cancel",
        "common.confirm": "Confirm",
        "common.delete": "Delete",

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
    },
    "es": {
        "menu.idioma": "Idioma",
        "menu.back_to_menu": "Back to menu: button or Esc",
        "common.close": "Cerrar",
        "common.cancel": "Cancelar",
        "common.confirm": "Confirmar",
        "common.delete": "Eliminar",

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
