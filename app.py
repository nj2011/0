from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import hashlib

app = Flask(__name__)
CORS(app)

# Database file path
DB_FILE = 'database.json'
ADMIN_KEY = "YOUR_SECRET_ADMIN_KEY_HERE"  # Change this!

# Load database
def load_database():
    if not os.path.exists(DB_FILE):
        return {"combos": [], "metadata": {"total_lines": 0, "date_added": "N/A", "added_by": "System"}}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"combos": [], "metadata": {"total_lines": 0, "date_added": "N/A", "added_by": "System"}}

# Save database
def save_database(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Hash combo for faster lookup
def hash_combo(combo):
    return hashlib.md5(combo.strip().lower().encode()).hexdigest()

@app.route('/', methods=['GET', 'POST'])
def handle_request():
    if request.method == 'GET':
        action = request.args.get('action')
        
        if action == 'metadata':
            db = load_database()
            return jsonify(db.get('metadata', {}))
        
        return jsonify({"status": "ok", "message": "Database server running"})
    
    elif request.method == 'POST':
        data = request.get_json() or request.form
        
        # Compare combos with database
        if 'combos' in data:
            combos_text = data['combos']
            combos = [c.strip() for c in combos_text.split('\n') if c.strip() and ':' in c]
            
            db = load_database()
            existing_hashes = set(db.get('hashes', []))
            
            matched = []
            non_matched = []
            
            for combo in combos:
                combo_hash = hash_combo(combo)
                if combo_hash in existing_hashes:
                    matched.append(combo)
                else:
                    non_matched.append(combo)
            
            return jsonify({
                'success': True,
                'total_checked': len(combos),
                'matches': len(matched),
                'non_matches': len(non_matched),
                'non_matched_combos': non_matched
            })
        
        # Add combos to database (admin only)
        elif 'add_combos' in data and data.get('admin_key') == ADMIN_KEY:
            new_combos = [c.strip() for c in data['add_combos'].split('\n') if c.strip() and ':' in c]
            
            db = load_database()
            existing_hashes = set(db.get('hashes', []))
            
            added = 0
            for combo in new_combos:
                combo_hash = hash_combo(combo)
                if combo_hash not in existing_hashes:
                    existing_hashes.add(combo_hash)
                    db['hashes'].append(combo_hash)
                    db['combos'].append(combo)
                    added += 1
            
            db['metadata'] = {
                'total_lines': len(db['combos']),
                'latest_added': added,
                'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'added_by': data.get('added_by', 'Admin')
            }
            
            save_database(db)
            
            return jsonify({
                'success': True,
                'added': added,
                'total': len(db['combos'])
            })
        
        return jsonify({'success': False, 'error': 'Invalid request'})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)