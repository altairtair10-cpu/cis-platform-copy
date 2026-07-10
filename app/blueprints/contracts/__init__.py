from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import Contract, ContractSummaryRow, db

contracts = Blueprint('contracts', __name__,
                      url_prefix='/contracts',
                      template_folder='../../app/templates/contracts')


def _build_context(contract):
    """Reshape the DB rows into the same dict structure the template already
    expects, so no template changes were needed for this migration off of the
    hardcoded dict."""
    summary = []
    for row in contract.summary_rows:
        deviation = row.fact_q - row.plan_q
        pct = round(row.fact_q / row.plan_q * 100) if row.plan_q > 0 else 0
        summary.append({
            'name': row.name, 'plan_year': row.plan_year, 'plan_q': row.plan_q,
            'fact_q': row.fact_q, 'unit': row.unit, 'color': row.color,
            'deviation': deviation, 'pct': pct, 'id': row.id,
        })

    detail = []
    for group in contract.detail_groups:
        rows = []
        for row in group.rows:
            pct = round(row.done / row.contract_qty * 100) if row.contract_qty > 0 else 0
            rows.append({
                'name': row.name, 'contract': row.contract_qty, 'done': row.done,
                'remainder': row.remainder, 'pct': pct,
            })
        detail.append({'group': group.name, 'rows': rows})

    return {
        'client': contract.client,
        'period': contract.period,
        'updated': contract.updated_at.strftime('%d.%m.%Y') if contract.updated_at else '—',
        'summary': summary,
        'detail': detail,
    }


@contracts.route('/')
@login_required
def index():
    contract = Contract.query.order_by(Contract.id.desc()).first()
    if not contract:
        return render_template('contracts/index.html', data=None)
    return render_template('contracts/index.html', data=_build_context(contract), contract=contract)


@contracts.route('/<int:row_id>/update-fact', methods=['POST'])
@login_required
def update_fact(row_id):
    """Lets an authorized user update the quarterly 'done' figure — the one
    number that actually changes week to week — without touching anything
    else about the contract."""
    if not current_user.can_access('kpi') and current_user.role != 'it_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('contracts.index'))

    row = ContractSummaryRow.query.get_or_404(row_id)
    try:
        new_value = int(request.form.get('fact_q', row.fact_q))
    except (TypeError, ValueError):
        flash('Invalid number.', 'warning')
        return redirect(url_for('contracts.index'))

    row.fact_q = new_value
    db.session.commit()
    flash('Updated.', 'success')
    return redirect(url_for('contracts.index'))