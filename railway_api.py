from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATABASE_FILE = 'database.json'

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f)

@app.route('/db_api.php', methods=['GET', 'POST'])
def handle_api():
    if request.method == 'GET':
        action = request.args.get('action')
        if action == 'metadata':
            db = load_db()
            return jsonify({
                'success': True,
                'total_lines': len(db),
                'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'compare':
            combos_text = request.form.get('combos', '')
            combos_list = [c.strip() for c in combos_text.split('\n') if c.strip() and ':' in c]
            
            db = load_db()
            non_matched = []
            
            for combo in combos_list:
                if combo not in db:
                    non_matched.append(combo)
            
            return jsonify({
                'success': True,
                'total_checked': len(combos_list),
                'matches': len(combos_list) - len(non_matched),
                'non_matches': len(non_matched),
                'non_matched_combos': non_matched
            })
        
        elif action == 'add_combo':
            combo = request.form.get('combo', '')
            if combo and ':' in combo:
                db = load_db()
                if combo not in db:
                    db[combo] = {
                        'added_date': datetime.now().isoformat(),
                        'source': request.form.get('source', 'phone_checker')
                    }
                    save_db(db)
                    return jsonify({'success': True, 'added': True})
                return jsonify({'success': True, 'added': False, 'duplicate': True})
            
            return jsonify({'success': False, 'error': 'Invalid combo'})
    
    return jsonify({'success': False, 'error': 'Invalid request'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)