from flask import Blueprint, render_template
from flask_login import login_required, current_user

contracts = Blueprint('contracts', __name__,
                      url_prefix='/contracts',
                      template_folder='../../app/templates/contracts')

@contracts.route('/')
@login_required
def index():
    contract_data = {
        'client': 'ЭМГ',
        'period': 'Q1 2026 · Январь — Март',
        'updated': '15.04.2026',
        'summary': [
            {'name': 'ГРП (всего)', 'plan_year': 131, 'plan_q': 51, 'fact_q': 23, 'unit': 'скв.', 'color': 'red'},
            {'name': 'ОГРП', 'plan_year': 37, 'plan_q': 18, 'fact_q': 12, 'unit': 'скв.', 'color': 'amber'},
            {'name': 'Малотонн. ГРП', 'plan_year': 60, 'plan_q': 30, 'fact_q': 9, 'unit': 'скв.', 'color': 'red'},
            {'name': 'МГРП', 'plan_year': 9, 'plan_q': 3, 'fact_q': 2, 'unit': 'скв.', 'color': 'amber'},
            {'name': 'ПЗР к ОГРП', 'plan_year': 37, 'plan_q': 16, 'fact_q': 10, 'unit': 'скв.', 'color': 'blue'},
            {'name': 'Освоение после ОГРП', 'plan_year': 37, 'plan_q': 16, 'fact_q': 9, 'unit': 'скв.', 'color': 'blue'},
        ],
        'detail': [
            {
                'group': 'ОГРП',
                'rows': [
                    {'name': 'ЭМГ ОГРП', 'contract': 30, 'done': 9, 'remainder': -6},
                    {'name': 'С.Нуржанов, Досмухамбетова, ЮВН Подкарниз', 'contract': 18, 'done': 4, 'remainder': -14},
                    {'name': 'Западная Прорва, Актобе', 'contract': 6, 'done': 2, 'remainder': -4},
                    {'name': 'ЮВН Подкарниз', 'contract': 3, 'done': 3, 'remainder': 0},
                    {'name': 'ЮВН Надкарниз, С.Балгымбаева, Акуудук', 'contract': 3, 'done': 0, 'remainder': -3},
                ]
            },
            {
                'group': 'Малотонн. ГРП / МГРП',
                'rows': [
                    {'name': 'Малотонн. ГРП', 'contract': 40, 'done': 9, 'remainder': -5},
                    {'name': 'МГРП', 'contract': 8, 'done': 1, 'remainder': -7},
                    {'name': 'МГРП КТМ', 'contract': 1, 'done': 1, 'remainder': 0},
                    {'name': 'ППК', 'contract': 1, 'done': 1, 'remainder': 0},
                ]
            },
        ]
    }

    for row in contract_data['summary']:
        row['deviation'] = row['fact_q'] - row['plan_q']
        row['pct'] = round(row['fact_q'] / row['plan_q'] * 100) if row['plan_q'] > 0 else 0

    for group in contract_data['detail']:
        for row in group['rows']:
            row['pct'] = round(row['done'] / row['contract'] * 100) if row['contract'] > 0 else 0

    return render_template('contracts/index.html', data=contract_data)