"""Спецификации кадровых приказов (фаза 2 дорожной карты).

Один приказ = Document(doc_type='hr_order') + HROrderDetail. Вместо 11
почти одинаковых форм — одна форма, управляемая спецификацией: какие поля
показать, какое поле является «датой вступления в силу», и какой эффект
приказ оказывает на карточку сотрудника при регистрации.

Поле спецификации:
    name      — имя поля формы (уходит в fields_json)
    label     — подпись
    type      — text | date | number | select | textarea
    options   — список вариантов (для select)
    required  — обязательное поле
    help      — подсказка под полем
    placeholder

ORDER_SPECS[kind] = {
    label, category, icon, effective_field, employee_status_hint, fields[]
}

Порядок регистрации применяет эффект (см. _apply_order_effect в orders.py).
"""
from app.models import EMPLOYEE_SCHEDULES

_BASIS = {'name': 'basis', 'label': 'Основание', 'type': 'text',
          'placeholder': 'заявление / служебная записка / № и дата'}
_NOTE = {'name': 'note', 'label': 'Примечание', 'type': 'textarea'}


ORDER_SPECS = {
    # ── ЛИЧНЫЙ СОСТАВ ─────────────────────────────────────────────────────
    'transfer': {
        'label': 'Приказ о переводе',
        'category': 'ls', 'icon': 'ti-arrows-exchange',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'new_position_ru', 'label': 'Новая должность (рус)', 'type': 'text', 'required': True, 'half': True},
            {'name': 'new_position_kz', 'label': 'Новая должность (каз)', 'type': 'text', 'half': True},
            {'name': 'new_department', 'label': 'Новое подразделение', 'type': 'text'},
            {'name': 'transfer_type', 'label': 'Вид перевода', 'type': 'select',
             'options': ['Постоянный', 'Временный']},
            {'name': 'effective_date', 'label': 'Дата перевода', 'type': 'date', 'required': True, 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'salary': {
        'label': 'Приказ об изменении заработной платы',
        'category': 'ls', 'icon': 'ti-cash',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'new_salary', 'label': 'Новый оклад, ₸', 'type': 'number', 'required': True, 'half': True,
             'help': 'Целое число в тенге (без копеек)'},
            {'name': 'effective_date', 'label': 'Дата вступления в силу', 'type': 'date', 'required': True, 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'combine': {
        'label': 'Приказ о совмещении / замещении',
        'category': 'ls', 'icon': 'ti-users-group',
        'effective_field': 'period_from',
        'fields': [
            {'name': 'combine_position', 'label': 'Совмещаемая должность', 'type': 'text', 'required': True},
            {'name': 'combine_percent', 'label': 'Доплата, %', 'type': 'number', 'half': True},
            {'name': 'period_from', 'label': 'Период с', 'type': 'date', 'half': True},
            {'name': 'period_to', 'label': 'Период по', 'type': 'date', 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'schedule': {
        'label': 'Приказ об изменении графика / вахты',
        'category': 'ls', 'icon': 'ti-calendar-time',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'new_schedule', 'label': 'Новый график / вахта', 'type': 'select',
             'options': EMPLOYEE_SCHEDULES, 'required': True, 'half': True},
            {'name': 'effective_date', 'label': 'Дата вступления в силу', 'type': 'date', 'required': True, 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'bonus': {
        'label': 'Приказ о премировании',
        'category': 'ls', 'icon': 'ti-award',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'bonus_reason', 'label': 'За что', 'type': 'text', 'required': True},
            {'name': 'bonus_amount', 'label': 'Сумма премии, ₸', 'type': 'number', 'half': True},
            {'name': 'bonus_percent', 'label': 'или % от оклада', 'type': 'number', 'half': True},
            {'name': 'effective_date', 'label': 'Дата', 'type': 'date', 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'discipline': {
        'label': 'Приказ о дисциплинарном взыскании',
        'category': 'ls', 'icon': 'ti-alert-triangle',
        'effective_field': 'incident_date',
        'fields': [
            {'name': 'measure', 'label': 'Мера взыскания', 'type': 'select',
             'options': ['Замечание', 'Выговор', 'Строгий выговор'], 'required': True, 'half': True},
            {'name': 'incident_date', 'label': 'Дата проступка', 'type': 'date', 'half': True},
            {'name': 'reason', 'label': 'Обстоятельства', 'type': 'textarea', 'required': True},
            _BASIS, _NOTE,
        ],
    },
    'termination': {
        'label': 'Приказ об увольнении',
        'category': 'ls', 'icon': 'ti-user-x',
        'effective_field': 'termination_date',
        'fields': [
            {'name': 'termination_date', 'label': 'Дата увольнения', 'type': 'date', 'required': True, 'half': True},
            {'name': 'ground', 'label': 'Основание увольнения', 'type': 'select',
             'options': ['По собственному желанию', 'По соглашению сторон',
                         'По инициативе работодателя', 'Истечение срока договора',
                         'Иное'], 'required': True, 'half': True},
            {'name': 'compensation', 'label': 'Компенсация за неисп. отпуск', 'type': 'text',
             'placeholder': 'кол-во дней / сумма'},
            _BASIS, _NOTE,
        ],
    },

    # ── ОТПУСКА ──────────────────────────────────────────────────────────
    'vacation': {
        'label': 'Приказ о ежегодном трудовом отпуске',
        'category': 'vacation', 'icon': 'ti-beach',
        'effective_field': 'period_from',
        'fields': [
            {'name': 'period_from', 'label': 'Отпуск с', 'type': 'date', 'required': True, 'half': True},
            {'name': 'period_to', 'label': 'Отпуск по', 'type': 'date', 'required': True, 'half': True},
            {'name': 'days', 'label': 'Календарных дней', 'type': 'number', 'half': True},
            {'name': 'payout', 'label': 'Отпускные', 'type': 'text', 'placeholder': 'сумма / расчёт'},
            _BASIS, _NOTE,
        ],
    },
    'vacation_unpaid': {
        'label': 'Приказ об отпуске без сохранения з/п',
        'category': 'vacation', 'icon': 'ti-calendar-off',
        'effective_field': 'period_from',
        'fields': [
            {'name': 'period_from', 'label': 'Отпуск с', 'type': 'date', 'required': True, 'half': True},
            {'name': 'period_to', 'label': 'Отпуск по', 'type': 'date', 'required': True, 'half': True},
            {'name': 'days', 'label': 'Календарных дней', 'type': 'number', 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'recall': {
        'label': 'Приказ об отзыве из отпуска',
        'category': 'vacation', 'icon': 'ti-arrow-back-up',
        'effective_field': 'recall_date',
        'fields': [
            {'name': 'recall_date', 'label': 'Дата выхода из отпуска', 'type': 'date', 'required': True, 'half': True},
            {'name': 'unused_days', 'label': 'Неиспользованных дней', 'type': 'number', 'half': True},
            _BASIS, _NOTE,
        ],
    },

    # ── КОМАНДИРОВКИ ─────────────────────────────────────────────────────
    'trip': {
        'label': 'Приказ о командировании',
        'category': 'trip', 'icon': 'ti-plane',
        'effective_field': 'period_from',
        'fields': [
            {'name': 'destination', 'label': 'Пункт назначения', 'type': 'text', 'required': True},
            {'name': 'purpose_text', 'label': 'Цель командировки', 'type': 'textarea', 'required': True},
            {'name': 'period_from', 'label': 'С', 'type': 'date', 'required': True, 'half': True},
            {'name': 'period_to', 'label': 'По', 'type': 'date', 'required': True, 'half': True},
            {'name': 'days', 'label': 'Дней', 'type': 'number', 'half': True},
            {'name': 'transport', 'label': 'Транспорт', 'type': 'text', 'half': True},
            {'name': 'per_diem', 'label': 'Суточные / расходы', 'type': 'text'},
            _BASIS, _NOTE,
        ],
    },

    # ── ПРОИЗВОДСТВЕННЫЕ ─────────────────────────────────────────────────
    'overtime': {
        'label': 'Приказ о работе в выходной / сверхурочно',
        'category': 'production', 'icon': 'ti-clock-plus',
        'effective_field': 'work_date',
        'fields': [
            {'name': 'work_date', 'label': 'Дата работы', 'type': 'date', 'required': True, 'half': True},
            {'name': 'hours', 'label': 'Количество часов', 'type': 'number', 'half': True},
            {'name': 'compensation', 'label': 'Компенсация', 'type': 'select',
             'options': ['Оплата в повышенном размере', 'Другой день отдыха (отгул)']},
            {'name': 'reason', 'label': 'Причина (производственная необходимость)', 'type': 'textarea'},
            _BASIS, _NOTE,
        ],
    },

    'sick_leave': {
        'label': 'Приказ о больничном листе',
        'category': 'ls', 'icon': 'ti-heart-plus',
        'effective_field': 'period_from',
        'fields': [
            {'name': 'sick_note_number', 'label': '№ больничного листа', 'type': 'text', 'required': True, 'half': True},
            {'name': 'period_from', 'label': 'С', 'type': 'date', 'required': True, 'half': True},
            {'name': 'period_to', 'label': 'По', 'type': 'date', 'required': True, 'half': True},
            {'name': 'days', 'label': 'Дней', 'type': 'number', 'half': True},
            _BASIS, _NOTE,
        ],
    },

    # ── ПРОЧЕЕ ───────────────────────────────────────────────────────────
    'responsibility': {
        'label': 'Приказ о назначении ответственного',
        'category': 'other', 'icon': 'ti-shield-check',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'responsible_for', 'label': 'За что назначается ответственным', 'type': 'text',
             'required': True, 'placeholder': 'напр. «уборка склада»'},
            {'name': 'effective_date', 'label': 'Дата', 'type': 'date', 'half': True},
            {'name': 'until_date', 'label': 'До какой даты (если временно)', 'type': 'date', 'half': True},
            _BASIS, _NOTE,
        ],
    },
    'other': {
        'label': 'Приказ (прочее)',
        'category': 'other', 'icon': 'ti-file-text',
        'effective_field': 'effective_date',
        'fields': [
            {'name': 'subject', 'label': 'Тема приказа', 'type': 'text', 'required': True},
            {'name': 'effective_date', 'label': 'Дата', 'type': 'date', 'half': True},
            {'name': 'body', 'label': 'Содержание', 'type': 'textarea'},
            _BASIS,
        ],
    },
}
