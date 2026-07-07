import os
from app import create_app, db
from app.models import User, Equipment

app = create_app(os.environ.get('FLASK_ENV', 'development'))

@app.cli.command('seed')
def seed():
    """Seed the database with initial data for testing."""
    db.create_all()

    # Create IT Admin (you)
    if not User.query.filter_by(email='admin@cis.kz').first():
        admin = User(
            first_name = 'Alex',
            last_name  = 'Marat',
            email      = 'admin@cis.kz',
            role       = 'it_admin',
            department = 'it',
            language   = 'ru',
        )
        admin.set_password('admin123')
        db.session.add(admin)

    # Create Zhanibek
    if not User.query.filter_by(email='zhanibek@cis.kz').first():
        zh = User(
            first_name = 'Zhanibek',
            last_name  = 'M',
            email      = 'zhanibek@cis.kz',
            role       = 'dept_head',
            department = 'it',
            language   = 'ru',
        )
        zh.set_password('zhanibek123')
        db.session.add(zh)

    # Sample mechanic user
    if not User.query.filter_by(email='mechanic@cis.kz').first():
        mech = User(
            first_name = 'Aibek',
            last_name  = 'K',
            email      = 'mechanic@cis.kz',
            role       = 'mechanic',
            department = 'mechanic',
            language   = 'ru',
        )
        mech.set_password('mechanic123')
        db.session.add(mech)

    # Sample equipment
    units = [
        ('Unit-07', 'Frac Pump',    'Block 4, Field A', 'maintenance', 2000),
        ('Unit-12', 'Blender',      'Field A',          'deployed',    1200),
        ('Unit-19', 'Wireline',     'Field B Well 3',   'deployed',    None),
        ('Unit-23', 'Coil Tubing',  'Base Atyrau',      'idle',        800),
        ('Unit-31', 'Frac Pump',    'Field C',          'deployed',    2000),
    ]
    for uid, name, loc, status, hp in units:
        if not Equipment.query.filter_by(unit_id=uid).first():
            eq = Equipment(unit_id=uid, name=name, location=loc, status=status, horsepower=hp)
            db.session.add(eq)

    db.session.commit()
    print('Database seeded successfully.')
    print('Login: admin@cis.kz / admin123')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)  # ← all interfaces
