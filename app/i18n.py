"""Локализация: русский — основной язык (msgid), en/kk — каталоги переводов.

Каталоги компилируются из .po в .mo прямо при старте приложения, чтобы не
зависеть от команд сборки на деплое.
"""
import os

LOCALE_MAP = {'ru': 'ru', 'en': 'en', 'kz': 'kk'}   # наш код языка -> локаль Babel


def select_locale():
    from flask_login import current_user
    try:
        if current_user.is_authenticated:
            return LOCALE_MAP.get(current_user.language, 'ru')
    except Exception:
        pass
    return 'ru'


def compile_catalogs(root='translations'):
    """Compile .po -> .mo when missing or stale (runs in milliseconds)."""
    from babel.messages.pofile import read_po
    from babel.messages.mofile import write_mo

    if not os.path.isdir(root):
        return
    for lang in os.listdir(root):
        po_path = os.path.join(root, lang, 'LC_MESSAGES', 'messages.po')
        mo_path = os.path.join(root, lang, 'LC_MESSAGES', 'messages.mo')
        if not os.path.isfile(po_path):
            continue
        if (os.path.isfile(mo_path)
                and os.path.getmtime(mo_path) >= os.path.getmtime(po_path)):
            continue
        with open(po_path, 'rb') as f:
            catalog = read_po(f, locale=lang)
        with open(mo_path, 'wb') as f:
            write_mo(f, catalog)
