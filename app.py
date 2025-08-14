from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import string

# --- CONFIG ---
APP_HOST = "127.0.0.1"
APP_PORT = 5000
BASE = 62
ALPHABET = string.digits + string.ascii_letters  # 0-9a-zA-Z -> 62 chars

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urls.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret'  # change for production
db = SQLAlchemy(app)

# --- MODELS ---
class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    long_url = db.Column(db.String(2048), nullable=False)
    custom_alias = db.Column(db.String(128), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    clicks = db.Column(db.Integer, default=0)

    def short_code(self):
        # if custom alias present, use it
        if self.custom_alias:
            return self.custom_alias
        return encode_base62(self.id)

# --- HELPERS: Base62 ---
def encode_base62(num: int) -> str:
    if num == 0:
        return ALPHABET[0]
    arr = []
    base = BASE
    while num:
        rem = num % base
        num = num // base
        arr.append(ALPHABET[rem])
    arr.reverse()
    return ''.join(arr)

def decode_base62(s: str) -> int:
    base = BASE
    num = 0
    for ch in s:
        num = num * base + ALPHABET.index(ch)
    return num

# --- ROUTES ---
@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        long_url = request.form.get('long_url', '').strip()
        custom = request.form.get('custom_alias', '').strip() or None

        # basic validation
        from validators import url as is_url
        if not long_url or not is_url(long_url):
            flash('Please enter a valid URL (include http:// or https://)', 'error')
            return redirect(url_for('index'))

        # if custom alias requested -> check uniqueness
        if custom:
            existing = URL.query.filter_by(custom_alias=custom).first()
            if existing:
                flash('This custom alias is already taken. Choose another.', 'error')
                return redirect(url_for('index'))
            shortened = URL(long_url=long_url, custom_alias=custom)
            db.session.add(shortened)
            db.session.commit()
            short = shortened.custom_alias
        else:
            # store first (so we get ID) then generate short code from id
            new = URL(long_url=long_url)
            db.session.add(new)
            db.session.commit()
            short = new.short_code()
        short_link = f"http://{APP_HOST}:{APP_PORT}/{short}"
        flash('Short URL created!', 'success')
        return render_template('index.html', short_link=short_link)

    return render_template('index.html')

@app.route('/<string:short>')
def redirect_short(short):
    # first check if a custom alias exists
    entry = URL.query.filter_by(custom_alias=short).first()
    if not entry:
        # try decode base62 -> id
        try:
            id_num = decode_base62(short)
            entry = URL.query.get(id_num)
        except ValueError:
            entry = None

    if not entry:
        return render_template('404.html', short=short), 404

    entry.clicks += 1
    db.session.commit()
    return redirect(entry.long_url)

@app.route('/stats/<string:short>')
def stats(short):
    entry = URL.query.filter_by(custom_alias=short).first()
    if not entry:
        try:
            entry = URL.query.get(decode_base62(short))
        except Exception:
            entry = None
    if not entry:
        abort(404)
    return render_template('stats.html', entry=entry, short_link=f"http://{APP_HOST}:{APP_PORT}/{short}")

# simple API endpoint for JSON shorteners
@app.route('/api/shorten', methods=['POST'])
def api_shorten():
    data = request.get_json() or {}
    long_url = data.get('long_url')
    custom = data.get('custom_alias')
    from validators import url as is_url
    if not long_url or not is_url(long_url):
        return jsonify({'error': 'invalid url'}), 400
    if custom:
        if URL.query.filter_by(custom_alias=custom).first():
            return jsonify({'error': 'alias taken'}), 409
        item = URL(long_url=long_url, custom_alias=custom)
        db.session.add(item)
        db.session.commit()
        short = custom
    else:
        item = URL(long_url=long_url)
        db.session.add(item)
        db.session.commit()
        short = item.short_code()
    return jsonify({'short': f'http://{APP_HOST}:{APP_PORT}/{short}'}), 201

if __name__ == '__main__':
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
