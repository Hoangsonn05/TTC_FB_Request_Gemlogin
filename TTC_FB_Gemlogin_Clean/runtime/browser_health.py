# -*- coding: utf-8 -*-

def page_is_alive(page) -> bool:
    if page is None:
        return False
    try:
        return not page.is_closed()
    except Exception:
        return False
