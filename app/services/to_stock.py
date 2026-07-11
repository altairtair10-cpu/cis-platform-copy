"""Проверка наличия материалов для ТО по складской таблице (Остатки по базам)."""
import re


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def _stock_rows():
    """Складские строки; при неподключённой таблице — None (не падаем)."""
    try:
        from app.blueprints.inventory import get_inventory_rows
        return get_inventory_rows()
    except Exception:
        return None


def _row_total(row):
    """Суммируем все числовые колонки строки (остатки по базам)."""
    total = 0.0
    found = False
    for k, v in row.items():
        if _norm(k) in ('материал', 'предупреждение', 'ед. изм.', 'ед.изм.', 'единица'):
            continue
        try:
            total += float(str(v).replace(' ', '').replace(',', '.'))
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def check_to_parts(equipment, rows=None):
    """[{'part': ToPart, 'in_stock': float|None, 'enough': bool|None}].
    in_stock None = материал не найден на складе / склад не подключён."""
    if rows is None:
        rows = _stock_rows()
    index = {}
    if rows:
        for row in rows:
            material = _norm(row.get('Материал', ''))
            if material:
                index[material] = _row_total(row)

    out = []
    for part in equipment.to_parts.order_by('id'):
        stock = None
        key = _norm(part.name)
        if rows is not None:
            if key in index:
                stock = index[key]
            else:  # частичное совпадение («фильтр FF105» ~ «FF105»)
                for mat, total in index.items():
                    if key in mat or mat in key:
                        stock = total
                        break
        enough = None
        if stock is not None:
            enough = stock >= float(part.qty or 0)
        out.append({'part': part, 'in_stock': stock, 'enough': enough})
    return out
